"""Lado-backend del túnel keni-fotos (fuente «Propio»): dispatcher + endpoints HTTP.

OFFLINE y sin red real: el WebSocket de la app se simula con conexiones FAKE que resuelven los
RPC del dispatcher en memoria. Cubre:
  - registro/fan-out de `fotos_tunel.buscar` (agrega de varias apps y trocea a `limite`),
  - el GATE de marca (`claro-sports`): sin esa marca o sin dispositivos, la fuente sale vacía,
  - `_adjuntar_propio` pide el original por el túnel, lo SUBE a media y lo LIGA como foto propia,
  - el WebSocket RECHAZA un token inválido (cierra sin registrar).

Los tests que crean piezas usan la fixture `entorno` (BD de pruebas); el resto corre sin BD.
"""

from __future__ import annotations

import base64
from typing import Any

import anyio
from starlette.websockets import WebSocketDisconnect

from keni_consola import auth, fotos_tunel
from keni_consola.api import artes
from keni_consola.api import fotos as fotos_api

# PNG 1x1 válido: el original que la app «manda» por el túnel (base64).
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeWS:
    """WebSocket FAKE: al `send_json` de un RPC, responde de inmediato vía `responder`."""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}
        self.conexion: fotos_tunel.Conexion | None = None
        self.responder = None  # callable(msg) -> dict | None
        self.enviados: list[dict[str, Any]] = []
        self.cerrado: int | None = None
        self.aceptado = False

    async def accept(self) -> None:
        self.aceptado = True

    async def close(self, code: int = 1000) -> None:
        self.cerrado = code

    async def send_json(self, mensaje: dict[str, Any]) -> None:
        self.enviados.append(mensaje)
        if self.responder is not None and self.conexion is not None:
            respuesta = self.responder(mensaje)
            if respuesta is not None:
                self.conexion.resolver(mensaje["id"], respuesta)


def _conexion(usuario_id: str, responder=None, *, dispositivo="Mac de Ale", galerias=None):
    """Registra una conexión FAKE de `usuario_id` y la devuelve."""
    ws = _FakeWS()
    conexion = fotos_tunel.Conexion(ws, usuario_id)
    conexion.dispositivo = dispositivo
    conexion.galerias = galerias if galerias is not None else [{"id": "g1"}]
    ws.conexion = conexion
    ws.responder = responder
    fotos_tunel.registrar(conexion)
    return conexion


def _resultado(msg, n):
    return {
        "tipo": "resultado",
        "id": msg["id"],
        "candidatos": [
            {
                "galeria_id": "g1",
                "archivo": f"f{i}.jpg",
                "thumb_b64": "data:image/jpeg;base64,xx",
                "nombre": "Colombia vs Uzbekistán",
                "dia": "2026-06-20",
                "fase": "in-game",
                "en_foco": "portero",
            }
            for i in range(n)
        ],
    }


# --------------------------------------------------------------------------- #
# Dispatcher: registro + fan-out + troceo                                       #
# --------------------------------------------------------------------------- #


def test_buscar_agrega_y_trocea_a_limite():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("u1", lambda m: _resultado(m, 5), dispositivo="Mac de Ale")
        res = anyio.run(fotos_tunel.buscar, "u1", "portero", 3)
        assert len(res) == 3  # 5 candidatos troceados a `limite`
        assert all(c["dispositivo"] == "Mac de Ale" for c in res)
    finally:
        fotos_tunel._REGISTRO.clear()


def test_buscar_hace_fan_out_a_varias_apps():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("u1", lambda m: _resultado(m, 2), dispositivo="Mac A")
        _conexion("u1", lambda m: _resultado(m, 2), dispositivo="Mac B")
        res = anyio.run(fotos_tunel.buscar, "u1", "portero", 10)
        assert len(res) == 4  # 2 + 2 de las dos apps
        assert {c["dispositivo"] for c in res} == {"Mac A", "Mac B"}
    finally:
        fotos_tunel._REGISTRO.clear()


def test_buscar_sin_dispositivos_devuelve_vacio():
    fotos_tunel._REGISTRO.clear()
    res = anyio.run(fotos_tunel.buscar, "u-nadie", "portero", 4)
    assert res == []


# --------------------------------------------------------------------------- #
# Gate de marca en `_buscar_propio`                                             #
# --------------------------------------------------------------------------- #


def test_buscar_propio_marca_no_claro_inerte():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("u1", lambda m: _resultado(m, 3))  # hay dispositivo, pero la marca no es claro
        res = anyio.run(artes._buscar_propio, "u1", "portero", 4, "unotv")
        assert res["candidatos"] == []
        assert res["proveedores"][0]["disponible"] is False
        assert res["proveedores"][0]["proveedor"] == "propio"
    finally:
        fotos_tunel._REGISTRO.clear()


def test_buscar_propio_claro_sin_dispositivos_inerte():
    fotos_tunel._REGISTRO.clear()
    res = anyio.run(artes._buscar_propio, "u1", "portero", 4, "claro-sports")
    assert res["candidatos"] == []
    assert res["proveedores"][0]["disponible"] is False


def test_buscar_propio_claro_con_dispositivo_devuelve_candidatos():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("u1", lambda m: _resultado(m, 2), dispositivo="Mac de Ale")
        res = anyio.run(artes._buscar_propio, "u1", "portero", 4, "claro-sports")
        prov = res["proveedores"][0]
        assert prov["disponible"] is True
        assert prov["dispositivos"] == 1
        cand = res["candidatos"][0]
        assert cand["proveedor"] == "propio"
        assert cand["galeria_id"] == "g1"
        assert cand["archivo"] == "f0.jpg"
        assert cand["dispositivo"] == "Mac de Ale"
        assert cand["titulo"] == "Colombia vs Uzbekistán · in-game · portero"
    finally:
        fotos_tunel._REGISTRO.clear()


# --------------------------------------------------------------------------- #
# Adjuntar: pide el original por el túnel, sube a media y liga la pieza          #
# --------------------------------------------------------------------------- #


def _responder_original(msg):
    if msg.get("tipo") != "original":
        return None
    return {
        "tipo": "original_datos",
        "id": msg["id"],
        "mime": "image/png",
        "datos_b64": base64.b64encode(_PNG_1x1).decode("ascii"),
        "nombre": "keeper.jpg",
    }


def test_adjuntar_propio_pide_original_sube_y_liga(entorno):
    from keni_consola import repos

    fotos_tunel._REGISTRO.clear()
    try:
        tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="claro-sports")
        pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
        _conexion("u1", _responder_original, galerias=[{"id": "g1", "nombre": "X"}])

        status, cuerpo = anyio.run(artes._adjuntar_propio, "u1", pid, "g1", "keeper.jpg", "")
        assert status == 200
        assert cuerpo["plataforma"]["foto"]

        fila = repos.obtener_pieza_fila(pid)
        assert fila["imagen_origen"] == "propia"
        assert bool(fila["falta_imagen"]) is False
        assert fila["foto"]  # objeto subido a media
    finally:
        fotos_tunel._REGISTRO.clear()


def test_adjuntar_propio_gate_marca_no_claro(entorno):
    from keni_consola import repos

    fotos_tunel._REGISTRO.clear()
    try:
        tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="unotv")
        pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
        _conexion("u1", _responder_original)
        status, cuerpo = anyio.run(artes._adjuntar_propio, "u1", pid, "g1", "keeper.jpg", "")
        assert status == 400
        assert "Claro Sports" in cuerpo["error"]
    finally:
        fotos_tunel._REGISTRO.clear()


def test_adjuntar_propio_sin_dispositivo_da_400(entorno):
    from keni_consola import repos

    fotos_tunel._REGISTRO.clear()
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="claro-sports")
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    status, cuerpo = anyio.run(artes._adjuntar_propio, "u1", pid, "g1", "keeper.jpg", "")
    assert status == 400
    assert "error" in cuerpo


# --------------------------------------------------------------------------- #
# WebSocket: auth con el token de escritorio                                    #
# --------------------------------------------------------------------------- #


def test_ws_token_invalido_cierra_y_no_registra():
    fotos_tunel._REGISTRO.clear()
    ws = _FakeWS(headers={})  # sin Authorization -> token None -> cierra
    anyio.run(fotos_api.tunel, ws)
    assert ws.aceptado is True
    assert ws.cerrado == 4401
    assert fotos_tunel._REGISTRO == {}


class _FakeWSGuion(_FakeWS):
    """WebSocket FAKE con un GUION de mensajes entrantes; al agotarse, simula desconexión."""

    def __init__(self, headers, guion):
        super().__init__(headers=headers)
        self._guion = list(guion)

    async def receive_json(self):
        if not self._guion:
            raise WebSocketDisconnect(1000)
        item = self._guion.pop(0)
        return item() if callable(item) else item


def test_ws_token_valido_registra_y_limpia_al_desconectar(monkeypatch):
    fotos_tunel._REGISTRO.clear()
    monkeypatch.setattr(
        auth, "token_mcp_valido", lambda t: {"id": "u1", "usuario": "ale", "rol": "editor"}
    )
    visto: dict[str, Any] = {}

    def _comprobar_y_cortar():
        # En pleno bucle, la conexión ya está registrada con su `hola`.
        visto["dispositivos"] = fotos_tunel.dispositivos("u1")
        raise WebSocketDisconnect(1000)

    guion = [
        {
            "tipo": "hola",
            "dispositivo": "Mac de Ale",
            "version": "0.1.0",
            "galerias": [{"id": "g1", "nombre": "X", "dia": "2026-06-20", "fotos": 10}],
        },
        _comprobar_y_cortar,
    ]
    ws = _FakeWSGuion({"authorization": "Bearer tok"}, guion)
    anyio.run(fotos_api.tunel, ws)

    assert visto["dispositivos"][0]["dispositivo"] == "Mac de Ale"
    assert visto["dispositivos"][0]["galerias"][0]["id"] == "g1"
    assert fotos_tunel._REGISTRO == {}  # limpio tras desconectar
