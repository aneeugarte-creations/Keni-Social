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
    # `eventos_creados` es el CONTEO; los ids van en `ids.eventos`.
    assert resumen["eventos_creados"] == 1
    ev = repos.obtener_evento_rota(resumen["ids"]["eventos"][0])
    assert ev is not None
    assert ev["marca"] == "claro-sports"
    assert ev["titulo"] == "Cruz Azul vs América"


def test_aplicar_propuesta_sin_marca_no_regresiona_turnos(entorno):
    """Sin marca (import legado de Turnos) el evento nace con marca "" — comportamiento de hoy."""
    prop = repos.crear_propuesta_parrilla(semana="", doc_nombre="doc.pdf")
    assert prop["marca"] == ""
    ops = [{"tipo": "crear_evento", "titulo": "Amistoso", "fecha": "2026-07-02"}]
    resumen = repos.aplicar_propuesta_parrilla(prop["id"], ops, nombres_miembros={})
    ev = repos.obtener_evento_rota(resumen["ids"]["eventos"][0])
    assert (ev or {}).get("marca", "") == ""


def test_aplicar_propuesta_crea_tareas(entorno):
    """Modo tareas: una op `crear_tarea` crea un contenido clase='tarea' (encargo), NO un evento.
    Nace SIN responsable («por coger»); se estampa la marca para que la lista (filtrada) lo vea."""
    prop = repos.crear_propuesta_parrilla(
        semana="", doc_nombre="pendientes.txt", marca="claro-sports"
    )
    ops = [
        {
            "tipo": "crear_tarea",
            "titulo": "Editar el clip del gol",
            "detalle": "subir a IG",
            "prioridad": "alta",
            "fecha_objetivo": "2026-07-03",
        }
    ]
    resumen = repos.aplicar_propuesta_parrilla(
        prop["id"], ops, nombres_miembros={}, marca="claro-sports"
    )
    assert resumen["tareas_creadas"] == 1
    assert resumen["eventos_creados"] == 0
    tarea = repos.obtener_publicacion(resumen["ids"]["tareas"][0])
    assert tarea is not None
    assert tarea["clase"] == "tarea"
    assert tarea["titulo"] == "Editar el clip del gol"
    assert tarea["descripcion"] == "subir a IG"
    assert tarea["prioridad"] == "alta"
    assert tarea["fecha_objetivo"] == "2026-07-03"
    assert tarea["marca"] == "claro-sports"
    # Nace «por coger»: sin responsable asignado.
    assert (tarea.get("responsable_id") or "") == ""


def test_aplicar_propuesta_estampa_marca_en_turno(entorno):
    """El turno importado (modo `turnos`) nace con la MARCA de la propuesta. La rejilla filtra
    `WHERE marca = ?`: sin marca el turno quedaba invisible (bug «no están asignados en las
    franjas»). La franja que crea `_franja_id_de` si no existe también hereda la marca."""
    prop = repos.crear_propuesta_parrilla(
        semana="", doc_nombre="parrilla.xlsx", marca="claro-sports"
    )
    ops = [
        {
            "tipo": "crear_turno",
            "fecha": "2026-07-01",
            "franja": "Mañana",
            "franja_inicio": "08:00",
            "franja_fin": "16:00",
            "miembro_id": "u-luis",
        }
    ]
    resumen = repos.aplicar_propuesta_parrilla(
        prop["id"], ops, nombres_miembros={"u-luis": "Luis"}, marca="claro-sports"
    )
    assert resumen["turnos_creados"] == 1
    tid = resumen["ids"]["turnos"][0]
    # La rejilla por marca SÍ lo devuelve bajo claro-sports...
    de_claro = repos.listar_turnos_rota(marca="claro-sports")
    assert any(t["id"] == tid for t in de_claro)
    # ...y NO bajo otra marca (no se cuela en otra rejilla).
    de_otra = repos.listar_turnos_rota(marca="otra-marca")
    assert all(t["id"] != tid for t in de_otra)


def test_aplicar_turno_sin_marca_resuelve_franja_de_cualquier_marca(entorno):
    """Sin marca (legado/«Todas») `_franja_id_de` NO filtra por marca: resuelve por nombre como
    antes (no rompe el import legado de Turnos)."""
    prop = repos.crear_propuesta_parrilla(semana="", doc_nombre="doc.pdf")
    assert prop["marca"] == ""
    ops = [
        {"tipo": "crear_turno", "fecha": "2026-07-08", "franja": "Tarde", "miembro_id": "u-x"}
    ]
    resumen = repos.aplicar_propuesta_parrilla(
        prop["id"], ops, nombres_miembros={"u-x": "X"}
    )
    assert resumen["turnos_creados"] == 1
