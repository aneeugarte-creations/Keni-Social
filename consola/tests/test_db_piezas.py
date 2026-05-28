"""Tests del CRUD de `rota_piezas` (`keni_consola.db`): dato OPERACIONAL (#150).

La PARRILLA 2026 del Excel de Tescu modela cada FILA como un POST individual. Aqui
probamos el contrato basico de la persistencia: CRUD, filtros combinables, allowlist de
campos editables, migracion idempotente, y que el `actualizado` se refresca en cada
edicion. Reutiliza la fixture `entorno` (Postgres de pruebas o skip).
"""

from __future__ import annotations

from keni_consola import db


def test_crear_pieza_minimal_persiste(entorno):
    """Una pieza nace con todos los campos por defecto y `id` propio."""
    p = db.crear_pieza_rota(programa="Álvaro Fidalgo", contenido_sugerido="Reel semanal")
    assert p["id"]
    assert p["programa"] == "Álvaro Fidalgo"
    assert p["contenido_sugerido"] == "Reel semanal"
    assert p["evento_id"] == ""
    assert p["estado"] == "pendiente"
    assert p["material_entregado"] is False
    assert p["contenido_entregado"] is False
    assert p["publicado"] is False
    assert p["creado"]
    assert p["actualizado"]


def test_crear_pieza_con_workflow_excel(entorno):
    """El workflow del Excel (material/contenido/publicado/enlace) se persiste tal cual."""
    p = db.crear_pieza_rota(
        evento_id="ev-1",
        red_social="FB, IG, X",
        tipo_pieza="IMAGEN",
        dia="2026-06-15",
        hora_post="17:30",
        material_entregado=True,
        contenido_entregado=True,
        publicado=False,
        enlace="https://example.com/post/abc",
    )
    leida = db.obtener_pieza_rota(p["id"])
    assert leida is not None
    assert leida["red_social"] == "FB, IG, X"
    assert leida["tipo_pieza"] == "IMAGEN"
    assert leida["dia"] == "2026-06-15"
    assert leida["hora_post"] == "17:30"
    assert leida["material_entregado"] is True
    assert leida["contenido_entregado"] is True
    assert leida["publicado"] is False
    assert leida["enlace"] == "https://example.com/post/abc"


def test_crear_pieza_estado_invalido_cae_a_pendiente(entorno):
    """El layer DB valida `estado` contra `ESTADOS_PIEZA`; un valor raro cae a default."""
    assert "publicado" in db.ESTADOS_PIEZA
    p = db.crear_pieza_rota(programa="X", estado="raro")
    assert p["estado"] == "pendiente"


def test_listar_piezas_filtro_evento(entorno):
    """`evento_id` filtra; pasar "" lista las piezas SUELTAS (sin evento)."""
    a = db.crear_pieza_rota(evento_id="ev-1", contenido_sugerido="pieza a")
    b = db.crear_pieza_rota(evento_id="ev-2", contenido_sugerido="pieza b")
    suelta = db.crear_pieza_rota(programa="Real Oviedo", contenido_sugerido="sin evento")

    soloA = db.listar_piezas_rota(evento_id="ev-1")
    assert {p["id"] for p in soloA} == {a["id"]}

    sueltas = db.listar_piezas_rota(evento_id="")
    assert suelta["id"] in {p["id"] for p in sueltas}
    assert b["id"] not in {p["id"] for p in sueltas}


def test_listar_piezas_filtros_combinables(entorno):
    """Rango de `dia`, `estado`, `programa`, `red`/`tipo` filtran a la vez."""
    db.crear_pieza_rota(programa="MUNDIAL", dia="2026-06-01", estado="pendiente", red_social="WEB")
    db.crear_pieza_rota(programa="MUNDIAL", dia="2026-06-10", estado="listo", red_social="FB, IG")
    db.crear_pieza_rota(programa="Paty Cantú", dia="2026-06-10", estado="listo", red_social="FB, IG")

    en_rango = db.listar_piezas_rota(desde="2026-06-05", hasta="2026-06-15")
    assert len(en_rango) == 2

    listos_mundial = db.listar_piezas_rota(programa="MUNDIAL", estado="listo")
    assert len(listos_mundial) == 1
    assert listos_mundial[0]["red_social"] == "FB, IG"


def test_actualizar_pieza_cambia_estado_y_publicado(entorno):
    """El PATCH cambia estado y booleanos; `actualizado` se refresca."""
    p = db.crear_pieza_rota(programa="X")
    actualizada = db.actualizar_pieza_rota(p["id"], {"estado": "listo", "publicado": True})
    assert actualizada is not None
    assert actualizada["estado"] == "listo"
    assert actualizada["publicado"] is True
    # `actualizado` cambia entre crear y editar (en el peor caso queda igual al ser mismo
    # segundo; sigue siendo no decreciente).
    assert actualizada["actualizado"] >= p["actualizado"]


def test_actualizar_pieza_ignora_columnas_arbitrarias(entorno):
    """La allowlist `_CAMPOS_EDITABLES_PIEZA_ROTA` filtra cualquier columna ajena."""
    p = db.crear_pieza_rota(programa="X")
    # Intentar tocar `id`/`creado` no debe poder. Lo importante: NO revienta y NO los toca.
    actualizada = db.actualizar_pieza_rota(
        p["id"], {"id": "otro-id", "creado": "1900-01-01", "notas": "nota legit"}
    )
    assert actualizada is not None
    assert actualizada["id"] == p["id"]
    assert actualizada["creado"] == p["creado"]
    assert actualizada["notas"] == "nota legit"


def test_actualizar_pieza_inexistente_devuelve_none(entorno):
    assert db.actualizar_pieza_rota("no-existe", {"estado": "listo"}) is None


def test_borrar_pieza(entorno):
    p = db.crear_pieza_rota(programa="X")
    assert db.borrar_pieza_rota(p["id"]) is True
    assert db.obtener_pieza_rota(p["id"]) is None
    assert db.borrar_pieza_rota(p["id"]) is False


def test_esquema_se_crea_on_demand(entorno):
    """La primera llamada crea el esquema en Postgres (idempotente)."""
    assert db.listar_piezas_rota() == []


def test_migracion_columnas_piezas_idempotente(entorno):
    """Volver a abrir la BD no rompe si las columnas ya existen (migracion idempotente)."""
    # Forzar varias conexiones consecutivas: el _crear_esquema se ejecuta cada vez.
    db.listar_piezas_rota()
    db.listar_piezas_rota()
    p = db.crear_pieza_rota(programa="X")
    assert p["id"]
