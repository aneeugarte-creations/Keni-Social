"""Tests del sistema de GENERACIONES (trabajos de IA en background, seguibles en vivo).

TODO OFFLINE: NUNCA se llama a `claude` ni a un proveedor de imagen real.

Cubre:
  - `AcumuladorStream` en modo PARCIAL (`--include-partial-messages`): texto token a
    token (`text_delta`), turnos por `message_start`, `thinking` ignorado.
  - Store de generaciones (crear/obtener/actualizar/listar) aislado en tmp.
  - Endpoints `GET /api/generaciones` y `GET /api/generaciones/{id}`.
  - El POST a `/api/skills/ejecutar` con el lanzador por defecto (noop) deja la
    generacion en `ejecutando` (no bloquea, sin resultado todavia) y es sondeable.
  - El lanzador de imagen completa la generacion con su `resultado`.
"""

from __future__ import annotations

import json

from keni_consola import generaciones
from keni_consola.api import skills

from .conftest import _cliente

_MARCA = "unotv"

# Referencia GENUINA al lanzador de imagen real: otros tests crean la app con un lanzador
# FAKE inyectado (crear_app reasigna el atributo de modulo), que persistiria. Los tests que
# ejercitan el lanzador REAL lo invocan por esta referencia capturada al importar.
_LANZAR_IMAGEN_REAL = generaciones.lanzar_job_imagen


# --------------------------------------------------------------------------- #
# AcumuladorStream: streaming token a token (eventos `stream_event`)          #
# --------------------------------------------------------------------------- #


def _se(event: dict) -> str:
    """Serializa un `stream_event` NDJSON (modo --include-partial-messages)."""
    return json.dumps({"type": "stream_event", "event": event})


def test_acumulador_streaming_texto_token_a_token():
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_se({"type": "message_start", "message": {"model": "claude-haiku-4-5"}}))
    # thinking NO debe acumularse en el texto del copy.
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "thinking_delta", "thinking": "pensando..."}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 1,
                            "delta": {"type": "text_delta", "text": "Hola "}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 1,
                            "delta": {"type": "text_delta", "text": "mundo"}}))
    acc.procesar_linea(_se({"type": "message_delta",
                            "usage": {"input_tokens": 10, "output_tokens": 5}}))

    assert acc.iniciado is True
    assert acc.texto == "Hola mundo"  # solo el texto, no el thinking
    assert "pensando" not in acc.texto
    assert acc.turnos == 1  # un solo message_start
    assert acc.modelo == "claude-haiku-4-5"
    parc = acc.metricas_parciales()
    assert parc is not None and parc.tokens_out == 5


def test_acumulador_parcial_no_recuenta_turnos_desde_assistant():
    """En modo parcial los turnos los cuenta `message_start`; un `assistant` posterior
    (que el CLI tambien emite) NO debe sumar otro turno."""
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_se({"type": "message_start", "message": {}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": "ok"}}))
    acc.procesar_linea(json.dumps({"type": "assistant",
                                   "message": {"usage": {"input_tokens": 9, "output_tokens": 9}}}))
    assert acc.turnos == 1  # no 2


# --------------------------------------------------------------------------- #
# Store de generaciones                                                       #
# --------------------------------------------------------------------------- #


def test_store_crear_obtener_actualizar_listar(entorno):
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Copy desde nota"})
    gid = g["id"]
    assert g["estado"] == "ejecutando"
    assert g["fecha_inicio"]
    assert g["resultado"] is None

    leido = generaciones.obtener(gid)
    assert leido is not None and leido["etiqueta"] == "Copy desde nota"

    generaciones.actualizar(gid, {"estado": "completado", "salida": "hey",
                                  "resultado": {"piezas": [{"red": "x"}]}})
    g2 = generaciones.obtener(gid)
    assert g2["estado"] == "completado"
    assert g2["salida"] == "hey"
    assert g2["resultado"] == {"piezas": [{"red": "x"}]}

    assert any(x["id"] == gid for x in generaciones.listar())
    assert generaciones.obtener("noexiste") is None


def test_store_id_invalido_no_escapa(entorno):
    # Un id con separadores / .. no debe resolver (anti-traversal).
    assert generaciones.obtener("../secreto") is None
    assert generaciones.obtener("a/b") is None


# --------------------------------------------------------------------------- #
# Endpoints de sondeo                                                         #
# --------------------------------------------------------------------------- #


def test_get_generacion_404_si_no_existe(entorno):
    r = _cliente().get("/api/generaciones/noexiste")
    assert r.status_code == 404


def test_get_y_listar_generaciones(entorno):
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    cli = _cliente()
    r = cli.get(f"/api/generaciones/{g['id']}")
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == g["id"]
    lista = cli.get("/api/generaciones").json()["generaciones"]
    assert any(x["id"] == g["id"] for x in lista)


def test_ejecutar_lanza_en_background_y_queda_ejecutando(entorno):
    """Con el lanzador por defecto (noop) la generacion queda `ejecutando`, sondeable."""
    cli = _cliente()  # lanzador de generacion por defecto = noop (no claude)
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": _MARCA, "texto": "una nota"},
    )
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["tipo"] == "copy"
    assert gen["estado"] == "ejecutando"
    assert gen["resultado"] is None
    # Sondeable por su id.
    r2 = cli.get(f"/api/generaciones/{gen['id']}")
    assert r2.status_code == 200
    assert r2.json()["generacion"]["estado"] == "ejecutando"


# --------------------------------------------------------------------------- #
# Lanzador de imagen (background, sin red)                                    #
# --------------------------------------------------------------------------- #


def test_lanzar_job_imagen_completa(entorno):
    gid = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": "Imagen"})["id"]
    _LANZAR_IMAGEN_REAL(
        gid, generar=lambda: {"id": "x.png", "url": "/api/media/x.png"}
    )
    # El handle se suelta DESPUES de fijar el estado terminal; si sigue, lo esperamos.
    with generaciones._HANDLES_LOCK:
        handle = generaciones._HANDLES.get(gid)
    if handle is not None:
        handle["hilo"].join(timeout=5)
    g = generaciones.obtener(gid)
    assert g["estado"] == "completado"
    assert g["resultado"] == {"id": "x.png", "url": "/api/media/x.png"}


def test_lanzar_job_imagen_error(entorno):
    gid = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": "Imagen"})["id"]

    def _falla() -> dict:
        raise RuntimeError("proveedor caído")

    _LANZAR_IMAGEN_REAL(gid, generar=_falla)
    with generaciones._HANDLES_LOCK:
        handle = generaciones._HANDLES.get(gid)
    if handle is not None:
        handle["hilo"].join(timeout=5)
    g = generaciones.obtener(gid)
    assert g["estado"] == "error"
    assert "proveedor" in g["error"].lower()
