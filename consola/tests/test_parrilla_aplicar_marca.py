"""La marca del workspace que importó se estampa en los `rota_eventos` creados al APLICAR
una propuesta de parrilla — sin ella, la lista de Tareas (filtrada por marca) no los vería.

Postgres real (fixture `entorno`): ejercita el INSERT INTO rota_eventos de
`db_parrilla.aplicar_propuesta_parrilla` y la columna `marca` de `parrilla_propuesta`.
"""

from __future__ import annotations

from keni_consola import repos


def test_aplicar_propuesta_estampa_marca_en_eventos(entorno):
    prop = repos.crear_propuesta_parrilla(
        semana="", doc_nombre="programacion.xlsx", marca="claro-sports"
    )
    assert prop["marca"] == "claro-sports"
    ops = [
        {
            "tipo": "crear_evento",
            "titulo": "Cruz Azul vs América",
            "fecha": "2026-07-01",
            "hora": "20:00",
        }
    ]
    resumen = repos.aplicar_propuesta_parrilla(
        prop["id"], ops, nombres_miembros={}, marca="claro-sports"
    )
    assert len(resumen["eventos_creados"]) == 1
    ev = repos.obtener_evento_rota(resumen["eventos_creados"][0])
    assert ev is not None
    assert ev["marca"] == "claro-sports"
    assert ev["titulo"] == "Cruz Azul vs América"


def test_aplicar_propuesta_sin_marca_no_regresiona_turnos(entorno):
    """Sin marca (import legado de Turnos) el evento nace con marca "" — comportamiento de hoy."""
    prop = repos.crear_propuesta_parrilla(semana="", doc_nombre="doc.pdf")
    assert prop["marca"] == ""
    ops = [{"tipo": "crear_evento", "titulo": "Amistoso", "fecha": "2026-07-02"}]
    resumen = repos.aplicar_propuesta_parrilla(prop["id"], ops, nombres_miembros={})
    ev = repos.obtener_evento_rota(resumen["eventos_creados"][0])
    assert (ev or {}).get("marca", "") == ""
