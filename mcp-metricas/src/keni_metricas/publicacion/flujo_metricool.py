"""Flujo de PROGRAMACION via Metricool para copy YA aprobado (multi-red).

╔══════════════════════════════════════════════════════════════════════════╗
║  SEGURIDAD — ORQUESTA PUBLICACION. LEER ANTES DE TOCAR.                     ║
║                                                                            ║
║  Este modulo NO duplica la logica del adaptador: solo la ORQUESTA. Toma    ║
║  borradores ya aprobados y corre `programar(dry_run=True)` por defecto.    ║
║                                                                            ║
║  DRY-RUN POR DEFECTO. El camino por defecto NUNCA toca la red: produce un  ║
║  REPORTE de lo que se enviaria (los cuerpos `ScheduledPost`). La           ║
║  programacion REAL solo ocurre si se pide explicitamente (`publicar_real`) ║
║  Y hay credenciales de Metricool en el adaptador; la CLI exige ademas      ║
║  doble confirmacion (`--publicar-real --si-publicar`). Espeja `flujo.py`.  ║
╚══════════════════════════════════════════════════════════════════════════╝

Entrada (`.json` o `.toml`): una o varias publicaciones aprobadas. Formato del
dict / JSON (objeto suelto, lista, o `{"publicaciones": [...]}`):

    {
      "redes": ["facebook", "instagram"],     # 1+ redes destino
      "texto": "Copy aprobado",                # cuerpo (sin hashtags)
      "media": [{"tipo": "imagen", "url": "https://e/x.jpg", "descripcion": "alt"}],
      "hashtags": ["deporte", "futbol"],        # opcional, sin '#'
      "publicar_en": "2026-05-30T18:00:00",     # opcional; None => ahora
      "timezone": "America/Mexico_City",        # opcional
      "auto_publish": true,                      # opcional (defecto true)
      "borrador": false                          # opcional; true => DRAFT en Metricool
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .metricool import (
    AdaptadorPublicacionMetricool,
    BorradorMetricool,
    ResultadoProgramacion,
)


def _normaliza_a_lista(datos: object) -> list[dict]:
    """Acepta un dict suelto, `{"publicaciones": [...]}` o una lista directa."""
    if isinstance(datos, list):
        return list(datos)
    if isinstance(datos, dict):
        if "publicaciones" in datos:
            pubs = datos["publicaciones"]
            if not isinstance(pubs, list):
                raise ValueError("'publicaciones' debe ser una lista")
            return list(pubs)
        return [datos]
    raise ValueError("Entrada no reconocida: se esperaba un objeto, una lista o {'publicaciones': [...]}")


def parsear_borradores(datos: object) -> list[BorradorMetricool]:
    """Convierte datos crudos (dict/list) en `BorradorMetricool` validados."""
    return [BorradorMetricool.model_validate(d) for d in _normaliza_a_lista(datos)]


def cargar_borradores(ruta: str | Path) -> list[BorradorMetricool]:
    """Carga borradores desde un archivo JSON o TOML (por extension). SIN red."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    sufijo = ruta.suffix.lower()
    if sufijo == ".toml":
        datos: object = tomllib.loads(texto)
    elif sufijo == ".json":
        datos = json.loads(texto)
    else:
        raise ValueError(f"Extension no soportada: {ruta.suffix!r}. Usa .json o .toml")
    return parsear_borradores(datos)


def ejecutar_flujo(
    borradores: list[BorradorMetricool],
    *,
    adaptador: AdaptadorPublicacionMetricool | None = None,
    ahora: datetime | None = None,
    publicar_real: bool = False,
) -> list[ResultadoProgramacion]:
    """Orquesta la programacion punta-a-punta. DRY-RUN POR DEFECTO (no toca la red).

    `publicar_real=True` solo programa de verdad si el adaptador tiene credenciales;
    si faltan, `programar` lanza `ProgramacionNoConfigurada` ANTES de tocar la red.
    """
    adaptador = adaptador or AdaptadorPublicacionMetricool(creds={})
    return [
        adaptador.programar(b, dry_run=not publicar_real, ahora=ahora) for b in borradores
    ]


def render_reporte(resultados: list[ResultadoProgramacion]) -> str:
    """Reporte humano: que se enviaria (cuerpos `ScheduledPost`) o que se envio."""
    dry = all(r.dry_run for r in resultados) if resultados else True
    out: list[str] = []
    out.append(f"# Flujo de programacion (Metricool) — {'DRY-RUN' if dry else 'PROGRAMACION REAL'}")
    out.append(
        "(NADA se ha programado. Esto es solo lo que se enviaria.)"
        if dry
        else "(!! REAL: estas peticiones SE ENVIARON al scheduler de Metricool.)"
    )
    out.append("")
    out.append(f"Borradores: {len(resultados)}")
    out.append("")
    for i, res in enumerate(resultados, 1):
        cuando = res.peticion.body.get("publicationDate", {}).get("dateTime", "?")
        out.append(f"## {i}. redes: {', '.join(res.redes)} — {cuando}")
        out.append(f"  {res.peticion.metodo} {res.peticion.url}")
        out.append(f"  params: {json.dumps(res.peticion.params, ensure_ascii=False)}")
        out.append(f"  body: {json.dumps(res.peticion.body, ensure_ascii=False)}")
        if not res.dry_run:
            out.append(f"  -> id_post: {res.id_post}  estados: {json.dumps(res.estados, ensure_ascii=False)}")
        out.append("")
    out.append(
        "**NADA se ha programado. Esto es DRY-RUN; no hubo peticiones de red.**"
        if dry
        else "**PROGRAMACION REAL completada. Verifica los ids/estados arriba.**"
    )
    return "\n".join(out)


# --- CLI --------------------------------------------------------------------
def _adaptador_desde_env() -> AdaptadorPublicacionMetricool:
    """Credenciales (una sola identidad) desde el entorno, para el camino real de la CLI.

    El camino programatico (Consola) resuelve credenciales POR MARCA con
    `config.MetricoolConfig.marcas_configuradas()`; la CLI usa una sola identidad
    via env para operaciones puntuales. Sin env, el camino real falla seguro.
    """
    return AdaptadorPublicacionMetricool(
        creds={
            "user_token": os.environ.get("METRICOOL_USER_TOKEN", ""),
            "user_id": os.environ.get("METRICOOL_USER_ID", ""),
            "blog_id": os.environ.get("METRICOOL_BLOG_ID", ""),
        }
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m keni_metricas.publicacion.flujo_metricool",
        description=(
            "Programa/publica copy YA aprobado via Metricool (DRY-RUN por defecto; "
            "NO publica salvo --publicar-real --si-publicar con credenciales en el entorno)."
        ),
    )
    ap.add_argument("entrada", help="archivo .json o .toml con la(s) publicacion(es) aprobada(s)")
    ap.add_argument("--formato", choices=["json", "texto"], default="texto", help="formato del reporte")
    ap.add_argument(
        "--publicar-real",
        action="store_true",
        help="PROGRAMAR DE VERDAD (no dry-run). Exige credenciales en el entorno y --si-publicar.",
    )
    ap.add_argument(
        "--si-publicar",
        action="store_true",
        help="confirma la programacion real (obligatorio junto a --publicar-real)",
    )
    args = ap.parse_args(argv)

    try:
        borradores = cargar_borradores(args.entrada)
    except FileNotFoundError:
        print(f"Error: no existe el archivo {args.entrada!r}", file=sys.stderr)
        return 2
    except ValidationError as e:
        print(f"Error en la entrada: {e.errors()[0]['msg']}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Error en la entrada: {e}", file=sys.stderr)
        return 2

    if not borradores:
        print("Error: la entrada no contiene publicaciones", file=sys.stderr)
        return 2

    publicar_real = bool(args.publicar_real)
    if publicar_real:
        if not args.si_publicar:
            print(
                "PROGRAMACION REAL bloqueada: --publicar-real exige confirmacion explicita "
                "con --si-publicar. Nada se ha enviado.",
                file=sys.stderr,
            )
            return 2
        print(
            "!! Solicitada PROGRAMACION REAL. Esto enviara peticiones a Metricool si hay "
            "credenciales (METRICOOL_USER_TOKEN/USER_ID/BLOG_ID) en el entorno.",
            file=sys.stderr,
        )

    adaptador = _adaptador_desde_env() if publicar_real else AdaptadorPublicacionMetricool(creds={})
    try:
        resultados = ejecutar_flujo(borradores, adaptador=adaptador, publicar_real=publicar_real)
    except (ValueError, RuntimeError) as e:
        print(f"Error al ejecutar el flujo: {e}", file=sys.stderr)
        return 1

    if args.formato == "json":
        print(json.dumps([r.como_dict() for r in resultados], ensure_ascii=False, indent=2))
    else:
        print(render_reporte(resultados))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
