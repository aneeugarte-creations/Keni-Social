#!/usr/bin/env python3
"""Integridad referencial de la config de CI: todo fichero de test referenciado por un
pipeline (`.woodpecker/*.yml`) o su espejo (`.github/workflows/*.yml`) DEBE existir.

POR QUÉ: los steps de test enumeran ficheros a mano (`consola/tests/test_x.py …`). Cuando un
refactor borra un test sin actualizar el step, `pytest` aborta en *collection* con "file not
found" — y como esos steps suelen llevar filtro `path:`, el fallo queda LATENTE hasta el primer
push que toca esa área, apareciendo en el commit equivocado. Este guard corre SIEMPRE (sin
filtro de path) y falla en el commit que crea la deriva, con el fichero y el yml señalados.

Es el mismo patrón que el contrato de `fronteras` (router↔app), aplicado a la frontera
config-de-CI↔filesystem. PURO: solo lee ficheros, sin BD ni red.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Directorios de definiciones de CI a escanear.
DIRS_CI = (".woodpecker", ".github/workflows")

# Rutas de ficheros de test que un step puede enumerar. Captura paths tipo
# `consola/tests/test_x.py` para cualquier paquete del monorepo.
_RE_RUTA_TEST = re.compile(r"(?:consola|keni-shared|mcp-metricas|mcp-tablero)/tests/[\w/]+\.py")


def referencias() -> dict[str, list[str]]:
    """Mapa `ruta_de_test -> [yml que la referencian]`, recogida de todos los ficheros de CI."""
    encontradas: dict[str, list[str]] = {}
    for d in DIRS_CI:
        base = RAIZ / d
        if not base.is_dir():
            continue
        for yml in sorted([*base.glob("*.yml"), *base.glob("*.yaml")]):
            texto = yml.read_text(encoding="utf-8", errors="replace")
            for ruta in _RE_RUTA_TEST.findall(texto):
                encontradas.setdefault(ruta, []).append(str(yml.relative_to(RAIZ)))
    return encontradas


def huerfanas() -> dict[str, list[str]]:
    """Referencias a ficheros de test que NO existen en el repo."""
    return {ruta: ymls for ruta, ymls in referencias().items() if not (RAIZ / ruta).is_file()}


def main() -> int:
    rotas = huerfanas()
    if not rotas:
        total = len(referencias())
        print(f"lint-ci-refs: OK — {total} referencias de test válidas.")
        return 0
    print("lint-ci-refs: FALLO — referencias de test que ya no existen:", file=sys.stderr)
    for ruta, ymls in sorted(rotas.items()):
        print(f"  - {ruta}  (referenciada en: {', '.join(sorted(set(ymls)))})", file=sys.stderr)
    print(
        "\nBorra esas líneas del step de CI (o restaura el fichero). Mismo patrón que los "
        "arreglos previos de tests-shell.yml.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
