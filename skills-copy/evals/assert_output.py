#!/usr/bin/env python3
"""Aserciones del corredor LOCAL: evalua un output capturado contra su fuente.

Lo usa `run.sh` despues de ejecutar una skill con `claude -p`. Recibe el texto
que produjo el modelo y la(s) fuente(s) de `ejemplos/`, y corre las propiedades
deterministicas de `checks.evaluar_copy`:

  - X y cada tuit del hilo <= 280 (via contar.py)
  - titulo de YouTube <= 70
  - bloque de auto-verificacion presente (✅/⚠️/❌ + veredicto)
  - sin "bandera con escudo"
  - sin numeros/citas ausentes de la fuente

NO llama al modelo: solo analiza texto ya capturado. Sale con codigo 0 si todo
pasa, 1 si algo falla (para que CI/scripts lo detecten — aunque el corredor es
un gate LOCAL, no de CI).

Uso:
    python3 assert_output.py --salida out.txt --fuente ejemplos/cable-1.md \\
        [--fuente ejemplos/cable-2.md] [--ignorar-numero 2026]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evalua un copy generado contra su(s) fuente(s).")
    ap.add_argument("--salida", required=True, help="fichero con el output capturado de la skill")
    ap.add_argument("--fuente", action="append", default=[], required=True,
                    help="fichero de fuente (repetible para varias fuentes)")
    ap.add_argument("--ignorar-numero", action="append", default=[],
                    help="numero a ignorar en el check de fidelidad (p. ej. el anio actual)")
    args = ap.parse_args(argv)

    salida = Path(args.salida).read_text(encoding="utf-8")
    fuente = "\n\n".join(Path(f).read_text(encoding="utf-8") for f in args.fuente)
    ignorar = {checks._digitos(n) for n in args.ignorar_numero if checks._digitos(n)}

    informe = checks.evaluar_copy(salida, fuente, ignorar_numeros=ignorar)

    print(informe.texto())
    if informe.ok:
        print("\nRESULTADO: PASA (todas las propiedades deterministicas se cumplen)")
        return 0
    print(f"\nRESULTADO: FALLA ({len(informe.fallos())} comprobacion(es))")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
