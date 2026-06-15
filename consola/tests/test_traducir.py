"""Tests del módulo dominio/traducir.py. OFFLINE: nunca llama a `claude` real.

Cubre:
  - `traducir_items` con ejecutor falso que devuelve JSON válido.
  - Best-effort: fallo del ejecutor -> devuelve originales.
  - Best-effort: JSON inválido -> devuelve originales.
  - Best-effort: ítem faltante en la respuesta -> devuelve el original para ese ítem.
  - Lista vacía -> devuelve lista vacía.
  - Textos largos se truncan en el payload (no en la respuesta final).
  - El Radar EN VIVO solo etiqueta `idioma` (#desacoplo del back) y nunca llama a
    `traducir_items`. La traducción de historias persistidas la hace el daemon de
    ingesta (tests del daemon, no aquí).
"""

from __future__ import annotations

import json

import pytest

from keni_consola.dominio import traducir

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
    assert traducir.traducir_items([], ejecutor=_ejecutor_ok) == []


def test_traduccion_correcta():
    items = [
        {"id": "t1", "titulo": "Breaking news", "resumen": "Summary here"},
        {"id": "t2", "titulo": "Sport update", "resumen": ""},
    ]
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_ok)
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
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_falla)
    assert len(resultado) == 1
    assert resultado[0]["titulo_es"] == "Original title"
    assert resultado[0]["resumen_es"] == "Original summary"


def test_json_invalido_devuelve_originales():
    items = [{"id": "x2", "titulo": "Hello", "resumen": "World"}]
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_json_invalido)
    assert resultado[0]["titulo_es"] == "Hello"


def test_respuesta_parcial_rellena_con_originales(caplog):
    import logging

    items = [
        {"id": "a", "titulo": "A title", "resumen": "A summary"},
        {"id": "b", "titulo": "B title", "resumen": "B summary"},
    ]
    with caplog.at_level(logging.WARNING, logger="keni_consola.dominio.traducir"):
        resultado = traducir.traducir_items(items, ejecutor=_ejecutor_respuesta_parcial)
    assert len(resultado) == 2
    a_res = next(r for r in resultado if r["id"] == "a")
    b_res = next(r for r in resultado if r["id"] == "b")
    # El primer ítem fue traducido.
    assert a_res["titulo_es"] == "[ES] primero"
    # El segundo ítem no llegó en la respuesta -> devuelve original (fallback razonable)…
    assert b_res["titulo_es"] == "B title"
    assert b_res["resumen_es"] == "B summary"
    # …pero NO silencioso: queda un WARN con el id y la cuenta de ítems sin traducir.
    avisos = [r.message for r in caplog.records if "sin traducción" in r.message]
    assert avisos and "1 de 2" in avisos[0] and "b" in avisos[0]


def test_respuesta_completa_no_deja_warn_de_faltantes(caplog):
    import logging

    items = [{"id": "t1", "titulo": "Breaking news", "resumen": "Summary"}]
    with caplog.at_level(logging.WARNING, logger="keni_consola.dominio.traducir"):
        traducir.traducir_items(items, ejecutor=_ejecutor_ok)
    assert not [r for r in caplog.records if "sin traducción" in r.message]


# --------------------------------------------------------------------------- #
# Truncado de texto largo (el cap por ítem no rompe la funcionalidad)          #
# --------------------------------------------------------------------------- #


def test_texto_largo_no_rompe():
    titulo_largo = "X" * 2000
    resumen_largo = "Y" * 2000
    items = [{"id": "big", "titulo": titulo_largo, "resumen": resumen_largo}]
    # Con el ejecutor que devuelve "[ES] ..." el resultado debe ser válido.
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_ok)
    assert len(resultado) == 1
    assert "titulo_es" in resultado[0]


def test_construir_prompt_inserta_items_y_contrato():
    # La plantilla viene de la Biblioteca (inicial): la lista JSON sustituye al marcador (que
    # NO debe quedar crudo) y se conserva el contrato JSON {"traducciones": [...]}.
    p = traducir._construir_prompt('[{"id":"1","titulo":"Hi"}]')
    assert '[{"id":"1","titulo":"Hi"}]' in p
    assert traducir._MARCA_ITEMS not in p
    assert "traducciones" in p


# --------------------------------------------------------------------------- #
# Regresión SQL: `clusters_extranjeros_sin_traducir` toca la BD REAL (no mock)  #
# La fixture `cliente` (conftest) aísla el entorno y prepara el esquema de BD.   #
# --------------------------------------------------------------------------- #


def _inicializar_cluster_idioma(cid, *, idioma, traducido=0, estado="nuevo"):
    from keni_consola import repos

    repos.upsert_noticia_cluster({
        "id": cid,
        "titulo": f"Cluster {cid}",
        "resumen": "r",
        "marca": "unotv",
        "categoria": "internacional",
        "geo": "US",
        "clave": f"t:{cid}",
        "n_items": 1,
        "n_fuentes": 1,
        "idiomas": [idioma],
        "senal": 10,
        "score": 0.5,
        "breaking": 0,
        "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": "2026-06-05T12:00:00+00:00",
        "estado": estado,
        "idioma": idioma,
        "traducido": traducido,
    })


def test_clusters_extranjeros_sin_traducir_no_revienta_con_like(cliente):  # noqa: ARG001
    """El selector usa `idioma NOT LIKE 'es%%'`: el `%` literal DEBE ir doblado o psycopg casca.

    Este test lo ejercita contra Postgres de verdad (no mocked como los tests del daemon).
    """
    from keni_consola import repos

    _inicializar_cluster_idioma("en1", idioma="en")  # extranjero sin traducir -> candidato
    _inicializar_cluster_idioma("es1", idioma="es")  # español -> excluido por el NOT LIKE 'es%'
    _inicializar_cluster_idioma("en2", idioma="en", traducido=1)  # ya traducido -> excluido

    # Ventana enorme para que el corte temporal no descarte la inicial; min_score bajo.
    candidatos = repos.clusters_extranjeros_sin_traducir(24 * 365 * 100, min_score=0.0, limite=40)
    ids = {c["id"] for c in candidatos}
    assert "en1" in ids
    assert "es1" not in ids  # el `NOT LIKE 'es%'` filtra el español
    assert "en2" not in ids  # ya traducido



# --------------------------------------------------------------------------- #
# Métricas del ejecutor síncrono (acumulador por hilo, para la actividad IA)    #
# --------------------------------------------------------------------------- #


def test_metricas_de_envelope_extrae_y_tolera():
    """Extrae tokens/coste/duración/turnos del envelope de `claude -p --output-format json`;
    campos ausentes o ilegibles se omiten; sin nada útil devuelve None."""
    envelope = {
        "result": "ok",
        "total_cost_usd": 0.0123,
        "duration_ms": 4200,
        "num_turns": 2,
        "usage": {"input_tokens": 100, "output_tokens": 40},
    }
    m = traducir._metricas_de_envelope(envelope)
    assert m == {
        "tokens_in": 100, "tokens_out": 40,
        "total_cost_usd": 0.0123, "duration_ms": 4200, "num_turns": 2,
    }
    assert traducir._metricas_de_envelope({"result": "ok"}) is None
    assert traducir._metricas_de_envelope({"usage": {"input_tokens": "raro"}}) is None
    assert traducir._metricas_de_envelope("no-dict") is None


def test_acumulador_de_metricas_suma_y_resetea():
    """Las llamadas SUMAN en el acumulador del hilo; `tomar_metricas_acumuladas` devuelve la
    suma y RESETEA (la siguiente toma sin llamadas es None)."""
    traducir.tomar_metricas_acumuladas()  # limpia restos de otros tests del hilo
    traducir._acumular_metricas({"tokens_in": 10, "total_cost_usd": 0.01})
    traducir._acumular_metricas({"tokens_in": 5, "tokens_out": 7, "total_cost_usd": 0.02})
    traducir._acumular_metricas(None)  # no-op
    tomadas = traducir.tomar_metricas_acumuladas()
    assert tomadas["tokens_in"] == 15
    assert tomadas["tokens_out"] == 7
    assert tomadas["total_cost_usd"] == pytest.approx(0.03)
    assert traducir.tomar_metricas_acumuladas() is None
