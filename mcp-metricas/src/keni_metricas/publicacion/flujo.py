"""Flujo de aprobacion punta-a-punta para publicar copy YA aprobado.

╔══════════════════════════════════════════════════════════════════════════╗
║  SEGURIDAD — ORQUESTA PUBLICACION. LEER ANTES DE TOCAR.                     ║
║                                                                            ║
║  Este modulo NO duplica la logica del adaptador: solo la ORQUESTA. Toma    ║
║  copy ya aprobado (por plataforma), construye `Borrador`s, los encola en   ║
║  una `ColaPublicacion` y corre `publicar_pendientes(dry_run=True)`.        ║
║                                                                            ║
║  DRY-RUN POR DEFECTO. El camino por defecto NUNCA toca la red: produce un  ║
║  REPORTE de lo que esta encolado y de lo que SE ENVIARIA (los payloads de  ║
║  dry-run). La publicacion REAL solo ocurre si se pide explicitamente       ║
║  (`publicar_real=True`) Y hay token configurado en el adaptador; ademas    ║
║  exige una confirmacion clara. Espeja la seguridad de `meta.py`.           ║
║                                                                            ║
║  Postura del producto: el humano aprueba; nada se publica solo.            ║
╚══════════════════════════════════════════════════════════════════════════╝

Entrada estructurada (`EntradaPublicacion`): describe UNA publicacion ya
aprobada para UNA plataforma de Meta. Se puede cargar desde:

- un archivo JSON  -> `cargar_entradas(ruta)`  (extension .json)
- un archivo TOML  -> `cargar_entradas(ruta)`  (extension .toml)
- un dict de Python -> `EntradaPublicacion.model_validate(d)`

Formato del dict / JSON (una sola entrada o lista `{"publicaciones": [...]}`):

    {
      "plataforma": "instagram",        # facebook | instagram
      "cuenta": "IG_USER_ID",           # Page ID (FB) o IG User ID (IG)
      "texto": "Copy aprobado",         # cuerpo del post (sin hashtags)
      "media": [                          # opcional; refs (URL), nunca binarios
        {"tipo": "imagen", "url": "https://e/x.jpg", "descripcion": "alt"}
      ],
      "hashtags": ["deporte", "futbol"], # opcional; sin '#', se normalizan
      "publicar_en": "2026-05-24T18:00:00"  # opcional; ISO-8601, agenda en la cola
    }

En TOML, una lista se expresa con tablas `[[publicaciones]]`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from ..schema import Plataforma
from .cola import ColaPublicacion
from .meta import AdaptadorPublicacionMeta, ResultadoPublicacion
from .modelos import PLATAFORMAS_META, Borrador, MediaRef


# --- entrada estructurada --------------------------------------------------
class EntradaPublicacion(BaseModel):
    """Copy YA aprobado para UNA plataforma, listo para construir un `Borrador`.

    Es el contrato de entrada del flujo. Reutiliza los validadores de `Borrador`
    al materializarlo (`a_borrador`), por lo que aqui solo se modela la forma y
    el agendado opcional (`publicar_en`).
    """

    plataforma: Plataforma
    cuenta: str
    texto: str = ""
    media: list[MediaRef] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    # Hora opcional de publicacion (agenda en la cola). None = disparar ya.
    publicar_en: datetime | None = None

    @field_validator("plataforma")
    @classmethod
    def _plataforma_es_meta(cls, v: Plataforma) -> Plataforma:
        # Reutiliza la restriccion de `modelos` (no se duplica el conjunto) para
        # rechazar plataformas no-Meta YA al parsear la entrada, no al publicar.
        if v not in PLATAFORMAS_META:
            permitidas = ", ".join(sorted(p.value for p in PLATAFORMAS_META))
            raise ValueError(
                f"Entrada para Meta solo admite {permitidas}; recibido {v.value!r}"
            )
        return v

    def a_borrador(self) -> Borrador:
        """Materializa el `Borrador` (aplica TODA la validacion de `modelos`)."""
        return Borrador(
            plataforma=self.plataforma,
            cuenta=self.cuenta,
            texto=self.texto,
            media=self.media,
            hashtags=self.hashtags,
        )


def _normaliza_a_lista(datos: object) -> list[dict]:
    """Acepta un dict suelto, `{"publicaciones": [...]}` o una lista directa."""
    if isinstance(datos, list):
        return [d for d in datos]
    if isinstance(datos, dict):
        if "publicaciones" in datos:
            pubs = datos["publicaciones"]
            if not isinstance(pubs, list):
                raise ValueError("'publicaciones' debe ser una lista")
            return list(pubs)
        return [datos]
    raise ValueError(
        "Entrada no reconocida: se esperaba un objeto, una lista o "
        "{'publicaciones': [...]}"
    )


def parsear_entradas(datos: object) -> list[EntradaPublicacion]:
    """Convierte datos crudos (dict/list) en `EntradaPublicacion` validadas."""
    return [EntradaPublicacion.model_validate(d) for d in _normaliza_a_lista(datos)]


def cargar_entradas(ruta: str | Path) -> list[EntradaPublicacion]:
    """Carga entradas desde un archivo JSON o TOML (por extension). SIN red."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    sufijo = ruta.suffix.lower()
    if sufijo == ".toml":
        datos: object = tomllib.loads(texto)
    elif sufijo == ".json":
        datos = json.loads(texto)
    else:
        raise ValueError(
            f"Extension no soportada: {ruta.suffix!r}. Usa .json o .toml"
        )
    return parsear_entradas(datos)


# --- resultado del flujo ----------------------------------------------------
@dataclass
class ResultadoFlujo:
    """Lo que produce el flujo: que se encolo y que se enviaria (dry-run).

    `dry_run=True` => `resultados` son ensayos (cero red). `dry_run=False` =>
    `resultados` son envios reales (POST efectivos). `encolados` es el conteo de
    borradores anadidos a la cola.
    """

    dry_run: bool
    encolados: int
    resultados: list[ResultadoPublicacion] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "encolados": self.encolados,
            "resultados": [r.como_dict() for r in self.resultados],
        }


# --- orquestacion -----------------------------------------------------------
def construir_borradores(entradas: list[EntradaPublicacion]) -> list[Borrador]:
    """Materializa los `Borrador`s de cada entrada (valida via `modelos`)."""
    return [e.a_borrador() for e in entradas]


def llenar_cola(
    entradas: list[EntradaPublicacion],
    adaptador: AdaptadorPublicacionMeta,
) -> ColaPublicacion:
    """Construye los borradores y los encola, respetando `publicar_en`."""
    cola = ColaPublicacion(adaptador=adaptador)
    for entrada in entradas:
        cola.encolar(entrada.a_borrador(), publicar_en=entrada.publicar_en)
    return cola


def ejecutar_flujo(
    entradas: list[EntradaPublicacion],
    *,
    adaptador: AdaptadorPublicacionMeta | None = None,
    ahora: datetime | None = None,
    publicar_real: bool = False,
) -> ResultadoFlujo:
    """Orquesta el flujo punta-a-punta. DRY-RUN POR DEFECTO (no toca la red).

    - Construye `Borrador`s desde `entradas` y los encola en una `ColaPublicacion`.
    - Corre `publicar_pendientes(ahora, dry_run=not publicar_real)`.
    - `publicar_real=True` solo publica de verdad si el adaptador tiene token; si
      falta, `cola.publicar_pendientes` lanza `PublicacionNoConfigurada` ANTES de
      tocar la red (misma garantia que `meta.py`).

    El defecto (`publicar_real=False`, adaptador sin token) NUNCA llama a la red.
    """
    adaptador = adaptador or AdaptadorPublicacionMeta(creds={})
    ahora = ahora or datetime.now()

    cola = llenar_cola(entradas, adaptador)
    resultados = cola.publicar_pendientes(ahora, dry_run=not publicar_real)

    return ResultadoFlujo(
        dry_run=not publicar_real,
        encolados=len(cola.items),
        resultados=resultados,
    )


# --- reporte legible --------------------------------------------------------
def render_reporte(resultado: ResultadoFlujo, entradas: list[EntradaPublicacion]) -> str:
    """Reporte humano: que esta encolado y que SE ENVIARIA (payloads dry-run)."""
    out: list[str] = []
    titulo = "DRY-RUN" if resultado.dry_run else "PUBLICACION REAL"
    out.append(f"# Flujo de publicacion — {titulo}")
    if resultado.dry_run:
        out.append("(NADA se ha publicado. Esto es solo lo que se enviaria.)")
    else:
        out.append("(!! PUBLICACION REAL: estas peticiones SE ENVIARON a Meta.)")
    out.append("")
    out.append(f"Encolados: {resultado.encolados}")
    out.append(f"Disparados ahora: {len(resultado.resultados)}")
    out.append("")

    # Resumen por entrada encolada (incluye agendadas que aun no vencen).
    out.append("## Encolado")
    for i, e in enumerate(entradas, 1):
        cuando = e.publicar_en.isoformat() if e.publicar_en else "inmediato"
        b = e.a_borrador()
        out.append(f"{i}. {e.plataforma.value} / {e.cuenta} — {cuando}")
        out.append(f"   texto final: {b.texto_final() or '(vacio)'}")
    out.append("")

    out.append("## Lo que SE ENVIARIA (payloads)")
    if not resultado.resultados:
        out.append("(nada vencido a esta hora)")
    for i, res in enumerate(resultado.resultados, 1):
        out.append(f"### {i}. {res.plataforma.value} / {res.cuenta}")
        for j, pet in enumerate(res.peticiones, 1):
            out.append(f"- Peticion {j}/{len(res.peticiones)} — {pet.paso}")
            out.append(f"  {pet.metodo} {pet.url}")
            out.append(f"  data: {json.dumps(pet.data, ensure_ascii=False)}")
    out.append("")
    if resultado.dry_run:
        out.append("**NADA se ha publicado. Esto es DRY-RUN; no hubo peticiones de red.**")
    else:
        out.append("**PUBLICACION REAL completada. Verifica los ids arriba.**")
    return "\n".join(out)


# --- CLI --------------------------------------------------------------------
def _adaptador_desde_creds(creds_meta: dict | None) -> AdaptadorPublicacionMeta:
    return AdaptadorPublicacionMeta(creds=creds_meta or {})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m keni_metricas.publicacion.flujo",
        description=(
            "Orquesta el flujo de publicacion de copy YA aprobado (DRY-RUN por "
            "defecto; NO publica salvo --publicar-real con confirmacion y token)."
        ),
    )
    ap.add_argument(
        "entrada",
        help="archivo .json o .toml con la(s) publicacion(es) aprobada(s)",
    )
    ap.add_argument(
        "--formato", choices=["json", "texto"], default="texto",
        help="formato del reporte (defecto: texto)",
    )
    ap.add_argument(
        "--publicar-real",
        action="store_true",
        help=(
            "PUBLICAR DE VERDAD (no dry-run). Exige token de Meta configurado y "
            "confirmacion explicita (--si-publicar)."
        ),
    )
    ap.add_argument(
        "--si-publicar",
        action="store_true",
        help="confirma la publicacion real (obligatorio junto a --publicar-real)",
    )
    args = ap.parse_args(argv)

    try:
        entradas = cargar_entradas(args.entrada)
    except FileNotFoundError:
        print(f"Error: no existe el archivo {args.entrada!r}", file=sys.stderr)
        return 2
    except ValidationError as e:
        # B6: pydantic dumpea texto en ingles + URL errors.pydantic.dev. Mostramos
        # solo el mensaje limpio del primer error (ya en espanol via validadores).
        print(f"Error en la entrada: {e.errors()[0]['msg']}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Error en la entrada: {e}", file=sys.stderr)
        return 2

    if not entradas:
        print("Error: la entrada no contiene publicaciones", file=sys.stderr)
        return 2

    # --- gating de seguridad de la publicacion REAL -------------------------
    publicar_real = bool(args.publicar_real)
    if publicar_real:
        if not args.si_publicar:
            print(
                "PUBLICACION REAL bloqueada: --publicar-real exige confirmacion "
                "explicita con --si-publicar. Nada se ha enviado.",
                file=sys.stderr,
            )
            return 2
        # La CLI no carga credenciales: sin token, el adaptador fallara ANTES de
        # tocar la red. Se avisa con claridad aqui.
        print(
            "!! Solicitada PUBLICACION REAL. Esto enviara peticiones a Meta si "
            "hay token configurado.",
            file=sys.stderr,
        )

    # Adaptador SIN credenciales desde la CLI: el camino real exige token y, si
    # falta, `publicar_pendientes` lanza PublicacionNoConfigurada (cero red).
    adaptador = _adaptador_desde_creds(None)
    try:
        resultado = ejecutar_flujo(
            entradas, adaptador=adaptador, publicar_real=publicar_real
        )
    except (ValueError, RuntimeError) as e:
        print(f"Error al ejecutar el flujo: {e}", file=sys.stderr)
        return 1

    if args.formato == "json":
        print(json.dumps(resultado.como_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_reporte(resultado, entradas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
