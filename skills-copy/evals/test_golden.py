#!/usr/bin/env python3
"""Pruebas de los GOLDEN OUTPUTS de voz/tropicalizacion (`golden/`, #139).

Recorre `golden/manifest.json` y comprueba, por cada copy de referencia, que
cumple las propiedades DETERMINISTAS que un buen copy de esa marca debe cumplir:

  1. Pasa TODAS las propiedades de `checks.evaluar_copy` contra su fuente
     (limites por plataforma, bloque de auto-verificacion, fidelidad de
     numeros/citas, regla de la bandera con escudo).
  2. NO contiene espanolismos ni sus flexiones
     (`tropicalizacion.detecta_flexiones_es_es`).
  3. El manifest esta bien formado (rutas existen, marca canonica, plataforma
     reconocible).

Es CI-safe: Python puro, sin modelo ni red. Los golden son el ancla de
consistencia: si un golden deja de cumplir estas propiedades, algo se degrado.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402
import tropicalizacion as trop  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
MANIFEST = GOLDEN_DIR / "manifest.json"

# Plataformas reconocibles por checks.extraer_secciones (claves normalizadas).
_PLATAFORMAS_VALIDAS = {
    "x", "instagram", "facebook", "tiktok", "youtube", "hilo", "carrusel",
}


def _cargar_manifest() -> list[dict]:
    assert MANIFEST.is_file(), f"falta {MANIFEST}"
    datos = json.loads(MANIFEST.read_text(encoding="utf-8"))
    golden = datos.get("golden")
    assert isinstance(golden, list) and golden, "manifest sin lista 'golden'"
    return golden


def _entradas() -> list[dict]:
    # cacheado a nivel de modulo para no releer en cada test
    global _CACHE
    try:
        return _CACHE  # type: ignore[name-defined]
    except NameError:
        _CACHE = _cargar_manifest()  # type: ignore[name-defined]
        return _CACHE  # type: ignore[name-defined]


# --- el manifest esta bien formado -------------------------------------------

def test_manifest_existe_y_tiene_entradas():
    entradas = _entradas()
    assert len(entradas) >= 3, "se esperan al menos 3 golden (varias marcas)"


def test_manifest_rutas_existen_y_campos_completos():
    errores = []
    for g in _entradas():
        for campo in ("archivo", "marca", "plataforma", "fuente", "voz_notas"):
            if not g.get(campo):
                errores.append(f"{g.get('archivo', '?')}: falta campo '{campo}'")
        if g.get("archivo") and not (GOLDEN_DIR / g["archivo"]).is_file():
            errores.append(f"no existe golden {g['archivo']}")
        if g.get("fuente") and not (GOLDEN_DIR / g["fuente"]).is_file():
            errores.append(f"no existe fuente {g['fuente']}")
    assert not errores, "\n".join(errores)


def test_manifest_marca_canonica_y_plataforma_reconocible():
    errores = []
    for g in _entradas():
        if g["marca"] not in checks.MARCAS_ID_METRICAS:
            errores.append(f"{g['archivo']}: marca '{g['marca']}' no es canonica")
        if g["plataforma"] not in _PLATAFORMAS_VALIDAS:
            errores.append(f"{g['archivo']}: plataforma '{g['plataforma']}' no reconocible")
    assert not errores, "\n".join(errores)


def test_cubre_varias_marcas():
    # el valor del golden es contrastar voces distintas; exige >= 2 marcas.
    marcas = {g["marca"] for g in _entradas()}
    assert len(marcas) >= 2, f"los golden deberian cubrir varias marcas; hay {marcas}"


# --- cada golden cumple las propiedades deterministas ------------------------

def test_golden_pasan_checks_evaluar_copy():
    errores = []
    for g in _entradas():
        salida = (GOLDEN_DIR / g["archivo"]).read_text(encoding="utf-8")
        fuente = (GOLDEN_DIR / g["fuente"]).read_text(encoding="utf-8")
        inf = checks.evaluar_copy(salida, fuente)
        if not inf.ok:
            fallos = "; ".join(r.nombre for r in inf.fallos())
            errores.append(f"{g['archivo']}: falla {fallos}\n{inf.texto()}")
    assert not errores, "\n\n".join(errores)


def test_golden_sin_espanolismos_ni_flexiones():
    errores = []
    for g in _entradas():
        salida = (GOLDEN_DIR / g["archivo"]).read_text(encoding="utf-8")
        hallazgos = trop.detecta_flexiones_es_es(salida)
        if hallazgos:
            detalle = ", ".join(f"{h.forma} (lema {h.lema})" for h in hallazgos)
            errores.append(f"{g['archivo']}: espanolismos -> {detalle}")
    assert not errores, "\n".join(errores)


def test_golden_traen_bloque_de_verificacion():
    errores = []
    for g in _entradas():
        salida = (GOLDEN_DIR / g["archivo"]).read_text(encoding="utf-8")
        if not checks.tiene_bloque_verificacion(salida):
            errores.append(f"{g['archivo']}: sin bloque de auto-verificacion")
    assert not errores, "\n".join(errores)


def test_golden_seccion_de_su_plataforma_es_detectable():
    # el copy debe traer la seccion de la plataforma que declara en el manifest,
    # para que el contrato golden<->plataforma sea verificable.
    errores = []
    for g in _entradas():
        salida = (GOLDEN_DIR / g["archivo"]).read_text(encoding="utf-8")
        secciones = checks.extraer_secciones(salida)
        if g["plataforma"] not in secciones:
            errores.append(
                f"{g['archivo']}: no se detecta seccion '{g['plataforma']}' "
                f"(detectadas: {sorted(secciones)})"
            )
    assert not errores, "\n".join(errores)


# --- mini-runner sin pytest --------------------------------------------------

def _main() -> int:
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    fallos = 0
    for f in funcs:
        try:
            f()
            print(f"PASS {f.__name__}")
        except AssertionError as e:
            fallos += 1
            print(f"FAIL {f.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"ERROR {f.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(funcs) - fallos}/{len(funcs)} pruebas OK")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_main())
