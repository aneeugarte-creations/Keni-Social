"""CLI del harness de evals:  `python -m keni_consola.evals [opciones]`.

Determinista y barato (sin `claude -p`): carga los casos golden, corre los checks deterministas
y emite el reporte. Pensado para correr en CI y en local igual.

Uso:
    python -m keni_consola.evals                 # casos por defecto (consola/evals/casos)
    python -m keni_consola.evals --dir RUTA      # otro directorio de casos
    python -m keni_consola.evals --json          # salida JSON (para tooling)
    python -m keni_consola.evals --verboso       # incluye las dimensiones que pasan
    python -m keni_consola.evals --estricto      # exit!=0 si hay CUALQUIER discrepancia

Códigos de salida:
    0  todos los casos cuadran con su expectativa golden (o sin --estricto)
    1  con --estricto: hay al menos una discrepancia (un caso cambió de dictamen)
    2  error de configuración (casos ilegibles / directorio inexistente)
"""

from __future__ import annotations

import argparse
import json
import sys

from .modelo import ErrorCaso
from .runner import correr_directorio, render_texto


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m keni_consola.evals", description=__doc__)
    parser.add_argument("--dir", default=None, help="directorio de casos (def consola/evals/casos)")
    parser.add_argument("--json", action="store_true", help="salida JSON en vez de texto")
    parser.add_argument("--verboso", action="store_true", help="muestra también las dimensiones OK")
    parser.add_argument(
        "--estricto", action="store_true", help="exit!=0 si hay alguna discrepancia"
    )
    args = parser.parse_args(argv)

    try:
        reporte = correr_directorio(args.dir)
    except ErrorCaso as exc:
        print(f"ERROR de configuración de evals: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(reporte.a_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_texto(reporte, verboso=args.verboso))

    if args.estricto and reporte.discrepancias:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
