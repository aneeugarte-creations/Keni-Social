"""Tests del módulo dominio/traduccion.py. OFFLINE: nunca llama a `claude` real.

Cubre:
  - `traducir_items` con ejecutor falso que devuelve JSON válido.
  - Best-effort: fallo del ejecutor -> devuelve originales.
  - Best-effort: JSON inválido -> devuelve originales.
  - Best-effort: ítem faltante en la respuesta -> devuelve el original para ese ítem.
  - Lista vacía -> devuelve lista vacía.
  - Textos largos se truncan en el payload (no en la respuesta final).
  - El Radar EN VIVO ya NO traduce (#desacoplo del back): solo etiqueta `idioma` y nunca
    llama a `traducir_items`. La traducción de historias persistidas la hace el daemon de
    ingesta (tests del daemon, no aquí).
"""

from __future__ import annotations

import json

from keni_consola.dominio import traduccion

# --------------------------------------------------------------------------- #
# Ejecutores falsos                                                             #
# --------------------------------------------------------------------------- #


def _ejecutor_ok(prompt: str, dir_permitido: str) -> str:
    """Ejecutor que extrae los ids del prompt y devuelve traducciones al español."""
    # Extrae el JSON de ítems del prompt para construir una respuesta coherente.
    import re

    # Aísla la lista REAL de ítems (va tras "Lista de ítems:"); el prompt también
    # contiene un ejemplo con corchetes en las instrucciones que confundía al regex.
    cola = prompt.partition("Lista de ítems:")[2] or prompt
    m = re.search(r"\[.*\]", cola, re.DOTALL)
    if not m:
        return json.dumps({"traducciones": []})
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"traducciones": []})
    traducciones = [
        {
            "id": it["id"],
            "titulo_es": f"[ES] {it['titulo']}",
            "resumen_es": f"[ES] {it.get('resumen', '')}",
        }
        for it in items
    ]
    return json.dumps({"traducciones": traducciones})


def _ejecutor_falla(prompt: str, dir_permitido: str) -> str:
    raise RuntimeError("Fallo simulado del subproceso claude")


def _ejecutor_json_invalido(prompt: str, dir_permitido: str) -> str:
    return "esto no es JSON para nada"


def _ejecutor_respuesta_parcial(prompt: str, dir_permitido: str) -> str:
    """Solo devuelve traducción para el primer ítem."""
    import re

    # Aísla la lista REAL de ítems (va tras "Lista de ítems:"); el prompt también
    # contiene un ejemplo con corchetes en las instrucciones que confundía al regex.
    cola = prompt.partition("Lista de ítems:")[2] or prompt
    m = re.search(r"\[.*\]", cola, re.DOTALL)
    if not m:
        return json.dumps({"traducciones": []})
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"traducciones": []})
    if not items:
        return json.dumps({"traducciones": []})
    primer = items[0]
    return json.dumps({
        "traducciones": [{"id": primer["id"], "titulo_es": "[ES] primero", "resumen_es": ""}]
    })


# --------------------------------------------------------------------------- #
# Casos base                                                                    #
# --------------------------------------------------------------------------- #


def test_lista_vacia_devuelve_lista_vacia():
    assert traduccion.traducir_items([], ejecutor=_ejecutor_ok) == []


def test_traduccion_correcta():
    items = [
        {"id": "t1", "titulo": "Breaking news", "resumen": "Summary here"},
        {"id": "t2", "titulo": "Sport update", "resumen": ""},
    ]
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_ok)
    assert len(resultado) == 2
    ids = {r["id"] for r in resultado}
    assert ids == {"t1", "t2"}
    # El ejecutor fake añade "[ES]" al principio.
    t1 = next(r for r in resultado if r["id"] == "t1")
    assert "[ES]" in t1["titulo_es"]
    assert "titulo_es" in t1
    assert "resumen_es" in t1


# --------------------------------------------------------------------------- #
# Best-effort ante fallos                                                       #
# --------------------------------------------------------------------------- #


def test_fallo_ejecutor_devuelve_originales():
    items = [
        {"id": "x1", "titulo": "Original title", "resumen": "Original summary"},
    ]
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_falla)
    assert len(resultado) == 1
    assert resultado[0]["titulo_es"] == "Original title"
    assert resultado[0]["resumen_es"] == "Original summary"


def test_json_invalido_devuelve_originales():
    items = [{"id": "x2", "titulo": "Hello", "resumen": "World"}]
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_json_invalido)
    assert resultado[0]["titulo_es"] == "Hello"


def test_respuesta_parcial_rellena_con_originales():
    items = [
        {"id": "a", "titulo": "A title", "resumen": "A summary"},
        {"id": "b", "titulo": "B title", "resumen": "B summary"},
    ]
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_respuesta_parcial)
    assert len(resultado) == 2
    a_res = next(r for r in resultado if r["id"] == "a")
    b_res = next(r for r in resultado if r["id"] == "b")
    # El primer ítem fue traducido.
    assert a_res["titulo_es"] == "[ES] primero"
    # El segundo ítem no llegó en la respuesta -> devuelve original.
    assert b_res["titulo_es"] == "B title"
    assert b_res["resumen_es"] == "B summary"


# --------------------------------------------------------------------------- #
# Truncado de texto largo (el cap por ítem no rompe la funcionalidad)          #
# --------------------------------------------------------------------------- #


def test_texto_largo_no_rompe():
    titulo_largo = "X" * 2000
    resumen_largo = "Y" * 2000
    items = [{"id": "big", "titulo": titulo_largo, "resumen": resumen_largo}]
    # Con el ejecutor que devuelve "[ES] ..." el resultado debe ser válido.
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_ok)
    assert len(resultado) == 1
    assert "titulo_es" in resultado[0]


def test_construir_prompt_inserta_items_y_contrato():
    # La plantilla viene de la Biblioteca (semilla): la lista JSON sustituye al marcador (que
    # NO debe quedar crudo) y se conserva el contrato JSON {"traducciones": [...]}.
    p = traduccion._construir_prompt('[{"id":"1","titulo":"Hi"}]')
    assert '[{"id":"1","titulo":"Hi"}]' in p
    assert traduccion._MARCA_ITEMS not in p
    assert "traducciones" in p

