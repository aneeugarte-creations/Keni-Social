#!/usr/bin/env python3
"""Chequeos ESTATICOS de skills-copy (CI-safe).

No usan el modelo ni la red ni whisper: solo leen el repo y prueban Python puro.
Pensados para correr en un runner limpio de GitHub Actions con solo Python +
pytest. Si no hay pytest disponible, este fichero tambien funciona como script:

    python3 skills-copy/evals/test_static.py

(usa un mini-runner al final que recorre las funciones `test_*`).

Cubren:
  1. Cada SKILL.md tiene el frontmatter obligatorio (name, description, allowed-tools).
  2. contexto-editorial tiene los ficheros esperados (plataformas, tropicalizacion,
     reglas-legales, las 5 marcas, voces/_plantilla).
  3. Unit test de contar.py: cuenta code points (acentos y emojis = 1 cada uno).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402  (tras ajustar sys.path)


# ---------------------------------------------------------------------------
# 1) Frontmatter de cada SKILL.md
# ---------------------------------------------------------------------------

# Skills que DEBEN existir en el repo. Al crecer la suite, registramos aquí las
# nuevas conforme aterrizan en main.
ESPERADAS = {
    "copy-desde-nota",
    "clip-a-copy",
    "resumen-tendencia",
    "nota-a-formato",
    "publica-preview",
    "revisa-imagen",
    "responde-comentarios",
    "calendario-editorial",
    "nota-a-hilo",
    "brief-matutino",
    "termometro-mundial",
}


def test_skills_existen():
    skills = checks.listar_skills()
    nombres = {p.parent.name for p in skills}
    faltan = ESPERADAS - nombres
    assert not faltan, f"faltan SKILL.md de: {sorted(faltan)}"


def test_frontmatter_obligatorio_en_cada_skill():
    skills = checks.listar_skills()
    assert skills, "no se encontro ningun SKILL.md"
    errores = []
    for ruta in skills:
        texto = ruta.read_text(encoding="utf-8")
        faltan = checks.faltan_claves_frontmatter(texto)
        if faltan:
            errores.append(f"{ruta.parent.name}/SKILL.md le faltan claves: {faltan}")
    assert not errores, "\n".join(errores)


def test_name_del_frontmatter_coincide_con_carpeta():
    # el campo `name` debe coincidir con el nombre de la carpeta de la skill
    errores = []
    for ruta in checks.listar_skills():
        fm = checks.parsear_frontmatter(ruta.read_text(encoding="utf-8"))
        assert fm is not None, f"{ruta} sin frontmatter"
        if fm.get("name") != ruta.parent.name:
            errores.append(f"{ruta.parent.name}: name='{fm.get('name')}'")
    assert not errores, "name no coincide con la carpeta: " + "; ".join(errores)


def test_keni_yaml_parsea_como_mapa():
    # Cada `keni.yaml` (metadatos para la Consola) DEBE parsear como un mapa con
    # `nombre`. Un YAML inválido (p.ej. un ': ' sin comillas en un texto) hace que el
    # catálogo lo SALTE en silencio y la skill no aparezca en la consola: este test lo
    # caza. Requiere PyYAML; sin él (mini-runner pelado) el chequeo se omite (lo cubre
    # CI, que instala pyyaml, y los tests de la consola).
    try:
        import yaml
    except ImportError:
        return
    errores = []
    for ruta in checks.SKILLS_DIR.glob("*/keni.yaml"):
        try:
            datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errores.append(f"{ruta.parent.name}: no parsea ({e})")
            continue
        if not isinstance(datos, dict) or not datos.get("nombre"):
            errores.append(f"{ruta.parent.name}: keni.yaml no es un mapa con 'nombre'")
    assert not errores, "keni.yaml inválido:\n" + "\n".join(errores)


# ---------------------------------------------------------------------------
# 2) Ficheros de contexto-editorial
# ---------------------------------------------------------------------------

def test_contexto_editorial_completo():
    faltan = checks.ficheros_contexto_faltantes()
    assert not faltan, f"faltan ficheros en contexto-editorial: {faltan}"


# ---------------------------------------------------------------------------
# 3) Unit test de contar.py
# ---------------------------------------------------------------------------

def _contar_via_modulo(texto: str) -> int:
    """Replica de la logica de contar.py (lo que el modulo checks expone)."""
    return checks.contar_code_points(texto)


def _contar_via_subproceso(texto: str) -> int:
    """Invoca contar.py de verdad por stdin (como hace la skill con heredoc)."""
    proc = subprocess.run(
        [sys.executable, str(checks.CONTAR_PY)],
        input=texto,
        capture_output=True,
        text=True,
        check=True,
    )
    return int(proc.stdout.strip())


def test_contar_existe():
    assert checks.CONTAR_PY.is_file(), f"no existe {checks.CONTAR_PY}"


def test_contar_ascii_simple():
    assert _contar_via_modulo("hola") == 4
    assert _contar_via_subproceso("hola") == 4


def test_contar_acentos_cuentan_uno():
    # "café" = c, a, f, é  -> 4 code points (no 5)
    assert _contar_via_modulo("café") == 4
    assert _contar_via_subproceso("café") == 4
    # mezcla de acentos y ñ
    assert _contar_via_modulo("niño áéíóú") == 10
    assert _contar_via_subproceso("niño áéíóú") == 10


def test_contar_emoji_cuenta_uno():
    # un emoji BMP-extendido = 1 code point
    assert _contar_via_modulo("hola 😀") == 6
    assert _contar_via_subproceso("hola 😀") == 6


def test_contar_quita_salto_final_del_heredoc():
    # contar.py quita UN salto de linea final (el que mete el heredoc)
    assert _contar_via_modulo("hola\n") == 4
    assert _contar_via_subproceso("hola\n") == 4
    # pero un salto interno SI cuenta
    assert _contar_via_modulo("a\nb") == 3
    assert _contar_via_subproceso("a\nb") == 3


def test_contar_limite_x_exacto():
    # exactamente 280 'a' -> 280
    s = "a" * 280
    assert _contar_via_modulo(s) == 280
    assert _contar_via_subproceso(s) == 280


# ---------------------------------------------------------------------------
# mini-runner para correr sin pytest (`python3 test_static.py`)
# ---------------------------------------------------------------------------

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
