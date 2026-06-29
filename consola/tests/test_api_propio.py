"""Lado-backend del túnel keni-fotos (fuente «Propio»): registro COMPARTIDO + bus RPC cross-worker.

OFFLINE pero sobre Postgres (el registro y el bus viven en tablas): el WebSocket de la app se
simula con conexiones FAKE que resuelven los RPC en memoria. El registro es POR MARCA (cruza
usuarios) y vive en `tunel_conexiones`; las llamadas (`buscar`/`original`/`rafaga`) se encolan en
`tunel_rpc` y las ejecuta el worker que tiene el WebSocket en memoria. Cubre:
  - registro en tabla (alta/heartbeat/baja) y barrido de conexiones muertas (stale),
  - `dispositivos_registrados` = usuarios con token de escritorio + flag `online`, cruzando workers,
  - fan-out de `buscar` por marca cruzando usuarios; exclusión de quien no comparte la marca,
  - RPC enrutado a OTRO worker (la fila vive con `worker` ajeno; el dueño la ejecuta al recibirla),
  - payload GRANDE (original en base64 de ~2 MB) viajando por la columna `resultado`,
  - `_adjuntar_propio` pide el original (de un dispositivo que comparte la marca), lo SUBE y lo LIGA,
  - `GET /api/fotos/marcas` (auth Bearer) y el WebSocket (auth + registro/actualización por marca).

Casi todos los tests usan la fixture `entorno` (Postgres): el registro/bus son tablas.
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import pytest
from starlette.concurrency import run_in_threadpool

from keni_consola import auth, fotos_tunel, repos
from keni_consola.api import artes
from keni_consola.api import fotos as fotos_api
from keni_consola.tiempo import ahora_iso, iso_utc

# PNG 1x1 válido: el original que la app «manda» por el túnel (base64).
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_CLAVE = "Xx12345!abcd"


@pytest.fixture(autouse=True)
def _limpiar_conexiones_locales():
    """El mapa de WebSockets en memoria (`_CONEXIONES`) es global del proceso: aíslalo por test."""
    fotos_tunel._CONEXIONES.clear()
    fotos_tunel._EN_CURSO.clear()
    yield
    fotos_tunel._CONEXIONES.clear()
    fotos_tunel._EN_CURSO.clear()


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
    """Registra una conexión FAKE de `usuario` (WS LOCAL + fila en `tunel_conexiones`)."""
    conexion = _construir_conexion(
        usuario, responder, dispositivo=dispositivo, galerias=galerias, marcas=marcas
    )
    anyio.run(fotos_tunel.registrar, conexion)
    return conexion


def _conexion_remota(
    usuario: str,
    responder=None,
    *,
    dispositivo="Mac de Ale",
    galerias=None,
    marcas=("claro-sports",),
    worker="otro-host:999",
):
    """Conexión cuyo WebSocket vive en OTRO worker: solo la fila en `tunel_conexiones` (no local)."""
    conexion = _construir_conexion(
        usuario, responder, dispositivo=dispositivo, galerias=galerias, marcas=marcas
    )
    repos.tunel_upsert_conexion(
        id=conexion.id,
        worker=worker,
        usuario=usuario,
        dispositivo=conexion.dispositivo,
        version="",
        marcas=json.dumps(sorted(conexion.marcas)),
        galerias=json.dumps(conexion.galerias),
        visto_en=ahora_iso(),
    )
    return conexion


def _construir_conexion(usuario, responder, *, dispositivo, galerias, marcas):
    ws = _FakeWS()
    conexion = fotos_tunel.Conexion(ws, usuario)
    conexion.dispositivo = dispositivo
    conexion.galerias = galerias if galerias is not None else [{"id": "g1"}]
    conexion.marcas = set(marcas)
    ws.conexion = conexion
    ws.responder = responder
    return conexion


async def _esperar_pendientes(n):
    """Espera a que el peticionario haya encolado `n` RPC en `tunel_rpc` (aún sin worker local)."""
    for _ in range(500):
        filas = await run_in_threadpool(repos.tunel_rpc_pendientes)
        if len(filas) >= n:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("no aparecieron los RPC pendientes esperados")


async def _ejecutar_como_dueno(tarea, *conexiones):
    """El worker dueño recibe los WebSockets en memoria y drena el bus hasta cerrar la petición."""
    for c in conexiones:
        fotos_tunel._CONEXIONES[c.id] = c
    while not tarea.done():
        await fotos_tunel._pasada_local()
        await asyncio.sleep(0.02)
    return await tarea


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


# --------------------------------------------------------------------------- #
# Registro compartido en `tunel_conexiones`: alta / heartbeat / baja / stale     #
# --------------------------------------------------------------------------- #


def test_registro_alta_heartbeat_y_baja(entorno):
    conexion = _conexion("ale", marcas=("claro-sports",))
    vivas = repos.tunel_conexiones_vivas(fotos_tunel._umbral_vivo())
    assert any(v["id"] == conexion.id for v in vivas)

    anyio.run(fotos_tunel.latido, conexion)  # heartbeat: la fila sigue viva
    assert any(
        v["id"] == conexion.id
        for v in repos.tunel_conexiones_vivas(fotos_tunel._umbral_vivo())
    )

    anyio.run(fotos_tunel.desregistrar, conexion)  # baja: borra la fila
    assert all(
        v["id"] != conexion.id
        for v in repos.tunel_conexiones_vivas(fotos_tunel._umbral_vivo())
    )


def test_conexion_stale_se_ignora_y_se_barre(entorno):
    viejo = iso_utc(datetime.now(UTC) - timedelta(seconds=600))  # > TTL (90 s)
    repos.tunel_upsert_conexion(
        id="muerta",
        worker="caido:1",
        usuario="ale",
        dispositivo="Mac de Ale",
        version="",
        marcas=json.dumps(["claro-sports"]),
        galerias="[]",
        visto_en=viejo,
    )
    # La lectura ignora la fila muerta y la barre de paso.
    assert fotos_tunel.conexiones_de_marca("claro-sports") == []
    assert repos.tunel_conexiones_vivas(fotos_tunel._umbral_vivo()) == []


# --------------------------------------------------------------------------- #
# `dispositivos_registrados`: registrados + online, cruzando workers             #
# --------------------------------------------------------------------------- #


def test_dispositivos_registrados_online_offline_cruza_workers(entorno):
    ale = auth.crear_usuario("ale", _CLAVE, "editor")
    ane = auth.crear_usuario("ane", _CLAVE, "editor")
    bob = auth.crear_usuario("bob", _CLAVE, "editor")
    for u in (ale, ane, bob):
        auth.crear_token_mcp(u["id"], fotos_tunel.ETIQUETA_ESCRITORIO)

    # ale conectado en el "worker A", ane en el "worker B", bob registrado pero offline.
    repos.tunel_upsert_conexion(
        id="cA", worker="hostA:1", usuario=ale["id"], dispositivo="Mac de Ale",
        version="", marcas=json.dumps(["claro-sports"]), galerias="[]", visto_en=ahora_iso(),
    )
    repos.tunel_upsert_conexion(
        id="cB", worker="hostB:1", usuario=ane["id"], dispositivo="Mac de Ane",
        version="", marcas=json.dumps(["unotv"]), galerias="[]", visto_en=ahora_iso(),
    )

    por = {i["usuario"]: i for i in fotos_tunel.dispositivos_registrados()}
    assert por[ale["id"]]["online"] is True
    assert por[ale["id"]]["dispositivo"] == "Mac de Ale"
    assert por[ale["id"]]["marcas"] == ["claro-sports"]
    assert por[ane["id"]]["online"] is True
    assert por[ane["id"]]["dispositivo"] == "Mac de Ane"
    assert por[bob["id"]]["online"] is False
    assert "dispositivo" not in por[bob["id"]]  # offline -> solo {usuario, online}


def test_dispositivos_registrados_no_filtra_por_marca(entorno):
    """El listado es de QUIÉN está registrado/online, no de quién comparte una marca dada."""
    ale = auth.crear_usuario("ale", _CLAVE, "editor")
    auth.crear_token_mcp(ale["id"], fotos_tunel.ETIQUETA_ESCRITORIO)
    repos.tunel_upsert_conexion(
        id="cA", worker="hostA:1", usuario=ale["id"], dispositivo="Mac de Ale",
        version="", marcas=json.dumps(["unotv"]), galerias="[]", visto_en=ahora_iso(),
    )
    items = fotos_tunel.dispositivos_registrados()
    assert [i["usuario"] for i in items] == [ale["id"]]
    assert items[0]["online"] is True  # aparece aunque solo comparta unotv


# --------------------------------------------------------------------------- #
# Fan-out de `buscar` por marca (cruza usuarios), vía el bus de RPC               #
# --------------------------------------------------------------------------- #


def test_buscar_agrega_y_trocea_a_limite(entorno):
    _conexion("u1", lambda m: _resultado(m, 5), dispositivo="Mac de Ale")
    res = anyio.run(fotos_tunel.buscar, "claro-sports", "portero", 3)
    assert len(res) == 3  # 5 candidatos troceados a `limite`
    assert all(c["dispositivo"] == "Mac de Ale" for c in res)


def test_buscar_cruza_usuarios_por_marca(entorno):
    _conexion("ale", lambda m: _resultado(m, 2), dispositivo="Mac de Ale")
    _conexion("ane", lambda m: _resultado(m, 2), dispositivo="Mac de Ane")
    res = anyio.run(fotos_tunel.buscar, "claro-sports", "portero", 10)
    assert len(res) == 4  # 2 + 2: la búsqueda por marca cruza usuarios
    assert {c["dispositivo"] for c in res} == {"Mac de Ale", "Mac de Ane"}


def test_buscar_excluye_dispositivo_que_no_comparte_la_marca(entorno):
    _conexion("ale", lambda m: _resultado(m, 2), dispositivo="Mac de Ale", marcas=("claro-sports",))
    _conexion("ane", lambda m: _resultado(m, 2), dispositivo="Mac de Ane", marcas=("unotv",))
    res = anyio.run(fotos_tunel.buscar, "claro-sports", "portero", 10)
    assert {c["dispositivo"] for c in res} == {"Mac de Ale"}  # Ane no comparte claro-sports


def test_buscar_sin_dispositivos_de_la_marca_devuelve_vacio(entorno):
    _conexion("ale", lambda m: _resultado(m, 2), marcas=("unotv",))
    res = anyio.run(fotos_tunel.buscar, "claro-sports", "portero", 4)
    assert res == []


# --------------------------------------------------------------------------- #
# RPC enrutado a OTRO worker + payload grande en `resultado`                      #
# --------------------------------------------------------------------------- #


def test_rpc_original_se_enruta_al_worker_dueno(entorno):
    """La fila vive con un `worker` ajeno; el dueño la recibe en memoria y la ejecuta vía la tabla."""
    conexion = _conexion_remota("ane", _responder_original, galerias=[{"id": "g1", "nombre": "X"}])

    async def escenario():
        tarea = asyncio.create_task(fotos_tunel.pedir_original("claro-sports", "g1", "keeper.jpg"))
        await _esperar_pendientes(1)  # el peticionario encoló el RPC SIN tener el WS local
        return await _ejecutar_como_dueno(tarea, conexion)

    datos, mime = anyio.run(escenario)
    assert datos == _PNG_1x1
    assert mime == "image/png"


def test_rpc_buscar_fan_out_cross_worker(entorno):
    c1 = _conexion_remota("ale", lambda m: _resultado(m, 2), dispositivo="Mac de Ale")
    c2 = _conexion_remota("ane", lambda m: _resultado(m, 2), dispositivo="Mac de Ane")

    async def escenario():
        tarea = asyncio.create_task(fotos_tunel.buscar("claro-sports", "portero", 10))
        await _esperar_pendientes(2)  # fan-out: un RPC encolado por cada dispositivo de la marca
        return await _ejecutar_como_dueno(tarea, c1, c2)

    res = anyio.run(escenario)
    assert len(res) == 4
    assert {c["dispositivo"] for c in res} == {"Mac de Ale", "Mac de Ane"}


def test_rpc_payload_grande_viaja_por_resultado(entorno):
    grande = base64.b64encode(b"\xff" * 2_000_000).decode("ascii")  # original de ~2 MB

    def responder(msg):
        if msg.get("tipo") != "original":
            return None
        return {"tipo": "original_datos", "id": msg["id"], "mime": "image/jpeg", "datos_b64": grande}

    conexion = _conexion_remota("ale", responder, galerias=[{"id": "g1", "nombre": "X"}])

    async def escenario():
        tarea = asyncio.create_task(fotos_tunel.pedir_original("claro-sports", "g1", "big.jpg"))
        await _esperar_pendientes(1)
        return await _ejecutar_como_dueno(tarea, conexion)

    datos, mime = anyio.run(escenario)
    assert len(datos) == 2_000_000
    assert mime == "image/jpeg"


# --------------------------------------------------------------------------- #
# Pub/sub LOCAL del SSE de la Galería (sin BD)                                    #
# --------------------------------------------------------------------------- #


def test_manejar_notify_traduce_cada_canal():
    """El listener traduce cada NOTIFY a su efecto local (SSE / ejecutar RPC / despertar waiters)."""
    cola = fotos_tunel.suscribir()
    try:
        async def run():
            await fotos_tunel._manejar_notify("tunel_cambio", "")  # re-empuja el SSE local
            assert cola.get_nowait() is None
            # Sin conexiones locales, `tunel_rpc` no toca la BD ni lanza; `tunel_rpc_done` despierta.
            await fotos_tunel._manejar_notify("tunel_rpc", "x")
            await fotos_tunel._manejar_notify("tunel_rpc_done", "x")

        anyio.run(run)
    finally:
        fotos_tunel.desuscribir(cola)


def test_pubsub_local_avisos_colapsan_en_uno():
    cola = fotos_tunel.suscribir()
    try:
        assert cola.empty()
        fotos_tunel._notificar_cambio()
        assert cola.get_nowait() is None
        fotos_tunel._notificar_cambio()
        fotos_tunel._notificar_cambio()
        assert cola.get_nowait() is None  # varios cambios -> un único aviso pendiente
        assert cola.empty()
    finally:
        fotos_tunel.desuscribir(cola)


# --------------------------------------------------------------------------- #
# `_buscar_propio` por marca (sin gate a claro-sports)                          #
# --------------------------------------------------------------------------- #


def test_buscar_propio_sin_marca_inerte(entorno):
    _conexion("ale", lambda m: _resultado(m, 3))  # hay dispositivo, pero no se pide marca
    res = anyio.run(artes._buscar_propio, "portero", 4, "")
    assert res["candidatos"] == []
    assert res["proveedores"][0]["disponible"] is False
    assert res["proveedores"][0]["proveedor"] == "propio"


def test_buscar_propio_marca_sin_dispositivos_inerte(entorno):
    _conexion("ale", lambda m: _resultado(m, 3), marcas=("claro-sports",))
    res = anyio.run(artes._buscar_propio, "portero", 4, "unotv")  # nadie comparte unotv
    assert res["candidatos"] == []
    assert res["proveedores"][0]["disponible"] is False


def test_buscar_propio_con_dispositivo_devuelve_candidatos(entorno):
    _conexion("ale", lambda m: _resultado(m, 2), dispositivo="Mac de Ale")
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
    assert cand["grupo"] == "Colombia vs Uzbekistán"


# --------------------------------------------------------------------------- #
# Listar una galería (carpeta de partido) por el túnel: RPC `galeria`            #
# --------------------------------------------------------------------------- #


def _responder_galeria(msg, n):
    """Responde al RPC `galeria` (lista de keepers) con la MISMA forma que `buscar` (`resultado`)."""
    if msg.get("tipo") != "galeria":
        return None
    return _resultado(msg, n)


def test_galeria_lista_keepers_de_una_galeria(entorno):
    _conexion(
        "ale", lambda m: _responder_galeria(m, 3),
        dispositivo="Mac de Ale", galerias=[{"id": "g1", "nombre": "X"}],
    )
    res = anyio.run(fotos_tunel.galeria, "claro-sports", "g1", "", 120)
    assert len(res) == 3  # lista la galería entera (no exige query)
    assert all(c["dispositivo"] == "Mac de Ale" for c in res)
    assert res[0]["galeria_id"] == "g1"


def test_galeria_sin_dispositivo_de_la_marca_vacio(entorno):
    _conexion("ale", lambda m: _responder_galeria(m, 2), marcas=("unotv",))
    res = anyio.run(fotos_tunel.galeria, "claro-sports", "g1", "", 120)
    assert res == []  # nadie comparte claro-sports


def test_galeria_propio_endpoint_mapea_candidatos(entorno):
    _conexion(
        "ale", lambda m: _responder_galeria(m, 2),
        dispositivo="Mac de Ale", galerias=[{"id": "g1", "nombre": "X"}],
    )
    res = anyio.run(artes._galeria_propio, "g1", "", 120, "claro-sports")
    cands = res["candidatos"]
    assert len(cands) == 2
    assert cands[0]["proveedor"] == "propio"
    assert cands[0]["galeria_id"] == "g1"
    assert cands[0]["dispositivo"] == "Mac de Ale"


def test_galeria_propio_sin_marca_vacio(entorno):
    res = anyio.run(artes._galeria_propio, "g1", "", 120, "")
    assert res["candidatos"] == []


# --------------------------------------------------------------------------- #
# Etiquetas IA del túnel: se extraen del label y se conservan en el candidato   #
# --------------------------------------------------------------------------- #


def test_etiquetas_de_label_extrae_tags_equipos_y_contexto():
    label = {
        "tags": ["celebración", "afición"],
        "equipos": ["Colombia"],
        "deporte": "fútbol",
        "momento": "post-gol",
        "en_foco": "niño con pintura",
    }
    ets = artes._etiquetas_de_label(label)
    assert "celebración" in ets and "Colombia" in ets and "fútbol" in ets
    assert "niño con pintura" in ets


def test_etiquetas_de_label_tolera_ausente_o_mal_formado():
    assert artes._etiquetas_de_label(None) == []
    assert artes._etiquetas_de_label("texto") == []
    assert artes._etiquetas_de_label({"tags": "no-es-lista"}) == []


def test_candidato_propio_conserva_etiquetas_del_label():
    crudo = {
        "galeria_id": "g1", "archivo": "k.jpg", "thumb_b64": "x",
        "nombre": "Colombia", "fase": "in-game", "en_foco": "portero",
        "label": {"tags": ["atajada"], "equipos": ["Colombia"]},
    }
    cand = artes._candidato_propio(crudo)
    assert "atajada" in cand["etiquetas"]
    assert "Colombia" in cand["etiquetas"]
    assert cand["grupo"] == "Colombia"


def test_candidato_propio_sin_label_etiquetas_vacias():
    cand = artes._candidato_propio({"galeria_id": "g1", "archivo": "k.jpg"})
    assert cand["etiquetas"] == []
    assert cand["grupo"] == ""


# --------------------------------------------------------------------------- #
# Adjuntar: pide el original por el túnel (de un dispositivo que comparte marca) #
# --------------------------------------------------------------------------- #


def test_adjuntar_propio_pide_original_sube_y_liga(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="claro-sports")
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    # Dispositivo de OTRO usuario (ane) compartiendo a claro-sports: lo alcanza por marca.
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


def test_adjuntar_propio_no_expone_galeria_a_marca_no_compartida(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="unotv")
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    _conexion("ale", _responder_original, marcas=("claro-sports",))
    status, cuerpo = anyio.run(artes._adjuntar_propio, pid, "g1", "keeper.jpg", "", "unotv")
    assert status == 400
    assert "error" in cuerpo


def test_adjuntar_propio_sin_marca_da_400(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="claro-sports")
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    status, cuerpo = anyio.run(artes._adjuntar_propio, pid, "g1", "keeper.jpg", "", "")
    assert status == 400
    assert "Falta la marca" in cuerpo["error"]


def test_adjuntar_propio_sin_dispositivo_da_400(entorno):
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


def test_ws_token_invalido_cierra_y_no_registra(monkeypatch):
    monkeypatch.setattr(auth, "token_mcp_valido", lambda t: None)
    ws = _FakeWS(headers={})  # sin Authorization -> token None -> cierra
    anyio.run(fotos_api.tunel, ws)
    assert ws.aceptado is True
    assert ws.cerrado == 4401
    assert fotos_tunel._CONEXIONES == {}


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


def test_ws_hola_registra_por_marca_y_limpia_al_desconectar(entorno, monkeypatch):
    monkeypatch.setattr(
        auth, "token_mcp_valido", lambda t: {"id": "u1", "usuario": "ale", "rol": "editor"}
    )
    visto: dict[str, Any] = {}

    def _comprobar_y_cortar():
        # En pleno bucle, la conexión ya está registrada con su `hola` (marcas incluidas).
        visto["claro"] = fotos_tunel.conexiones_de_marca("claro-sports")
        visto["unotv"] = fotos_tunel.conexiones_de_marca("unotv")
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
    assert fotos_tunel._CONEXIONES == {}  # limpio tras desconectar


def test_ws_mensaje_marcas_actualiza_en_vivo(entorno, monkeypatch):
    monkeypatch.setattr(
        auth, "token_mcp_valido", lambda t: {"id": "u1", "usuario": "ale", "rol": "editor"}
    )
    visto: dict[str, Any] = {}

    def _comprobar_y_cortar():
        # Tras el mensaje `marcas`, la conexión comparte a unotv (ya no a claro-sports).
        visto["claro"] = fotos_tunel.conexiones_de_marca("claro-sports")
        visto["unotv"] = fotos_tunel.conexiones_de_marca("unotv")
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
    assert fotos_tunel._CONEXIONES == {}


def test_procesar_mensaje_marcas_actualiza_conexion(entorno):
    conexion = _conexion("u1", marcas=("claro-sports",))
    anyio.run(
        fotos_api._procesar_mensaje,
        conexion,
        {"tipo": "marcas", "marcas": ["unotv", "nacion-gamer"]},
    )
    assert conexion.marcas == {"unotv", "nacion-gamer"}
    # La fila compartida refleja el cambio (cualquier worker la vería en unotv, no en claro-sports).
    assert fotos_tunel.conexiones_de_marca("claro-sports") == []
    assert any(c["id"] == conexion.id for c in fotos_tunel.conexiones_de_marca("unotv"))
