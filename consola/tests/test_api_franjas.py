"""Tests de la API Franjas (/api/franjas) + logica pura de calculo de hueco.

OFFLINE. El calculo de hueco se prueba con un "ahora" inyectado (determinista).
"""

from __future__ import annotations

from datetime import datetime

from keni_consola.api import franjas as af

# --------------------------------------------------------------------------- #
# CRUD endpoints                                                              #
# --------------------------------------------------------------------------- #


def test_crear_y_listar(cliente):
    r = cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "09:00", "marca": "unotv", "red": "x"})
    assert r.status_code == 200
    franja = r.json()["franja"]
    assert franja["dia_semana"] == 2
    assert franja["hora"] == "09:00"
    assert franja["marca_nombre"] == "UnoTV"
    assert franja["red_nombre"] == "X"
    assert len(cliente.get("/api/franjas").json()["franjas"]) == 1


def test_crear_general_sin_marca_ni_red(cliente):
    r = cliente.post("/api/franjas", json={"dia_semana": 0, "hora": "10:30"})
    assert r.status_code == 200
    f = r.json()["franja"]
    assert f["marca"] == "" and f["red"] == ""


def test_crear_dia_invalido_400(cliente):
    assert cliente.post("/api/franjas", json={"dia_semana": 7, "hora": "09:00"}).status_code == 400
    assert cliente.post("/api/franjas", json={"dia_semana": -1, "hora": "09:00"}).status_code == 400
    assert cliente.post("/api/franjas", json={"dia_semana": "lunes", "hora": "09:00"}).status_code == 400


def test_crear_dia_bool_400(cliente):
    # True es int en Python; no debe colarse como dia 1.
    assert cliente.post("/api/franjas", json={"dia_semana": True, "hora": "09:00"}).status_code == 400


def test_crear_hora_invalida_400(cliente):
    for hora in ("9:00", "25:00", "09:60", "0900", "abc"):
        assert cliente.post("/api/franjas", json={"dia_semana": 0, "hora": hora}).status_code == 400


def test_crear_marca_invalida_400(cliente):
    r = cliente.post("/api/franjas", json={"dia_semana": 0, "hora": "09:00", "marca": "marca_falsa"})
    assert r.status_code == 400


def test_crear_red_invalida_400(cliente):
    r = cliente.post("/api/franjas", json={"dia_semana": 0, "hora": "09:00", "red": "myspace"})
    assert r.status_code == 400


def test_borrar(cliente):
    fid = cliente.post("/api/franjas", json={"dia_semana": 0, "hora": "09:00"}).json()["franja"]["id"]
    assert cliente.delete(f"/api/franjas/{fid}").status_code == 200
    assert cliente.delete(f"/api/franjas/{fid}").status_code == 404


# --------------------------------------------------------------------------- #
# franjas_aplicables: prioridad por especificidad                             #
# --------------------------------------------------------------------------- #


def _f(fid, marca, red, dia, hora, categoria=""):
    return {"id": fid, "marca": marca, "red": red, "dia_semana": dia, "hora": hora,
            "categoria": categoria}


def test_aplicables_especifica_gana():
    franjas = [
        _f("esp", "unotv", "x", 0, "09:00"),
        _f("marca", "unotv", "", 1, "09:00"),
        _f("gen", "", "", 2, "09:00"),
    ]
    assert [f["id"] for f in af.franjas_aplicables(franjas, "unotv", "x")] == ["esp"]


def test_aplicables_parcial_y_general():
    franjas = [
        _f("marca", "unotv", "", 1, "09:00"),
        _f("red", "", "instagram", 2, "09:00"),
        _f("gen", "", "", 3, "09:00"),
    ]
    ids = {f["id"] for f in af.franjas_aplicables(franjas, "unotv", "instagram")}
    assert ids == {"marca", "red", "gen"}


def test_aplicables_solo_general():
    franjas = [_f("gen", "", "", 2, "09:00")]
    assert [f["id"] for f in af.franjas_aplicables(franjas, "piso-15", "youtube")] == ["gen"]


def test_aplicables_ninguna():
    franjas = [_f("otra", "piso-15", "x", 0, "09:00")]
    assert af.franjas_aplicables(franjas, "unotv", "instagram") == []


def test_aplicables_categoria_usa_sus_horarios():
    """Una pieza con categoría usa las franjas de SU categoría (los horarios del plan)."""
    franjas = [
        _f("intl", "unotv", "", 0, "14:45", "internacional"),
        _f("mx", "unotv", "", 0, "15:45", "mx"),
        _f("gen", "unotv", "", 0, "12:00"),
    ]
    ids = [f["id"] for f in af.franjas_aplicables(franjas, "unotv", "x", "internacional")]
    assert ids == ["intl"]


def test_aplicables_categoria_sin_horario_cae_a_genericas():
    franjas = [
        _f("intl", "unotv", "", 0, "14:45", "internacional"),
        _f("gen", "unotv", "", 0, "12:00"),
    ]
    ids = [f["id"] for f in af.franjas_aplicables(franjas, "unotv", "x", "deportes")]
    assert ids == ["gen"]


def test_aplicables_sin_categoria_solo_genericas():
    """Una pieza sin categoría no se cuela en los horarios del plan de una categoría."""
    franjas = [
        _f("intl", "unotv", "", 0, "14:45", "internacional"),
        _f("gen", "unotv", "", 0, "12:00"),
    ]
    ids = [f["id"] for f in af.franjas_aplicables(franjas, "unotv", "x")]
    assert ids == ["gen"]


def test_crear_franja_con_categoria(cliente):
    r = cliente.post(
        "/api/franjas",
        json={"dia_semana": 2, "hora": "14:45", "marca": "unotv", "categoria": "Internacional"},
    )
    assert r.status_code == 200
    f = r.json()["franja"]
    assert f["categoria"] == "internacional"  # normalizada a minúsculas
    # Y se lista con su categoría.
    listadas = cliente.get("/api/franjas").json()["franjas"]
    assert any(x["categoria"] == "internacional" for x in listadas)


# --------------------------------------------------------------------------- #
# proximo_hueco: calculo determinista con "ahora" inyectado                   #
# --------------------------------------------------------------------------- #

# Miercoles 2026-05-20 10:00 (weekday()==2).
_AHORA = datetime(2026, 5, 20, 10, 0)


def test_hueco_hoy_mas_tarde():
    franjas = [_f("a", "", "", 2, "15:00")]  # mie 15:00 (hoy, futuro)
    assert af.proximo_hueco(franjas, _AHORA, set()) == "2026-05-20T15:00"


def test_hueco_hoy_ya_paso_salta_semana():
    franjas = [_f("a", "", "", 2, "09:00")]  # mie 09:00 (ya paso hoy)
    assert af.proximo_hueco(franjas, _AHORA, set()) == "2026-05-27T09:00"


def test_hueco_proximo_dia():
    franjas = [_f("a", "", "", 4, "08:00")]  # viernes 08:00
    assert af.proximo_hueco(franjas, _AHORA, set()) == "2026-05-22T08:00"


def test_hueco_elige_el_mas_temprano():
    franjas = [
        _f("vie", "", "", 4, "08:00"),  # 2026-05-22
        _f("jue", "", "", 3, "20:00"),  # 2026-05-21 (mas temprano)
    ]
    assert af.proximo_hueco(franjas, _AHORA, set()) == "2026-05-21T20:00"


def test_hueco_evita_ocupado():
    franjas = [_f("a", "", "", 2, "15:00")]  # mie 15:00
    ocupados = {"2026-05-20T15:00"}  # ese hueco ya esta tomado
    assert af.proximo_hueco(franjas, _AHORA, ocupados) == "2026-05-27T15:00"


def test_hueco_sin_franjas_devuelve_none():
    assert af.proximo_hueco([], _AHORA, set()) is None
