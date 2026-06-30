"""Mapeo `tipo`→etapa/pestaña del desglose de economía (`db_jobs`, puro, sin BD).

Fija la corrección de atribución: los jobs `prompt` (audio + biblioteca) caen en Herramientas con
nombre limpio en vez de en Producción con la etiqueta cruda «prompt».
"""

from __future__ import annotations

from keni_consola import db_jobs


def test_prompt_cae_en_herramientas_con_nombre_limpio():
    # Audio y biblioteca de Prompts comparten tipo='prompt': son herramientas, no producción.
    assert db_jobs.pestana_economia("produccion", "prompt") == db_jobs.PESTANA_HERRAMIENTAS
    # Respaldo de nombre cuando no se sella etapa explícita (audio sella «Audio», biblioteca «Prompts»).
    assert db_jobs.etapa_economia("produccion", "prompt") == "Prompts"


def test_pipeline_se_desambigua_por_proceso():
    # El tipo 'pipeline' (compartido) lo desambigua el proceso sellado; una etapa EXPLÍCITA en la
    # fila (Cotejar/Subtema/Traducir/Investigar evergreen) manda sobre esta derivada (ver la query).
    assert db_jobs.etapa_economia("investigacion", "pipeline") == "Verificar"
    assert db_jobs.etapa_economia("produccion", "pipeline") == "Redactar"
