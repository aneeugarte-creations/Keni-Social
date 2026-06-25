"""Lado-backend del túnel keni-fotos (fuente «Propio»): dispatcher por MARCA + endpoints HTTP.

OFFLINE y sin red real: el WebSocket de la app se simula con conexiones FAKE que resuelven los
RPC del dispatcher en memoria. El registro es POR MARCA (cruza usuarios). Cubre:
  - registro/fan-out de `fotos_tunel.buscar` por marca, cruzando usuarios (un dispositivo del
    usuario A compartiendo a `m` lo ve una búsqueda hecha para `m`, sea quien sea quien busca),
  - un dispositivo que NO comparte `m` no aparece ni sirve el original de esa marca,
  - `_adjuntar_propio` pide el original (a un dispositivo que comparte la marca), lo SUBE a media
    y lo LIGA como foto propia; sin dispositivo de esa marca da 400,
  - `GET /api/fotos/marcas` exige token de escritorio (Bearer) y devuelve el catálogo,
  - el WebSocket RECHAZA un token inválido (cierra sin registrar), registra con `hola` (incluidas
    sus marcas) y actualiza las marcas en vivo con el mensaje `marcas`; ignora frames no-texto.

Los tests que crean piezas usan la fixture `entorno` (BD de pruebas); el resto corre sin BD.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import anyio

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


class _Req:
    """Request FAKE mínima: solo expone `.headers` (lo que leen los endpoints Bearer)."""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


def _conexion(
    usuario: str,
    responder=None,
    *,
    dispositivo="Mac de Ale",
    galerias=None,
    marcas=("claro-sports",),
):
    """Registra una conexión FAKE de `usuario` que comparte a `marcas` y la devuelve."""
    ws = _FakeWS()
    conexion = fotos_tunel.Conexion(ws, usuario)
    conexion.dispositivo = dispositivo
    conexion.galerias = galerias if galerias is not None else [{"id": "g1"}]
    conexion.marcas = set(marcas)
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
# Dispatcher por marca: registro + fan-out + troceo, cruzando usuarios          #
# --------------------------------------------------------------------------- #


def test_buscar_agrega_y_trocea_a_limite():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("u1", lambda m: _resultado(m, 5), dispositivo="Mac de Ale")
        res = anyio.run(fotos_tunel.buscar, "claro-sports", "portero", 3)
        assert len(res) == 3  # 5 candidatos troceados a `limite`
        assert all(c["dispositivo"] == "Mac de Ale" for c in res)
    finally:
        fotos_tunel._REGISTRO.clear()


def test_buscar_cruza_usuarios_por_marca():
    fotos_tunel._REGISTRO.clear()
    try:
        # Dispositivos de DOS dueños distintos, ambos compartiendo a claro-sports.
        _conexion("ale", lambda m: _resultado(m, 2), dispositivo="Mac de Ale")
        _conexion("ane", lambda m: _resultado(m, 2), dispositivo="Mac de Ane")
        res = anyio.run(fotos_tunel.buscar, "claro-sports", "portero", 10)
        assert len(res) == 4  # 2 + 2: la búsqueda por marca cruza usuarios
        assert {c["dispositivo"] for c in res} == {"Mac de Ale", "Mac de Ane"}
    finally:
        fotos_tunel._REGISTRO.clear()


def test_buscar_excluye_dispositivo_que_no_comparte_la_marca():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("ale", lambda m: _resultado(m, 2), dispositivo="Mac de Ale", marcas=("claro-sports",))
        _conexion("ane", lambda m: _resultado(m, 2), dispositivo="Mac de Ane", marcas=("unotv",))
        res = anyio.run(fotos_tunel.buscar, "claro-sports", "portero", 10)
        assert {c["dispositivo"] for c in res} == {"Mac de Ale"}  # Ane no comparte claro-sports
    finally:
        fotos_tunel._REGISTRO.clear()


def test_buscar_sin_dispositivos_de_la_marca_devuelve_vacio():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("ale", lambda m: _resultado(m, 2), marcas=("unotv",))
        res = anyio.run(fotos_tunel.buscar, "claro-sports", "portero", 4)
        assert res == []
    finally:
        fotos_tunel._REGISTRO.clear()


def test_dispositivos_por_marca_lleva_dueno_y_marcas():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("ale", dispositivo="Mac de Ale", marcas=("claro-sports", "unotv"))
        items = fotos_tunel.dispositivos("claro-sports")
        assert len(items) == 1
        assert items[0]["usuario"] == "ale"
        assert items[0]["dispositivo"] == "Mac de Ale"
        assert items[0]["marcas"] == ["claro-sports", "unotv"]
        assert fotos_tunel.dispositivos("nacion-gamer") == []  # nadie comparte esa marca
    finally:
        fotos_tunel._REGISTRO.clear()


# --------------------------------------------------------------------------- #
# `_buscar_propio` por marca (sin gate a claro-sports)                          #
# --------------------------------------------------------------------------- #


def test_buscar_propio_sin_marca_inerte():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("ale", lambda m: _resultado(m, 3))  # hay dispositivo, pero no se pide marca
        res = anyio.run(artes._buscar_propio, "portero", 4, "")
        assert res["candidatos"] == []
        assert res["proveedores"][0]["disponible"] is False
        assert res["proveedores"][0]["proveedor"] == "propio"
    finally:
        fotos_tunel._REGISTRO.clear()


def test_buscar_propio_marca_sin_dispositivos_inerte():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("ale", lambda m: _resultado(m, 3), marcas=("claro-sports",))
        res = anyio.run(artes._buscar_propio, "portero", 4, "unotv")  # nadie comparte unotv
        assert res["candidatos"] == []
        assert res["proveedores"][0]["disponible"] is False
    finally:
        fotos_tunel._REGISTRO.clear()


def test_buscar_propio_con_dispositivo_devuelve_candidatos():
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion("ale", lambda m: _resultado(m, 2), dispositivo="Mac de Ale")
        # Cualquiera que trabaje claro-sports ve la galería de Ale (registro por marca).
        res = anyio.run(artes._buscar_propio, "portero", 4, "claro-sports")
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
# Adjuntar: pide el original por el túnel (de un dispositivo que comparte marca) #
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
        # Dispositivo de OTRO usuario (ane) compartiendo a claro-sports: la búsqueda/adjuntar de
        # cualquiera que trabaje la marca lo alcanza (registro por marca, cruza usuarios).
        _conexion("ane", _responder_original, galerias=[{"id": "g1", "nombre": "X"}])

        status, cuerpo = anyio.run(
            artes._adjuntar_propio, pid, "g1", "keeper.jpg", "", "claro-sports"
        )
        assert status == 200
        assert cuerpo["plataforma"]["foto"]

        fila = repos.obtener_pieza_fila(pid)
        assert fila["imagen_origen"] == "propia"
        assert bool(fila["falta_imagen"]) is False
        assert fila["foto"]  # objeto subido a media
    finally:
        fotos_tunel._REGISTRO.clear()


def test_adjuntar_propio_no_expone_galeria_a_marca_no_compartida(entorno):
    from keni_consola import repos

    fotos_tunel._REGISTRO.clear()
    try:
        tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="unotv")
        pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
        # El dispositivo solo comparte a claro-sports: adjuntar a una marca distinta no lo alcanza.
        _conexion("ale", _responder_original, marcas=("claro-sports",))
        status, cuerpo = anyio.run(artes._adjuntar_propio, pid, "g1", "keeper.jpg", "", "unotv")
        assert status == 400
        assert "error" in cuerpo
    finally:
        fotos_tunel._REGISTRO.clear()


def test_adjuntar_propio_sin_marca_da_400(entorno):
    from keni_consola import repos

    fotos_tunel._REGISTRO.clear()
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="claro-sports")
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    status, cuerpo = anyio.run(artes._adjuntar_propio, pid, "g1", "keeper.jpg", "", "")
    assert status == 400
    assert "Falta la marca" in cuerpo["error"]


def test_adjuntar_propio_sin_dispositivo_da_400(entorno):
    from keni_consola import repos

    fotos_tunel._REGISTRO.clear()
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="claro-sports")
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    status, cuerpo = anyio.run(
        artes._adjuntar_propio, pid, "g1", "keeper.jpg", "", "claro-sports"
    )
    assert status == 400
    assert "error" in cuerpo


# --------------------------------------------------------------------------- #
# GET /api/fotos/marcas: catálogo para el checklist de la app (auth Bearer)      #
# --------------------------------------------------------------------------- #


def test_marcas_exige_token(monkeypatch):
    monkeypatch.setattr(auth, "token_mcp_valido", lambda t: None)
    resp = anyio.run(fotos_api.marcas_disponibles, _Req({}))  # sin Authorization
    assert resp.status_code == 401


def test_marcas_con_token_devuelve_catalogo(monkeypatch):
    monkeypatch.setattr(
        auth, "token_mcp_valido", lambda t: {"id": "u1", "usuario": "ale", "rol": "editor"}
    )
    resp = anyio.run(fotos_api.marcas_disponibles, _Req({"authorization": "Bearer tok"}))
    assert resp.status_code == 200
    cuerpo = json.loads(resp.body)
    items = cuerpo["marcas"]
    assert items and all("id" in m and "etiqueta" in m for m in items)
    assert any(m["id"] == "claro-sports" for m in items)


# --------------------------------------------------------------------------- #
# WebSocket: auth con el token de escritorio + registro/actualización por marca  #
# --------------------------------------------------------------------------- #


def test_ws_token_invalido_cierra_y_no_registra():
    fotos_tunel._REGISTRO.clear()
    ws = _FakeWS(headers={})  # sin Authorization -> token None -> cierra
    anyio.run(fotos_api.tunel, ws)
    assert ws.aceptado is True
    assert ws.cerrado == 4401
    assert fotos_tunel._REGISTRO == set()


class _FakeWSGuion(_FakeWS):
    """WebSocket FAKE con un GUION de eventos entrantes (estilo ASGI `receive`).

    Cada item del guión puede ser: un mensaje del protocolo (dict -> frame de texto JSON), un
    evento ASGI crudo (dict con `type` `websocket.*`, p.ej. un frame binario sin `text`), o un
    callable (se ejecuta; `None` -> desconexión). Al agotarse, simula la desconexión.
    """

    def __init__(self, headers, guion):
        super().__init__(headers=headers)
        self._guion = list(guion)

    async def receive(self):
        if not self._guion:
            return {"type": "websocket.disconnect", "code": 1000}
        item = self._guion.pop(0)
        if callable(item):
            item = item()
            if item is None:
                return {"type": "websocket.disconnect", "code": 1000}
        if isinstance(item, dict) and str(item.get("type", "")).startswith("websocket."):
            return item
        return {"type": "websocket.receive", "text": json.dumps(item)}


def test_ws_hola_registra_por_marca_y_limpia_al_desconectar(monkeypatch):
    fotos_tunel._REGISTRO.clear()
    monkeypatch.setattr(
        auth, "token_mcp_valido", lambda t: {"id": "u1", "usuario": "ale", "rol": "editor"}
    )
    visto: dict[str, Any] = {}

    def _comprobar_y_cortar():
        # En pleno bucle, la conexión ya está registrada con su `hola` (marcas incluidas).
        visto["claro"] = fotos_tunel.dispositivos("claro-sports")
        visto["unotv"] = fotos_tunel.dispositivos("unotv")
        return None  # -> desconexión

    guion = [
        # Frame de control/binario (sin `text`): el handler debe ignorarlo sin romper.
        {"type": "websocket.receive", "bytes": b"\x09\x01"},
        {
            "tipo": "hola",
            "dispositivo": "Mac de Ale",
            "version": "0.1.0",
            "marcas": ["claro-sports"],
            "galerias": [{"id": "g1", "nombre": "X", "dia": "2026-06-20", "fotos": 10}],
        },
        _comprobar_y_cortar,
    ]
    ws = _FakeWSGuion({"authorization": "Bearer tok"}, guion)
    anyio.run(fotos_api.tunel, ws)

    assert visto["claro"][0]["dispositivo"] == "Mac de Ale"
    assert visto["claro"][0]["usuario"] == "u1"
    assert visto["claro"][0]["galerias"][0]["id"] == "g1"
    assert visto["unotv"] == []  # solo comparte claro-sports
    assert fotos_tunel._REGISTRO == set()  # limpio tras desconectar


def test_ws_mensaje_marcas_actualiza_en_vivo(monkeypatch):
    fotos_tunel._REGISTRO.clear()
    monkeypatch.setattr(
        auth, "token_mcp_valido", lambda t: {"id": "u1", "usuario": "ale", "rol": "editor"}
    )
    visto: dict[str, Any] = {}

    def _comprobar_y_cortar():
        # Tras el mensaje `marcas`, la conexión comparte a unotv (ya no a claro-sports).
        visto["claro"] = fotos_tunel.dispositivos("claro-sports")
        visto["unotv"] = fotos_tunel.dispositivos("unotv")
        return None

    guion = [
        {"tipo": "hola", "dispositivo": "Mac de Ale", "marcas": ["claro-sports"], "galerias": []},
        {"tipo": "marcas", "marcas": ["unotv"]},
        _comprobar_y_cortar,
    ]
    ws = _FakeWSGuion({"authorization": "Bearer tok"}, guion)
    anyio.run(fotos_api.tunel, ws)

    assert visto["claro"] == []  # ya no comparte claro-sports
    assert visto["unotv"][0]["dispositivo"] == "Mac de Ale"
    assert fotos_tunel._REGISTRO == set()


def test_procesar_mensaje_marcas_actualiza_conexion():
    fotos_tunel._REGISTRO.clear()
    try:
        conexion = _conexion("u1", marcas=("claro-sports",))
        fotos_api._procesar_mensaje(conexion, {"tipo": "marcas", "marcas": ["unotv", "nacion-gamer"]})
        assert conexion.marcas == {"unotv", "nacion-gamer"}
    finally:
        fotos_tunel._REGISTRO.clear()
