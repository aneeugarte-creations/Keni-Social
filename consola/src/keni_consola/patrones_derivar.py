"""Re-derivación de los perfiles de patrones por marca (CLI): Metricool -> perfil JSON + doc.

Es la pieza REPRODUCIBLE del ciclo editorial basado en datos (ver `patrones_marca`):

    extraer (Metricool, ventana de meses)  ->  derivar (cuartil top vs fondo)
      ->  perfil JSON (runtime o base)  ->  doc `editorial/rrss/<marca>/patrones`

Modos de salida (combinables):
  --store    escribe el perfil en `<dir_config>/patrones/<marca>.json` y CREA/ACTUALIZA
             el doc `editorial/rrss/<marca>/patrones` en el STORE de texto (lo que
             inyecta el pipeline de copy). Es el modo de PRODUCCIÓN (re-derivación
             periódica sin tocar git).
  --inicial  reescribe los ficheros del PAQUETE (`patrones_inicial/*.json` y
             `prompts_inicial/editorial/rrss/<marca>/patrones.md`): para versionar en git
             una nueva foto de los patrones (lo corre una persona/agente y commitea).

Fuente de piezas:
  --jsonl FICHERO   reutiliza un volcado previo (una pieza por línea, forma
                    `Pieza.model_dump()` + claves `marca`/`red` con id_metricas).
  (sin --jsonl)     extrae de la API de Metricool con las credenciales del config de
                    keni_metricas (`KENI_METRICAS_CONFIG`; requiere fuente real).

Uso típico (producción, dentro de un contenedor con /data):
    KENI_METRICAS_FUENTE=metricool python -m keni_consola.patrones_derivar --meses 6 --store
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from keni_shared import marcas as cat_marcas
from keni_shared.io_atomico import escribir_atomico

from . import patrones_marca

_log = logging.getLogger("keni_consola.patrones_derivar")

# Marcas por defecto: las del catálogo del cliente activo que tengan credenciales de
# Metricool configuradas (el resto se omite con aviso, no rompe).
MESES_DEFECTO = 6


# --- Extracción (frontera con keni_metricas) --------------------------------------


def _ventanas_mensuales(hasta: date, meses: int):
    """Ventanas [inicio, fin] de ~mes hacia atrás desde `hasta` (la API pagina mal los
    rangos largos: cuentas muy activas devuelven decenas de miles de posts)."""
    fin = hasta
    for _ in range(max(1, meses)):
        inicio = fin.replace(day=1)
        if inicio == fin:  # fin cae en día 1: la ventana es el mes anterior entero
            inicio = (fin - timedelta(days=1)).replace(day=1)
        yield inicio, fin
        fin = inicio - timedelta(days=1)


def extraer_piezas_metricool(
    ids_metricas: list[str], *, meses: int, hasta: date | None = None
) -> dict[str, list[dict[str, object]]]:
    """Piezas publicadas (posts + reels) por marca, leyendo la API real de Metricool.

    Devuelve `{id_metricas: [pieza_dict, ...]}` con la forma de `Pieza.model_dump()`
    + clave `red`. Ventanas mensuales con dedup por (id, fecha); una red/mes que
    falla se OMITE con WARN (cobertura parcial honesta, igual que keni_metricas).
    Import perezoso de keni_metricas: el módulo es importable sin credenciales.
    """
    from keni_metricas import config as cfg_metricas
    from keni_metricas.fuentes.metricool import _RED_CON_REELS, FuenteMetricool

    conf = cfg_metricas.cargar_config()
    configuradas = conf.metricool.marcas_configuradas()
    objetivo = {m: configuradas[m] for m in ids_metricas if m in configuradas}
    omitidas = [m for m in ids_metricas if m not in configuradas]
    if omitidas:
        _log.warning("sin credenciales de Metricool, se omiten: %s", ", ".join(omitidas))
    if not objetivo:
        return {}
    fuente = FuenteMetricool(objetivo)
    hasta = hasta or date.today()

    resultado: dict[str, list[dict[str, object]]] = {}
    for marca_id, cfg in objetivo.items():
        piezas: list[dict[str, object]] = []
        for plat_crudo in cfg.get("plataformas") or []:
            from keni_metricas.schema import Plataforma

            plat = plat_crudo if isinstance(plat_crudo, Plataforma) else Plataforma(plat_crudo)
            vistos: set[tuple[str, str]] = set()
            vacias = 0
            for inicio, fin in _ventanas_mensuales(hasta, meses):
                lote = []
                try:
                    posts = fuente._fetch_posts(marca_id, plat, inicio, fin)
                    lote.extend(fuente._parsear_posts(posts, plat, marca_id, inicio, fin))
                except Exception as e:  # noqa: BLE001 -- cobertura parcial, como keni_metricas
                    _log.warning("posts %s/%s %s: %s", marca_id, plat.value, inicio, e)
                if plat in _RED_CON_REELS:
                    lote.extend(fuente._reels_plataforma(marca_id, plat, inicio, fin))
                nuevas = 0
                for p in lote:
                    clave = (p.id, p.publicado.isoformat())
                    if p.id and clave in vistos:
                        continue
                    vistos.add(clave)
                    d = p.model_dump(mode="json")
                    d["red"] = plat.value
                    piezas.append(d)
                    nuevas += 1
                # Dos ventanas seguidas sin piezas = se acabó el historial de esa red.
                vacias = vacias + 1 if nuevas == 0 else 0
                if vacias >= 2:
                    break
        resultado[marca_id] = piezas
        _log.info("metricool: %s -> %d piezas", marca_id, len(piezas))
    return resultado


def cargar_piezas_jsonl(ruta: Path) -> dict[str, list[dict[str, object]]]:
    """Carga un volcado JSONL (clave `marca` = id_metricas) agrupado por marca."""
    resultado: dict[str, list[dict[str, object]]] = {}
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                d = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict):
                resultado.setdefault(str(d.get("marca") or ""), []).append(d)
    return resultado


# --- Salidas: runtime (store) y base (repo) -------------------------------------

_FRONTMATTER_DOC = """---
titulo: "Patrones medidos · {etiqueta}"
tipo: editorial
clase: ""
marcas: [{marca}]
pipelines: [redactar]
creado: {creado}
actualizado: {actualizado}
---

"""


def _doc_patrones(perfil: dict[str, object], marca_keni: str, *, creado: str, ahora: str) -> str:
    etiqueta = cat_marcas.etiqueta_de(marca_keni)
    cuerpo = patrones_marca.renderizar_doc(perfil, etiqueta)
    front = _FRONTMATTER_DOC.format(
        etiqueta=etiqueta, marca=marca_keni, creado=creado, actualizado=ahora
    )
    return front + cuerpo


def escribir_inicial(perfil: dict[str, object], marca_keni: str, *, ahora: str) -> list[Path]:
    """Escribe perfil JSON + doc generado en el PAQUETE (para commitear). Devuelve rutas."""
    base = Path(__file__).resolve().parent
    ruta_json = patrones_marca.dir_perfiles_inicial() / f"{marca_keni}.json"
    ruta_doc = base / "prompts_inicial" / "editorial" / "rrss" / marca_keni / "patrones.md"
    ruta_json.parent.mkdir(parents=True, exist_ok=True)
    ruta_doc.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ruta_json, json.dumps(perfil, ensure_ascii=False, indent=1) + "\n")
    # `creado` estable en la base (la identidad del doc no cambia entre regeneraciones).
    escribir_atomico(
        ruta_doc, _doc_patrones(perfil, marca_keni, creado="2026-06-10T00:00:00+00:00", ahora=ahora)
    )
    return [ruta_json, ruta_doc]


def aplicar_store(perfil: dict[str, object], marca_keni: str, *, ahora: str) -> str:
    """Aplica el perfil al RUNTIME: JSON en `<dir_config>/patrones` + doc en el store de texto.

    El doc `editorial/rrss/<marca>/patrones` se CREA si no existe y se ACTUALIZA si ya
    está (es un doc generado, de dueño máquina; el humano edita Voz/Reglas, no este).
    Devuelve el id del documento en el store.
    """
    from . import libprompts

    dir_data = patrones_marca.dir_perfiles_data()
    dir_data.mkdir(parents=True, exist_ok=True)
    escribir_atomico(
        dir_data / f"{marca_keni}.json", json.dumps(perfil, ensure_ascii=False, indent=1) + "\n"
    )
    doc_id = f"editorial/rrss/{marca_keni}/patrones"
    cuerpo = patrones_marca.renderizar_doc(perfil, cat_marcas.etiqueta_de(marca_keni))
    if libprompts.obtener(doc_id) is None:
        # `crear` deriva el slug del título: "Patrones" -> ".../patrones", el MISMO id
        # con el que importa la base (`patrones.md`); así crear-primero e
        # inicializar-después convergen en un único documento.
        doc = libprompts.crear(
            "Patrones",
            tipo="editorial",
            carpeta=f"rrss/{marca_keni}",
            cuerpo=cuerpo,
            marcas=[marca_keni],
            pipelines=["redactar"],
        )
        return doc.id
    # Solo el cuerpo: sin `titulo` el doc no se mueve de ruta (el id es estable).
    libprompts.guardar(doc_id, cuerpo=cuerpo)
    return doc_id


# --- CLI ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m keni_consola.patrones_derivar", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--marca", action="append", default=None,
        help="id canónico de marca (repetible); por defecto, todas las del catálogo",
    )
    parser.add_argument("--meses", type=int, default=MESES_DEFECTO, help="ventana hacia atrás")
    parser.add_argument("--jsonl", type=Path, default=None, help="volcado previo en vez de la API")
    parser.add_argument("--store", action="store_true", help="aplica al runtime (data dir + store)")
    parser.add_argument("--inicial", action="store_true", help="reescribe la base del paquete")
    parser.add_argument(
        "--salida", type=Path, default=None, help="además, escribe los perfiles JSON en este dir"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    ids_keni = args.marca or [m for m, _ in cat_marcas.opciones()]
    invalidas = [m for m in ids_keni if not cat_marcas.es_marca(m)]
    if invalidas:
        parser.error(f"marca(s) desconocida(s): {', '.join(invalidas)}")
    a_metricas = {cat_marcas.id_metricas_de(m): m for m in ids_keni}

    if args.jsonl:
        por_marca = cargar_piezas_jsonl(args.jsonl)
    else:
        por_marca = extraer_piezas_metricool(list(a_metricas), meses=args.meses)

    ahora_dt = datetime.now(timezone.utc)
    ahora = ahora_dt.isoformat(timespec="seconds")
    salida = 0
    for id_metricas, marca_keni in a_metricas.items():
        piezas = por_marca.get(id_metricas) or []
        if not piezas:
            _log.warning("%s: sin piezas; no se deriva (se conserva el perfil anterior)", marca_keni)
            continue
        fechas = sorted(str(p.get("publicado") or "") for p in piezas if p.get("publicado"))
        perfil = patrones_marca.derivar_perfil(
            piezas, marca_keni,
            desde=fechas[0] if fechas else "", hasta=fechas[-1] if fechas else "",
            generado=ahora,
        )
        if not perfil["redes"]:
            _log.warning("%s: %d piezas pero ninguna red con muestra suficiente", marca_keni, len(piezas))
            continue
        print(f"{marca_keni}: {perfil['piezas']:,} piezas útiles, redes: {', '.join(perfil['redes'])}")  # type: ignore[arg-type]
        if args.salida:
            args.salida.mkdir(parents=True, exist_ok=True)
            escribir_atomico(
                args.salida / f"{marca_keni}.json",
                json.dumps(perfil, ensure_ascii=False, indent=1) + "\n",
            )
        if args.inicial:
            for ruta in escribir_inicial(perfil, marca_keni, ahora=ahora):
                print(f"  base: {ruta}")
        if args.store:
            print(f"  store: {aplicar_store(perfil, marca_keni, ahora=ahora)}")
    return salida


if __name__ == "__main__":
    sys.exit(main())
