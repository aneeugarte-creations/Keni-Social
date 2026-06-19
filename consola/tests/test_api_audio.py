"""Tests de la API del gestor de AUDIO (/api/audio/*). OFFLINE: NUNCA toca whisper/ffmpeg/red.

Cubre: subir+crear+encolar (mockeado), CRUD de transcripciones, validaciones (400/404) y el
lanzamiento de agentes de Claude (mockeando `prompts_lanzar.lanzar`).

El encolado del ASR (`generaciones.encolar_job_proceso`), la subida de media
(`media.guardar_audio_subida`) y el lanzamiento de agentes (`prompts_lanzar.lanzar`) se
MONKEYPATCHEAN: solo verificamos que la API los invoca con los params correctos.
"""

from __future__ import annotations

from keni_consola import generaciones, media, repos
from keni_consola.dominio import jobspec, prompts_lanzar

_MARCA = "unotv"


def _mock_subida_y_cola(monkeypatch, capturado: dict, *, clave="audios/abc.mp3"):
    async def fake_guardar(archivo, **k):
        return clave

    def fake_encolar(*, kind, params, marca=None, etiqueta=None):
        capturado.update(kind=kind, params=params, marca=marca)
        return {"id": "gen-asr-1"}

    monkeypatch.setattr(media, "guardar_audio_subida", fake_guardar)
    monkeypatch.setattr(generaciones, "encolar_job_proceso", fake_encolar)


def _crear(cliente, *, marca=_MARCA, nombre="grabacion.mp3"):
    return cliente.post(
        "/api/audio/transcripciones",
        files={"archivo": (nombre, b"audio-bytes", "audio/mpeg")},
        data={"marca": marca, "nombre": nombre},
    )


# --------------------------------------------------------------------------- #
# Crear (sube + crea + encola)                                                 #
# --------------------------------------------------------------------------- #


def test_crear_sube_crea_y_encola(cliente, monkeypatch):
    capturado: dict = {}
    _mock_subida_y_cola(monkeypatch, capturado, clave="audios/abc.mp3")

    r = _crear(cliente)
    assert r.status_code == 201
    body = r.json()
    assert body["gen_id"] == "gen-asr-1"
    t = body["transcripcion"]
    assert t["estado"] == "pendiente" and t["media_id"] == "audios/abc.mp3"
    assert t["marca"] == _MARCA and t["nombre"] == "grabacion.mp3"

    # Encola el job de proceso del motor de audio con los params correctos.
    assert capturado["kind"] == jobspec.PROC_TRANSCRIBIR_AUDIO
    assert capturado["params"]["transcripcion_id"] == t["id"]
    assert capturado["params"]["media_id"] == "audios/abc.mp3"

    # La fila quedó persistida.
    assert repos.obtener_audio_transcripcion(t["id"]) is not None


def test_crear_sin_marca_400(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    r = cliente.post(
        "/api/audio/transcripciones",
        files={"archivo": ("x.mp3", b"bytes", "audio/mpeg")},
        data={"marca": ""},
    )
    assert r.status_code == 400


def test_crear_marca_invalida_400(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    r = _crear(cliente, marca="no-existe")
    assert r.status_code == 400


def test_crear_sin_archivo_400(cliente):
    r = cliente.post("/api/audio/transcripciones", data={"marca": _MARCA})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# CRUD                                                                          #
# --------------------------------------------------------------------------- #


def test_listar_y_obtener(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]

    r = cliente.get("/api/audio/transcripciones", params={"marca": _MARCA})
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["transcripciones"]]
    assert tid in ids

    r2 = cliente.get(f"/api/audio/transcripciones/{tid}")
    assert r2.status_code == 200
    assert r2.json()["transcripcion"]["id"] == tid

    assert cliente.get("/api/audio/transcripciones/no-existe").status_code == 404


def test_actualizar_texto_y_estado(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]

    r = cliente.put(
        f"/api/audio/transcripciones/{tid}",
        json={"texto": "texto corregido", "estado": "editado"},
    )
    assert r.status_code == 200
    t = r.json()["transcripcion"]
    assert t["texto"] == "texto corregido" and t["estado"] == "editado"


def test_actualizar_estado_invalido_400(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    r = cliente.put(f"/api/audio/transcripciones/{tid}", json={"estado": "publicado"})
    assert r.status_code == 400


def test_borrar(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    assert cliente.delete(f"/api/audio/transcripciones/{tid}").status_code == 204
    assert cliente.get(f"/api/audio/transcripciones/{tid}").status_code == 404
    assert cliente.delete(f"/api/audio/transcripciones/{tid}").status_code == 404


# --------------------------------------------------------------------------- #
# Agentes de Claude                                                            #
# --------------------------------------------------------------------------- #


def test_agente_operacion_invalida_400(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    r = cliente.post(f"/api/audio/transcripciones/{tid}/agente", json={"operacion": "traducir"})
    assert r.status_code == 400


def test_agente_sin_texto_400(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    # Recién creada no tiene segmentos ni texto.
    r = cliente.post(f"/api/audio/transcripciones/{tid}/agente", json={"operacion": "limpiar"})
    assert r.status_code == 400


def test_agente_limpiar_lanza_prompt(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    # Le damos texto para que haya bloque de contexto.
    cliente.put(f"/api/audio/transcripciones/{tid}", json={"texto": "eh hola hola mundo"})

    capturado: dict = {}

    def fake_lanzar(*, prompt_id, marca, bloque_contexto, autor=None):
        capturado.update(prompt_id=prompt_id, marca=marca, bloque=bloque_contexto)
        return {"id": "gen-agente-1"}

    monkeypatch.setattr(prompts_lanzar, "lanzar", fake_lanzar)

    r = cliente.post(f"/api/audio/transcripciones/{tid}/agente", json={"operacion": "limpiar"})
    assert r.status_code == 200
    assert r.json()["gen_id"] == "gen-agente-1"
    assert capturado["prompt_id"] == "prompt/audio/limpiar"
    assert capturado["marca"] == _MARCA
    assert "hola" in capturado["bloque"]
