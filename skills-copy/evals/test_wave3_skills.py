#!/usr/bin/env python3
"""Chequeos estáticos de Wave 3 skills — #105/#106/#107/#108.

Verifica el estado de las cuatro skills tocadas en Ola 3 de skills-copy:
  - #106 publica-meta: existe, nombre alineado, dry-run documentado, grupo produccion.
  - #107 responde-comentarios: fuera de experimental, scope acotado (sin lives).
  - #108 calendario-editorial: fuera de experimental, soporta modo evergreen.
  - #105 voces-marca: nueva skill, entradas/salidas claras.

CI-safe: solo Python puro + PyYAML; sin modelo ni red.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402

import yaml  # PyYAML (requerido; CI lo instala)

SKILLS_DIR = checks.SKILLS_DIR


def _leer_skill_md(nombre: str) -> str:
    ruta = SKILLS_DIR / nombre / "SKILL.md"
    assert ruta.is_file(), f"SKILL.md no existe: {ruta}"
    return ruta.read_text(encoding="utf-8")


def _leer_keni_yaml(nombre: str) -> dict:
    ruta = SKILLS_DIR / nombre / "keni.yaml"
    assert ruta.is_file(), f"keni.yaml no existe: {ruta}"
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# #106 — publica-meta
# ---------------------------------------------------------------------------

def test_publica_meta_existe():
    """La skill publica-meta debe existir (issue #106)."""
    ruta = SKILLS_DIR / "publica-meta" / "SKILL.md"
    assert ruta.is_file(), "publica-meta/SKILL.md no existe (#106)"


def test_publica_meta_name_en_frontmatter():
    """El campo name del frontmatter debe ser 'publica-meta'."""
    texto = _leer_skill_md("publica-meta")
    fm = checks.parsear_frontmatter(texto)
    assert fm is not None, "publica-meta/SKILL.md sin frontmatter"
    assert fm.get("name") == "publica-meta", (
        f"name='{fm.get('name')}' != 'publica-meta' (#106)"
    )


def test_publica_meta_keni_yaml_nombre():
    """keni.yaml de publica-meta debe tener nombre con 'Meta' (no 'preview')."""
    datos = _leer_keni_yaml("publica-meta")
    nombre = datos.get("nombre", "")
    assert "Meta" in nombre or "meta" in nombre.lower(), (
        f"keni.yaml nombre='{nombre}' no alineado con 'Meta' (#106)"
    )


def test_publica_meta_keni_yaml_grupo_no_experimental():
    """publica-meta debe salir de experimentales (#106)."""
    datos = _leer_keni_yaml("publica-meta")
    assert datos.get("grupo", "") != "experimentales", (
        "publica-meta sigue en grupo 'experimentales' (#106)"
    )


def test_publica_meta_dry_run_documentado():
    """SKILL.md de publica-meta debe documentar el modo DRY-RUN."""
    texto = _leer_skill_md("publica-meta")
    assert "DRY-RUN" in texto or "dry-run" in texto.lower(), (
        "publica-meta no documenta DRY-RUN (#106)"
    )


def test_publica_meta_no_publica_de_verdad():
    """SKILL.md de publica-meta debe afirmar que NO publica."""
    texto = _leer_skill_md("publica-meta").upper()
    assert "NO PUBLICA" in texto or "NADA SE HA PUBLICADO" in texto, (
        "publica-meta no afirma explícitamente que no publica (#106)"
    )


def test_publica_meta_es_skill_de_copy():
    """publica-meta debe cumplir el contrato de skills de copy (veredicto+contexto)."""
    texto = _leer_skill_md("publica-meta")
    assert checks.produce_copy_con_veredicto(texto), (
        "publica-meta no cumple el contrato de skill de copy (#106)"
    )


# ---------------------------------------------------------------------------
# #107 — responde-comentarios (fuera de experimental, sin lives)
# ---------------------------------------------------------------------------

def test_responde_comentarios_fuera_de_experimental():
    """responde-comentarios NO debe estar en grupo 'experimentales' (#107)."""
    datos = _leer_keni_yaml("responde-comentarios")
    assert datos.get("grupo", "") != "experimentales", (
        "responde-comentarios sigue en 'experimentales' (#107)"
    )


def test_responde_comentarios_sin_etiqueta_experimental_en_skill_md():
    """SKILL.md de responde-comentarios no debe tener la marca Experimental (#107)."""
    texto = _leer_skill_md("responde-comentarios")
    # La línea "> **Experimental:**" es la marca original que debemos haber quitado
    assert "> **Experimental:**" not in texto, (
        "responde-comentarios aún tiene la marca '> **Experimental:**' (#107)"
    )


def test_responde_comentarios_scope_sin_lives():
    """SKILL.md de responde-comentarios debe declarar que NO cubre lives (#107)."""
    texto = _leer_skill_md("responde-comentarios").lower()
    # Debe mencionar que no cubre lives/transmisiones en vivo
    tiene_no_lives = (
        "no modera" in texto
        or "no cubre" in texto
        or "sin lives" in texto
        or "transmisiones en vivo" in texto
    )
    assert tiene_no_lives, (
        "responde-comentarios no aclara que el scope excluye lives/transmisiones (#107)"
    )


def test_responde_comentarios_frontmatter_valido():
    """responde-comentarios debe tener frontmatter con name, description, allowed-tools."""
    texto = _leer_skill_md("responde-comentarios")
    faltan = checks.faltan_claves_frontmatter(texto)
    assert not faltan, f"responde-comentarios frontmatter falta: {faltan} (#107)"


# ---------------------------------------------------------------------------
# #108 — calendario-editorial (fuera de experimental, soporta evergreen)
# ---------------------------------------------------------------------------

def test_calendario_editorial_fuera_de_experimental():
    """calendario-editorial NO debe estar en grupo 'experimentales' (#108)."""
    datos = _leer_keni_yaml("calendario-editorial")
    assert datos.get("grupo", "") != "experimentales", (
        "calendario-editorial sigue en 'experimentales' (#108)"
    )


def test_calendario_editorial_sin_etiqueta_experimental():
    """SKILL.md de calendario-editorial no debe tener la marca Experimental (#108)."""
    texto = _leer_skill_md("calendario-editorial")
    assert "> **Experimental:**" not in texto, (
        "calendario-editorial aún tiene la marca '> **Experimental:**' (#108)"
    )


def test_calendario_editorial_soporta_evergreen():
    """SKILL.md de calendario-editorial debe documentar el modo evergreen/anual (#108)."""
    texto = _leer_skill_md("calendario-editorial").lower()
    tiene_evergreen = "evergreen" in texto or "anual" in texto
    assert tiene_evergreen, (
        "calendario-editorial no documenta el modo evergreen/anual (#108)"
    )


def test_calendario_editorial_efemerides():
    """SKILL.md de calendario-editorial debe mencionar efemérides (#108)."""
    texto = _leer_skill_md("calendario-editorial").lower()
    # efemér con o sin acento (normalización básica)
    tiene_efemerides = "efem" in texto
    assert tiene_efemerides, (
        "calendario-editorial no menciona efemérides en el modo evergreen (#108)"
    )


def test_calendario_editorial_keni_yaml_campo_ventana():
    """keni.yaml de calendario-editorial debe tener campo 'ventana' (#108)."""
    datos = _leer_keni_yaml("calendario-editorial")
    ids_campos = [c.get("id") for c in datos.get("campos", [])]
    assert "ventana" in ids_campos, (
        f"calendario-editorial/keni.yaml no tiene campo 'ventana': {ids_campos} (#108)"
    )


def test_calendario_editorial_frontmatter_valido():
    """calendario-editorial debe tener frontmatter con name, description, allowed-tools."""
    texto = _leer_skill_md("calendario-editorial")
    faltan = checks.faltan_claves_frontmatter(texto)
    assert not faltan, f"calendario-editorial frontmatter falta: {faltan} (#108)"


# ---------------------------------------------------------------------------
# #105 — voces-marca (nueva skill)
# ---------------------------------------------------------------------------

def test_voces_marca_existe():
    """La skill voces-marca debe existir (issue #105)."""
    ruta = SKILLS_DIR / "voces-marca" / "SKILL.md"
    assert ruta.is_file(), "voces-marca/SKILL.md no existe (#105)"


def test_voces_marca_frontmatter_valido():
    """voces-marca debe tener frontmatter con name, description, allowed-tools."""
    texto = _leer_skill_md("voces-marca")
    faltan = checks.faltan_claves_frontmatter(texto)
    assert not faltan, f"voces-marca frontmatter falta: {faltan} (#105)"


def test_voces_marca_name_en_frontmatter():
    """El campo name del frontmatter debe ser 'voces-marca'."""
    texto = _leer_skill_md("voces-marca")
    fm = checks.parsear_frontmatter(texto)
    assert fm is not None
    assert fm.get("name") == "voces-marca", (
        f"name='{fm.get('name')}' != 'voces-marca' (#105)"
    )


def test_voces_marca_keni_yaml_valido():
    """keni.yaml de voces-marca debe parsear y tener 'nombre'."""
    datos = _leer_keni_yaml("voces-marca")
    assert datos.get("nombre"), "voces-marca/keni.yaml sin 'nombre' (#105)"


def test_voces_marca_carga_plantilla():
    """voces-marca debe referenciar _plantilla.md del directorio de voces."""
    texto = _leer_skill_md("voces-marca")
    assert "_plantilla.md" in texto or "voces/_plantilla" in texto, (
        "voces-marca no referencia _plantilla.md (#105)"
    )


def test_voces_marca_genera_en_contexto_editorial_voces():
    """voces-marca debe documentar que guarda en contexto-editorial/voces/."""
    texto = _leer_skill_md("voces-marca")
    assert "contexto-editorial/voces/" in texto, (
        "voces-marca no menciona contexto-editorial/voces/ como destino (#105)"
    )


def test_voces_marca_campo_historial_en_keni_yaml():
    """keni.yaml de voces-marca debe tener campo 'historial'."""
    datos = _leer_keni_yaml("voces-marca")
    ids_campos = [c.get("id") for c in datos.get("campos", [])]
    assert "historial" in ids_campos, (
        f"voces-marca/keni.yaml no tiene campo 'historial': {ids_campos} (#105)"
    )


def test_voces_marca_campo_nombre_voz_en_keni_yaml():
    """keni.yaml de voces-marca debe tener campo 'nombre_voz' (slug)."""
    datos = _leer_keni_yaml("voces-marca")
    ids_campos = [c.get("id") for c in datos.get("campos", [])]
    assert "nombre_voz" in ids_campos, (
        f"voces-marca/keni.yaml no tiene campo 'nombre_voz': {ids_campos} (#105)"
    )


def test_voces_marca_no_inventa_voz():
    """voces-marca debe advertir que no inventa rasgos sin evidencia (#105)."""
    texto = _leer_skill_md("voces-marca").lower()
    tiene_aviso = (
        "no inventes" in texto
        or "nunca inventes" in texto
        or "sin evidencia" in texto
        or "insuficiente" in texto
    )
    assert tiene_aviso, (
        "voces-marca no documenta que no debe inventar rasgos sin evidencia (#105)"
    )


# ---------------------------------------------------------------------------
# mini-runner para correr sin pytest (`python3 test_wave3_skills.py`)
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
