"""El guard de integridad referencial de CI (`scripts/lint_ci_refs.py`) también corre en la
suite: todo fichero de test enumerado en un pipeline debe existir. OFFLINE (solo lee ficheros).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]
_SCRIPT = _RAIZ / "scripts" / "lint_ci_refs.py"


def _cargar():
    spec = importlib.util.spec_from_file_location("lint_ci_refs", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_ninguna_referencia_de_test_en_ci_esta_huerfana():
    rotas = _cargar().huerfanas()
    assert rotas == {}, (
        "Pipelines de CI referencian ficheros de test inexistentes "
        f"(bórralos del step o restáuralos): {rotas}"
    )


def test_el_guard_encuentra_referencias():
    # Sanidad: el escáner ve referencias reales (no es un no-op silencioso por un regex roto).
    assert len(_cargar().referencias()) > 0
