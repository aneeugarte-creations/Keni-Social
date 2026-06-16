"""Tests de las features nuevas en /api/piezas: imagen, encolar y duplicar.

OFFLINE. Para `encolar`, inyectamos un "ahora" fijo parcheando el `datetime` del
modulo de piezas, de modo que el hueco calculado sea determinista.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from keni_consola.api import piezas as ap

# Miercoles 2026-05-20 10:00 (weekday()==2).
_AHORA = datetime(2026, 5, 20, 10, 0)


class _AhoraFijo(datetime):
    """Subclase de datetime cuyo `now()` devuelve un instante fijo (determinista)."""

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        return _AHORA


@pytest.fixture
def ahora_fijo(monkeypatch):
    """Ancla `datetime.now()` en el modulo de piezas a un instante fijo."""
    # El cálculo de hueco (`calcular_hueco_para`) vive en el submódulo `programacion`; ahí lee
    # `datetime.now()`, así que el ancla se parchea en ESE módulo (no en el facade del paquete).
    monkeypatch.setattr(ap.programacion, "datetime", _AhoraFijo)
    return _AHORA


def _crear(cliente, **campos):
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    return cliente.post("/api/piezas", json=base)


# --------------------------------------------------------------------------- #
# Imagen                                                                      #
# --------------------------------------------------------------------------- #


def test_crear_con_imagen_incluye_url(cliente):
    pub = _crear(cliente, imagen="foto.png").json()["pieza"]
    assert pub["imagen"] == "foto.png"
    assert pub["imagen_url"] == "/api/media/foto.png"


def test_crear_marca_sin_plantilla_estudio_imagen_url_vacio(cliente):
    # Sin imagen horneada, sin foto y SIN plantilla de estudio (el test no siembra ninguna), la
    # pieza no tiene imagen servible -> `imagen_url` vacío.
    # Solo componen plantillas de la galería del estudio (el /compuesta con plantilla lo cubre
    # `test_render_pieza`).
    pub = _crear(cliente).json()["pieza"]
    assert pub["imagen"] == ""
    assert pub["imagen_url"] == ""


def test_actualizar_imagen(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.put(f"/api/piezas/{pid}", json={"imagen": "nueva.webp"})
    assert r.status_code == 200
    pub = r.json()["pieza"]
    assert pub["imagen"] == "nueva.webp"
    assert pub["imagen_url"] == "/api/media/nueva.webp"


def test_imagen_no_texto_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    assert cliente.put(f"/api/piezas/{pid}", json={"imagen": 5}).status_code == 400


def test_placa_oculta_persiste(cliente):
    # "Quitar plantilla": se guarda y PERSISTE (se lee en el detalle posterior).
    pid = _crear(cliente).json()["pieza"]["id"]
    assert cliente.get(f"/api/piezas/{pid}").json()["pieza"]["placa_oculta"] is False
    r = cliente.put(f"/api/piezas/{pid}", json={"placa_oculta": True})
    assert r.status_code == 200
    assert r.json()["pieza"]["placa_oculta"] is True
    assert cliente.get(f"/api/piezas/{pid}").json()["pieza"]["placa_oculta"] is True


def test_placa_oculta_no_bool_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    assert cliente.put(f"/api/piezas/{pid}", json={"placa_oculta": "si"}).status_code == 400


def test_fecha_programada_null_limpia(cliente):
    # El SPA manda fecha_programada=null cuando la pieza NO está programada: debe limpiarse, no
    # dar 400 (regresión: "La fecha programada debe ser texto" bloqueaba guardar cualquier pieza).
    pid = _crear(cliente).json()["pieza"]["id"]
    assert cliente.put(f"/api/piezas/{pid}", json={"fecha_programada": "2026-07-01T10:00"}).status_code == 200
    r = cliente.put(f"/api/piezas/{pid}", json={"fecha_programada": None})
    assert r.status_code == 200
    assert r.json()["pieza"]["fecha_programada"] == ""


def test_fecha_programada_no_texto_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    assert cliente.put(f"/api/piezas/{pid}", json={"fecha_programada": 5}).status_code == 400


# --------------------------------------------------------------------------- #
# Encolar                                                                     #
# --------------------------------------------------------------------------- #


def test_encolar_sin_franjas_400(cliente):
    pid = _crear(cliente).json()["pieza"]["id"]
    r = cliente.post(f"/api/piezas/{pid}/encolar")
    assert r.status_code == 400
    assert "franjas" in r.json()["error"].lower()


def test_encolar_404(cliente):
    assert cliente.post("/api/piezas/noexiste/encolar").status_code == 404


def test_encolar_programa_en_proximo_hueco(cliente, ahora_fijo):
    pid = _crear(cliente, marca="unotv", red="x").json()["pieza"]["id"]
    # franja general mie 15:00 (hoy futuro respecto a las 10:00)
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    r = cliente.post(f"/api/piezas/{pid}/encolar")
    assert r.status_code == 200
    pub = r.json()["pieza"]
    assert pub["estado"] == "programado"
    assert pub["fecha_programada"] == "2026-05-20T15:00"


def test_encolar_usa_franja_especifica(cliente, ahora_fijo):
    pid = _crear(cliente, marca="unotv", red="x").json()["pieza"]["id"]
    # general jueves 09:00 y especifica unotv/x viernes 08:00 -> la especifica gana
    cliente.post("/api/franjas", json={"dia_semana": 3, "hora": "09:00"})
    cliente.post("/api/franjas", json={"dia_semana": 4, "hora": "08:00", "marca": "unotv", "red": "x"})
    r = cliente.post(f"/api/piezas/{pid}/encolar")
    assert r.json()["pieza"]["fecha_programada"] == "2026-05-22T08:00"


def test_encolar_evita_hueco_ocupado(cliente, ahora_fijo):
    # franja general mie 15:00; una pieza YA programada ahi ocupa ese hueco.
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    ocupante = _crear(cliente).json()["pieza"]["id"]
    cliente.put(
        f"/api/piezas/{ocupante}",
        json={"estado": "programado", "fecha_programada": "2026-05-20T15:00"},
    )
    nuevo = _crear(cliente).json()["pieza"]["id"]
    r = cliente.post(f"/api/piezas/{nuevo}/encolar")
    # el hueco de hoy esta tomado -> salta a la semana siguiente
    assert r.json()["pieza"]["fecha_programada"] == "2026-05-27T15:00"


# --------------------------------------------------------------------------- #
# Duplicar                                                                    #
# --------------------------------------------------------------------------- #


def test_duplicar_copia_borrador(cliente):
    orig = _crear(
        cliente, titulo="Original", contenido="cuerpo", imagen="img.png"
    ).json()["pieza"]
    # programamos el original para verificar que la copia NO hereda estado/fecha
    cliente.put(
        f"/api/piezas/{orig['id']}",
        json={"estado": "en_revision"},
    )
    r = cliente.post(f"/api/piezas/{orig['id']}/duplicar")
    assert r.status_code == 200
    copia = r.json()["pieza"]
    assert copia["id"] != orig["id"]
    assert copia["estado"] == "borrador"
    assert copia["fecha_programada"] == ""
    assert copia["contenido"] == "cuerpo"
    assert copia["imagen"] == "img.png"
    assert copia["titulo"] == "Original"


def test_duplicar_con_overrides(cliente):
    orig = _crear(cliente, marca="unotv", red="x", titulo="A").json()["pieza"]
    r = cliente.post(
        f"/api/piezas/{orig['id']}/duplicar",
        json={"red": "instagram", "marca": "piso-15", "titulo": "B"},
    )
    copia = r.json()["pieza"]
    assert copia["red"] == "instagram"
    assert copia["marca"] == "piso-15"
    assert copia["titulo"] == "B"


def test_duplicar_override_red_invalida_400(cliente):
    orig = _crear(cliente).json()["pieza"]
    assert cliente.post(
        f"/api/piezas/{orig['id']}/duplicar", json={"red": "myspace"}
    ).status_code == 400


def test_duplicar_override_marca_invalida_400(cliente):
    orig = _crear(cliente).json()["pieza"]
    assert cliente.post(
        f"/api/piezas/{orig['id']}/duplicar", json={"marca": "marca_falsa"}
    ).status_code == 400


def test_duplicar_404(cliente):
    assert cliente.post("/api/piezas/noexiste/duplicar").status_code == 404
