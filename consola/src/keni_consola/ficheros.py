"""Backend de FICHEROS YAML de la Consola Keni: el HISTORIAL DE PROMPTS vive en disco.

Los YAML estan organizados POR MARCA (agente = marca = carpeta), raiz =
`KENI_CONSOLA_RAIZ` (def `~/keni-proyectos`):

    <raiz>/<marca>/
        marca.yaml                  # id, etiqueta, id_metricas (al inicializar la marca)
        CLAUDE.md                   # minimo, si falta
        historial/<YYYY>/<MM>/<id>.yaml

ESQUEMA YAML: legible; el `id` es IMPLICITO (= nombre de fichero) y la `marca` la da
la CARPETA (no se repiten como campos dentro del YAML). Cuerpos largos (`resultado`)
salen en bloque `|`. Listas YAML nativas (no JSON embebido). Booleans nativos.
SIEMPRE `yaml.safe_load` al leer.

ESCRITURA ATOMICA: temporal en el mismo dir + `os.replace` (patron de
`secretos.py`). VALIDACION al leer: una entrada con YAML invalido, o con `estado` /
`red` fuera de la allowlist, se OMITE con log (degradado), nunca rompe el listado.

INDICE: `indice.py` (SQLite regenerable) mapea id -> (marca, tipo, ruta) + campos
filtrables. Se actualiza al escribir; si un YAML cambio por fuera (mtime) se
re-indexa; si el indice se borra, se reconstruye leyendo los ficheros.

ORDEN ESTABLE: las fechas de creacion llevan HORA (ISO datetime) para un orden
determinista.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from keni_shared.esquema_yaml import migrar, sellar

from . import config, indice, marcas, rutas
from .estados import ESTADOS_PIEZA, ESTADOS_TAREA  # re-export para la fachada
from .io_atomico import escribir_atomico
from .tiempo import hoy_utc, iso_utc

_log = logging.getLogger("keni_consola.ficheros")

__all__ = ["ESTADOS_TAREA", "ESTADOS_PIEZA"]

# Sub-carpetas por entidad dentro de la carpeta de cada marca.
_SUBDIR = {
    "pieza": "piezas",
    "plantilla": "plantillas",
}

# Marca por defecto para entidades creadas SIN marca (la carpeta necesita un slug).
_MARCA_SIN = "_sin-marca"

# Tipo de INDICE -> tipo de ESQUEMA (`keni_shared.esquema_yaml.VERSIONES`). Solo
# difieren en `historial` (indice) vs `historial_prompt` (esquema); el resto coincide.
_TIPO_ESQUEMA = {
    "pieza": "pieza",
    "plantilla": "plantilla",
    "historial": "historial_prompt",
}


# --------------------------------------------------------------------------- #
# Raiz / carpeta de marca                                                      #
# --------------------------------------------------------------------------- #


def raiz_datos() -> Path:
    """Raiz de datos de ficheros (CONTENIDO editorial por marca).

    `KENI_CONSOLA_RAIZ` la sobreescribe (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.raiz_proyectos()`): local `~/keni-proyectos`
    EXACTAMENTE como antes, o `<KENI_DATA_DIR>/keni-proyectos` en contenedor.
    """
    if (p := config.override_ruta(config.ENV_RAIZ)) is not None:
        return p
    return rutas.raiz_proyectos()


def _slug_marca(marca: str) -> str:
    """Slug de carpeta para una marca (cae a `_MARCA_SIN` si viene vacia)."""
    return marca or _MARCA_SIN


def carpeta_marca(marca: str) -> Path:
    """Carpeta `<raiz>/<marca>/`, creando `marca.yaml` y `CLAUDE.md` minimos si faltan."""
    carpeta = raiz_datos() / _slug_marca(marca)
    carpeta.mkdir(parents=True, exist_ok=True)
    _inicializar_marca(carpeta, marca)
    return carpeta


def _inicializar_marca(carpeta: Path, marca: str) -> None:
    """Crea `marca.yaml` (id/etiqueta/id_metricas) y un `CLAUDE.md` minimo si no existen."""
    meta = carpeta / "marca.yaml"
    if not meta.exists() and marca:
        datos = {
            "id": marca,
            "etiqueta": marcas.etiqueta_de(marca),
            "id_metricas": marcas.id_metricas_de(marca),
        }
        _escribir_yaml(meta, datos, tipo="marca")
    claude = carpeta / "CLAUDE.md"
    if not claude.exists() and marca:
        claude.write_text(
            f"# {marcas.etiqueta_de(marca)}\n\n"
            "Carpeta de contenido de esta marca (agente = marca = carpeta).\n"
            "El contenido (piezas, plantillas, RSS, hashtags, franjas, "
            "historial) vive aqui como ficheros YAML, fuente de verdad.\n",
            encoding="utf-8",
        )




def _marcas_en_disco() -> list[str]:
    """Slugs de marca presentes en disco (carpetas con `marca.yaml` o sub-carpetas)."""
    raiz = raiz_datos()
    if not raiz.is_dir():
        return []
    slugs: list[str] = []
    for hijo in sorted(raiz.iterdir()):
        if hijo.is_dir() and not hijo.name.startswith("."):
            slugs.append(hijo.name)
    return slugs


def _marca_de_slug(slug: str) -> str:
    """Traduce el slug de carpeta a la `marca` interna (`_MARCA_SIN` => '')."""
    return "" if slug == _MARCA_SIN else slug


# --------------------------------------------------------------------------- #
# YAML: lectura / escritura atomica                                            #
# --------------------------------------------------------------------------- #


class _DumperBloque(yaml.SafeDumper):
    """SafeDumper que vuelca los strings multilinea como bloque literal `|`.

    PyYAML por defecto representa los textos con saltos de linea en estilo plegado
    o entre comillas (feo de editar a mano). Forzamos el bloque `|` cuando el texto
    tiene saltos de linea, para que un humano (o Claude Code) edite el cuerpo
    (p. ej. `contenido`, `resultado`) comodamente. Si una linea tiene espacios al
    final, PyYAML cae solo a un estilo seguro (no se puede romper el round-trip).
    """


def _str_bloque(dumper: yaml.Dumper, data: str) -> Any:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_DumperBloque.add_representer(str, _str_bloque)


def _escribir_yaml(ruta: Path, datos: dict[str, Any], *, tipo: str) -> None:
    """Escribe un dict como YAML legible de forma ATOMICA (tmp + os.replace).

    `default_flow_style=False` (mapas/listas en bloque), `allow_unicode=True`
    (acentos sin escapar), `sort_keys=False` (respeta el orden dado), y bloque `|`
    para textos multilinea (via `_DumperBloque`). `sellar(tipo, ...)` estampa la
    `version` de esquema antes de volcar.
    """
    texto = yaml.dump(
        sellar(tipo, datos),
        Dumper=_DumperBloque,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )
    escribir_atomico(ruta, texto, sufijo=".yaml")


def _leer_yaml(ruta: Path, *, tipo: str) -> dict[str, Any] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa.

    Degrada con log (nunca lanza): un fichero ilegible se trata como ausente. Al
    leer aplica `migrar(tipo, ...)` (upgrade perezoso de esquema): un YAML
    legado sin `version` se trata como version 0 y se sube a la actual en memoria.
    """
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError:
        _log.warning("YAML invalido, se omite: %s", ruta)
        return None
    if not isinstance(datos, dict):
        _log.warning("YAML no es un mapa, se omite: %s", ruta)
        return None
    return migrar(tipo, datos)




def _nuevo_id() -> str:
    """Nuevo id corto (mismo formato que `db.py`: 12 hex)."""
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# Localizacion de una entidad por id (indice -> ruta; con re-indexado por mtime) #
# --------------------------------------------------------------------------- #


def _buscar_ruta(tipo: str, entidad_id: str) -> Path | None:
    """Ruta del fichero de una entidad por id: via indice, con fallback a escaneo.

    Si el indice apunta a una ruta que existe, se usa. Si no (indice borrado o
    desfasado), se reconstruye el indice de ese tipo y se reintenta.
    """
    entrada = indice.obtener(tipo, entidad_id)
    if entrada is not None:
        ruta = Path(entrada["ruta"])
        if ruta.exists():
            return ruta
    # Indice ausente o desfasado: reconstruir ese tipo y reintentar.
    _reindexar_tipo(tipo)
    entrada = indice.obtener(tipo, entidad_id)
    if entrada is not None:
        ruta = Path(entrada["ruta"])
        if ruta.exists():
            return ruta
    return None


def _indexar(tipo: str, marca: str, ruta: Path, datos: dict[str, Any]) -> None:
    """Da de alta/actualiza la entrada de indice de una entidad recien escrita."""
    indice.upsert(_a_entrada_indice(tipo, marca, ruta, datos))


def _a_entrada_indice(tipo: str, marca: str, ruta: Path, datos: dict[str, Any]) -> dict[str, Any]:
    """Construye la fila de indice (campos filtrables) de una entidad ya cargada."""
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        mtime = 0.0
    return {
        "id": ruta.stem,
        "tipo": tipo,
        "marca": marca,
        "ruta": str(ruta),
        "mtime": mtime,
        "red": datos.get("red", "") or "",
        "estado": datos.get("estado", "") or "",
        "evergreen": bool(datos.get("evergreen")),
        "fecha": datos.get("fecha", "") or "",
        "fecha_creacion": datos.get("fecha_creacion", "") or "",
    }


# --------------------------------------------------------------------------- #
# Reconstruccion del indice (regenerable desde los YAML)                       #
# --------------------------------------------------------------------------- #


def _rutas_de_tipo(tipo: str) -> list[tuple[str, Path]]:
    """Lista `(marca, ruta_yaml)` de TODAS las entidades de un tipo en todas las marcas."""
    pares: list[tuple[str, Path]] = []
    for slug in _marcas_en_disco():
        marca = _marca_de_slug(slug)
        if tipo == "historial":
            base = raiz_datos() / slug / "historial"
            if base.is_dir():
                pares.extend((marca, p) for p in base.rglob("*.yaml"))
        else:
            base = raiz_datos() / slug / _SUBDIR[tipo]
            if base.is_dir():
                pares.extend((marca, p) for p in sorted(base.glob("*.yaml")))
    return pares


def _reindexar_tipo(tipo: str) -> None:
    """Reconstruye en el indice TODAS las entradas de un `tipo` leyendo el disco."""
    entradas: list[dict[str, Any]] = []
    for marca, ruta in _rutas_de_tipo(tipo):
        datos = _leer_yaml(ruta, tipo=_TIPO_ESQUEMA[tipo])
        if datos is None:
            continue
        entradas.append(_a_entrada_indice(tipo, marca, ruta, datos))
    indice.reemplazar_tipo(tipo, entradas)




def _listar_validado(
    tipo: str,
    *,
    filtros: dict[str, Any] | None,
    parsear,  # noqa: ANN001 -- callable(datos, marca, id) -> dict | None
    limite: int | None = None,
    desplazamiento: int | None = None,
) -> list[dict[str, Any]]:
    """Lista entidades indexadas de un tipo, cargando+validando SOLO la pagina pedida.

    Si el indice esta vacio para ese tipo pero hay ficheros en disco, primero lo
    reconstruye (cubre el caso de indice borrado). Las entradas cuyo YAML ya no
    existe o no valida se OMITEN (degradado), sin romper el listado.

    `limite`/`desplazamiento` se EMPUJAN al indice (`LIMIT/OFFSET`): asi solo se leen
    los cuerpos YAML de la PAGINA, no de todas las coincidencias. `limite=None`
    devuelve el conjunto completo (retrocompat). Para que la reconstruccion perezosa
    no se salte por un OFFSET mas alla del final, el chequeo de "indice vacio" mira el
    conteo SIN paginar.
    """
    if indice.contar(tipo, filtros) == 0 and _rutas_de_tipo(tipo):
        _reindexar_tipo(tipo)
    entradas = indice.listar(tipo, filtros=filtros, limite=limite, desplazamiento=desplazamiento)
    salida: list[dict[str, Any]] = []
    for entrada in entradas:
        ruta = Path(entrada["ruta"])
        datos = _leer_yaml(ruta, tipo=_TIPO_ESQUEMA[tipo])
        if datos is None:
            continue
        item = parsear(datos, entrada["marca"], entrada["id"])
        if item is not None:
            salida.append(item)
    return salida


# --------------------------------------------------------------------------- #
# Piezas                                                                #
# --------------------------------------------------------------------------- #

























# --------------------------------------------------------------------------- #
# Plantillas                                                                   #
# --------------------------------------------------------------------------- #


















# --------------------------------------------------------------------------- #
# Historial de prompts (historial/<YYYY>/<MM>/<id>.yaml)                       #
# --------------------------------------------------------------------------- #


def _parsear_historial(datos: dict[str, Any], marca: str, hid: str) -> dict[str, Any]:
    """Reconstruye el dict publico de una entrada de historial (`piezas` lista, `metricas` dict|None)."""
    piezas = datos.get("piezas")
    if not isinstance(piezas, list):
        piezas = []
    metricas = datos.get("metricas")
    if not isinstance(metricas, dict) or not metricas:
        metricas = None
    return {
        "id": hid,
        "prompt": datos.get("prompt", "") or "",
        "marca": marca,
        "fecha": datos.get("fecha", "") or "",
        "resultado": datos.get("resultado", "") or "",
        "piezas": [p for p in piezas if isinstance(p, dict)],
        "titulo": datos.get("titulo", "") or "",
        # Atribucion por usuario. Ausente en historial legado => "".
        "autor_id": datos.get("autor_id", "") or "",
        "autor_nombre": datos.get("autor_nombre", "") or "",
        "metricas": metricas,
    }


def registrar_historial_prompt(
    prompt_id: str,
    marca: str,
    resultado: str,
    *,
    piezas: list[dict[str, Any]] | None = None,
    titulo: str = "",
    metricas: dict[str, Any] | None = None,
    autor: dict[str, str] | None = None,
) -> str:
    """Guarda una ejecucion de prompt (un YAML en `<marca>/historial/<YYYY>/<MM>/`) y devuelve su id.

    `metricas` (tokens/turnos/coste/duracion/modelo del run) se guarda como un mapa en
    el YAML, o se omite si es None. `autor` (atribucion por usuario) es
    `{"id", "usuario"}` o `None`; se persiste (vacio si anonimo / por token).
    """
    autor = autor or {}
    hid = _nuevo_id()
    ahora = datetime.now(UTC)
    cuerpo: dict[str, Any] = {
        "prompt": prompt_id,
        "fecha": hoy_utc().isoformat(),
        "fecha_creacion": iso_utc(ahora),
        "titulo": titulo,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "piezas": [dict(p) for p in (piezas or [])],
        "resultado": resultado,
    }
    if metricas:
        cuerpo["metricas"] = dict(metricas)
    carpeta = carpeta_marca(marca) / "historial" / f"{ahora.year:04d}" / f"{ahora.month:02d}"
    ruta = carpeta / f"{hid}.yaml"
    _escribir_yaml(ruta, cuerpo, tipo="historial_prompt")
    _indexar("historial", marca, ruta, cuerpo)
    return hid


def listar_historial_prompts(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Historial (recientes primero por fecha_creacion), con paginacion opcional."""
    return _listar_validado(
        "historial",
        filtros=None,
        parsear=_parsear_historial,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def contar_historial_prompts() -> int:
    """Total de entradas de historial (para el `total` de paginacion)."""
    if indice.contar("historial", None) == 0 and _rutas_de_tipo("historial"):
        _reindexar_tipo("historial")
    return indice.contar("historial", None)


def obtener_historial_prompt(historial_id: str) -> dict[str, Any] | None:
    """Una entrada del historial por id (None si no existe)."""
    ruta = _buscar_ruta("historial", historial_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="historial_prompt")
    if datos is None:
        return None
    # historial/<YYYY>/<MM>/<id>.yaml -> la marca es 3 niveles arriba del fichero.
    marca = _marca_de_slug(ruta.parent.parent.parent.parent.name)
    return _parsear_historial(datos, marca, historial_id)
