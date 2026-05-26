"""CLI de export del esquema: `python -m keni_consola.esquema_api`.

Imprime por stdout el JSON Schema del subconjunto estable del contrato `/api/*`.
Lo invoca el frontend desde `npm run gen:types` (ver `frontend/scripts/gen-types.mjs`)
para generar `src/types.gen.ts`. Solo escribe en stdout: nada de estado ni I/O.

Opcional: `--salida RUTA` escribe el JSON a un archivo en vez de a stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

from .schema import esquema_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="keni_consola.esquema_api",
        description="Emite el JSON Schema del subconjunto estable del contrato /api/*.",
    )
    parser.add_argument(
        "--salida",
        metavar="RUTA",
        default=None,
        help="Archivo destino del JSON (por defecto, stdout).",
    )
    args = parser.parse_args(argv)

    texto = json.dumps(esquema_json(), ensure_ascii=False, indent=2, sort_keys=False)
    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as fh:
            fh.write(texto + "\n")
    else:
        sys.stdout.write(texto + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
