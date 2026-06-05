"""Tests de las features nuevas en /api/publicaciones: imagen, encolar y duplicar.

OFFLINE. Para `encolar`, inyectamos un "ahora" fijo parcheando el `datetime` del
modulo de publicaciones, de modo que el hueco calculado sea determinista.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from keni_consola.api import publicaciones as ap

# Miercoles 2026-05-20 10:00 (weekday()==2).
_AHORA = datetime(2026, 5, 20, 10, 0)


class _AhoraFijo(datetime):
    """Subclase de datetime cuyo `now()` devuelve un instante fijo (determinista)."""

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        return _AHORA


@pytest.fixture
def ahora_fijo(monkeypatch):
    """Ancla `datetime.now()` en el modulo de publicaciones a un instante fijo."""
    monkeypatch.setattr(ap, "datetime", _AhoraFijo)
    return _AHORA


def _crear(cliente, **campos):
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    return cliente.post("/api/publicaciones", json=base)


# --------------------------------------------------------------------------- #
# Imagen                                                                      #
# --------------------------------------------------------------------------- #


def test_crear_con_imagen_incluye_url(cliente):
    pub = _crear(cliente, imagen="foto.png").json()["publicacion"]
    assert pub["imagen"] == "foto.png"
    assert pub["imagen_url"] == "/api/media/foto.png"


def test_crear_sin_imagen_horneada_usa_compuesta(cliente):
    # Sin imagen horneada pero CON receta de marca (unotv tiene placa), la url apunta al render
    # on-demand `/compuesta` (no a "" ni a un media): la placa se compone al pedirla.
    pub = _crear(cliente).json()["publicacion"]
    assert pub["imagen"] == ""
    # La URL puede llevar sufijo `?v=` (cache-bust por `actualizado`); comparamos solo la ruta.
    assert pub["imagen_url"].split("?")[0] == f"/api/publicaciones/{pub['id']}/compuesta"


def test_actualizar_imagen(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={"imagen": "nueva.webp"})
    assert r.status_code == 200
    pub = r.json()["publicacion"]
    assert pub["imagen"] == "nueva.webp"
    assert pub["imagen_url"] == "/api/media/nueva.webp"


def test_imagen_no_texto_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.put(f"/api/publicaciones/{pid}", json={"imagen": 5}).status_code == 400


def test_placa_oculta_persiste(cliente):
    # "Quitar plantilla": se guarda y PERSISTE (se lee en el detalle posterior).
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.get(f"/api/publicaciones/{pid}").json()["publicacion"]["placa_oculta"] is False
    r = cliente.put(f"/api/publicaciones/{pid}", json={"placa_oculta": True})
    assert r.status_code == 200
    assert r.json()["publicacion"]["placa_oculta"] is True
    assert cliente.get(f"/api/publicaciones/{pid}").json()["publicacion"]["placa_oculta"] is True


def test_placa_oculta_no_bool_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.put(f"/api/publicaciones/{pid}", json={"placa_oculta": "si"}).status_code == 400


def test_fecha_programada_null_limpia(cliente):
    # El SPA manda fecha_programada=null cuando la pieza NO está programada: debe limpiarse, no
    # dar 400 (regresión: "La fecha programada debe ser texto" bloqueaba guardar cualquier pieza).
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.put(f"/api/publicaciones/{pid}", json={"fecha_programada": "2026-07-01T10:00"}).status_code == 200
    r = cliente.put(f"/api/publicaciones/{pid}", json={"fecha_programada": None})
    assert r.status_code == 200
    assert r.json()["publicacion"]["fecha_programada"] == ""


def test_fecha_programada_no_texto_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.put(f"/api/publicaciones/{pid}", json={"fecha_programada": 5}).status_code == 400


# --------------------------------------------------------------------------- #
# Encolar                                                                     #
# --------------------------------------------------------------------------- #


def test_encolar_sin_franjas_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.post(f"/api/publicaciones/{pid}/encolar")
    assert r.status_code == 400
    assert "franjas" in r.json()["error"].lower()


def test_encolar_404(cliente):
    assert cliente.post("/api/publicaciones/noexiste/encolar").status_code == 404


def test_encolar_programa_en_proximo_hueco(cliente, ahora_fijo):
    pid = _crear(cliente, marca="unotv", red="x").json()["publicacion"]["id"]
    # franja general mie 15:00 (hoy futuro respecto a las 10:00)
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    r = cliente.post(f"/api/publicaciones/{pid}/encolar")
    assert r.status_code == 200
    pub = r.json()["publicacion"]
    assert pub["estado"] == "programado"
    assert pub["fecha_programada"] == "2026-05-20T15:00"


def test_encolar_usa_franja_especifica(cliente, ahora_fijo):
    pid = _crear(cliente, marca="unotv", red="x").json()["publicacion"]["id"]
    # general jueves 09:00 y especifica unotv/x viernes 08:00 -> la especifica gana
    cliente.post("/api/franjas", json={"dia_semana": 3, "hora": "09:00"})
    cliente.post("/api/franjas", json={"dia_semana": 4, "hora": "08:00", "marca": "unotv", "red": "x"})
    r = cliente.post(f"/api/publicaciones/{pid}/encolar")
    assert r.json()["publicacion"]["fecha_programada"] == "2026-05-22T08:00"


def test_encolar_evita_hueco_ocupado(cliente, ahora_fijo):
    # franja general mie 15:00; una publicacion YA programada ahi ocupa ese hueco.
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    ocupante = _crear(cliente).json()["publicacion"]["id"]
    cliente.put(
        f"/api/publicaciones/{ocupante}",
        json={"estado": "programado", "fecha_programada": "2026-05-20T15:00"},
    )
    nuevo = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.post(f"/api/publicaciones/{nuevo}/encolar")
    # el hueco de hoy esta tomado -> salta a la semana siguiente
    assert r.json()["publicacion"]["fecha_programada"] == "2026-05-27T15:00"


# --------------------------------------------------------------------------- #
# Duplicar                                                                    #
# --------------------------------------------------------------------------- #


def test_duplicar_copia_borrador(cliente):
    orig = _crear(
        cliente, titulo="Original", contenido="cuerpo", imagen="img.png"
    ).json()["publicacion"]
    # programamos el original para verificar que la copia NO hereda estado/fecha
    cliente.put(
        f"/api/publicaciones/{orig['id']}",
        json={"estado": "aprobado"},
    )
    r = cliente.post(f"/api/publicaciones/{orig['id']}/duplicar")
    assert r.status_code == 200
    copia = r.json()["publicacion"]
    assert copia["id"] != orig["id"]
    assert copia["estado"] == "borrador"
    assert copia["fecha_programada"] == ""
    assert copia["contenido"] == "cuerpo"
    assert copia["imagen"] == "img.png"
    assert copia["titulo"] == "Original"


def test_duplicar_con_overrides(cliente):
    orig = _crear(cliente, marca="unotv", red="x", titulo="A").json()["publicacion"]
    r = cliente.post(
        f"/api/publicaciones/{orig['id']}/duplicar",
        json={"red": "instagram", "marca": "piso-15", "titulo": "B"},
    )
    copia = r.json()["publicacion"]
    assert copia["red"] == "instagram"
    assert copia["marca"] == "piso-15"
    assert copia["titulo"] == "B"


def test_duplicar_override_red_invalida_400(cliente):
    orig = _crear(cliente).json()["publicacion"]
    assert cliente.post(
        f"/api/publicaciones/{orig['id']}/duplicar", json={"red": "myspace"}
    ).status_code == 400


def test_duplicar_override_marca_invalida_400(cliente):
    orig = _crear(cliente).json()["publicacion"]
    assert cliente.post(
        f"/api/publicaciones/{orig['id']}/duplicar", json={"marca": "marca_falsa"}
    ).status_code == 400


def test_duplicar_404(cliente):
    assert cliente.post("/api/publicaciones/noexiste/duplicar").status_code == 404
