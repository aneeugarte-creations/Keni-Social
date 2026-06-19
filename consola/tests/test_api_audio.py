"""Tests de la API del gestor de AUDIO (/api/audio/*). OFFLINE: NUNCA toca whisper/ffmpeg/red.

Cubre: subir+crear+encolar (con tratamientos), huérfano en 429, CRUD de audios, y los ARTEFACTOS
(lanzar tratamiento, editar, SRT no editable, borrar, corregir). El encolado del ASR, la subida de
media y el lanzamiento de tratamientos de Claude se MONKEYPATCHEAN.
"""

from __future__ import annotations

from keni_consola import generaciones, media, repos
from keni_consola.dominio import audio_artefactos, jobspec

_MARCA = "unotv"


def _mock_subida_y_cola(monkeypatch, capturado: dict, *, clave="audios/abc.mp3"):
    async def fake_guardar(archivo, **k):
        return clave

    def fake_encolar(*, kind, params, marca=None, etiqueta=None):
        capturado.update(kind=kind, params=params, marca=marca)
        return {"id": "gen-asr-1"}

    monkeypatch.setattr(media, "guardar_audio_subida", fake_guardar)
    monkeypatch.setattr(generaciones, "encolar_job_proceso", fake_encolar)


def _crear(cliente, *, marca=_MARCA, nombre="grabacion.mp3", tratamientos=None):
    data = {"marca": marca, "nombre": nombre}
    if tratamientos is not None:
        data["tratamientos"] = tratamientos
    return cliente.post(
        "/api/audio/transcripciones",
        files={"archivo": (nombre, b"audio-bytes", "audio/mpeg")},
        data=data,
    )


# --------------------------------------------------------------------------- #
# Crear (sube + crea + encola, con tratamientos)                               #
# --------------------------------------------------------------------------- #


def test_crear_sube_crea_y_encola_con_tratamientos(cliente, monkeypatch):
    capturado: dict = {}
    _mock_subida_y_cola(monkeypatch, capturado, clave="audios/abc.mp3")

    r = _crear(cliente, tratamientos=["resumen", "ideas", "noexiste"])
    assert r.status_code == 201
    t = r.json()["transcripcion"]
    assert r.json()["gen_id"] == "gen-asr-1"
    assert t["estado"] == "pendiente" and t["media_id"] == "audios/abc.mp3"

    assert capturado["kind"] == jobspec.PROC_TRANSCRIBIR_AUDIO
    assert capturado["params"]["transcripcion_id"] == t["id"]
    # 'noexiste' se descarta; quedan solo los válidos.
    assert capturado["params"]["tratamientos"] == ["resumen", "ideas"]
    assert repos.obtener_audio_transcripcion(t["id"]) is not None


def test_crear_cola_llena_no_deja_huerfano(cliente, monkeypatch):
    async def fake_guardar(archivo, **k):
        return "audios/x.mp3"

    def fake_encolar(*, kind, params, marca=None, etiqueta=None):
        raise generaciones.ColaLlenaError("llena")

    monkeypatch.setattr(media, "guardar_audio_subida", fake_guardar)
    monkeypatch.setattr(generaciones, "encolar_job_proceso", fake_encolar)

    r = _crear(cliente)
    assert r.status_code == 429
    # La fila NO debe quedar huérfana en 'pendiente' sin job.
    assert repos.listar_audio_transcripciones() == []


def test_crear_sin_marca_400(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    r = cliente.post(
        "/api/audio/transcripciones",
        files={"archivo": ("x.mp3", b"bytes", "audio/mpeg")},
        data={"marca": ""},
    )
    assert r.status_code == 400


def test_crear_sin_archivo_400(cliente):
    r = cliente.post("/api/audio/transcripciones", data={"marca": _MARCA})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# CRUD de audios                                                                #
# --------------------------------------------------------------------------- #


def test_listar_obtener_actualizar_borrar(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]

    # Listar SIN filtro de marca (la herramienta muestra todos).
    assert tid in [t["id"] for t in cliente.get("/api/audio/transcripciones").json()["transcripciones"]]
    assert cliente.get(f"/api/audio/transcripciones/{tid}").status_code == 200
    assert cliente.get("/api/audio/transcripciones/no-existe").status_code == 404

    r = cliente.put(f"/api/audio/transcripciones/{tid}", json={"texto": "x", "estado": "editado"})
    assert r.status_code == 200 and r.json()["transcripcion"]["estado"] == "editado"
    assert cliente.put(f"/api/audio/transcripciones/{tid}", json={"estado": "publicado"}).status_code == 400

    assert cliente.delete(f"/api/audio/transcripciones/{tid}").status_code == 204
    assert cliente.get(f"/api/audio/transcripciones/{tid}").status_code == 404


# --------------------------------------------------------------------------- #
# Artefactos                                                                    #
# --------------------------------------------------------------------------- #


def _fake_tratamiento(monkeypatch):
    """`lanzar_tratamiento` mock: crea el artefacto (generando) sin tocar Claude."""

    def fake(fila, tipo, *, autor=None, respuestas=None):
        art = repos.crear_audio_artefacto(
            transcripcion_id=fila["id"], tipo=tipo, titulo=tipo.title(),
            formato="md", estado="generando", gen_id="gen-trat",
        )
        return {"artefacto": art, "gen": {"id": "gen-trat"}}

    monkeypatch.setattr(audio_artefactos, "lanzar_tratamiento", fake)


def test_artefactos_crear_listar_editar_borrar(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    _fake_tratamiento(monkeypatch)

    # Lanzar un tratamiento -> artefacto 'generando'.
    r = cliente.post(f"/api/audio/transcripciones/{tid}/artefacto", json={"tipo": "resumen"})
    assert r.status_code == 201
    aid = r.json()["artefacto"]["id"]
    assert r.json()["artefacto"]["estado"] == "generando"

    # Tipo inválido -> 400.
    assert cliente.post(f"/api/audio/transcripciones/{tid}/artefacto", json={"tipo": "srt"}).status_code == 400

    # Listar artefactos del audio.
    arts = cliente.get(f"/api/audio/transcripciones/{tid}/artefactos").json()["artefactos"]
    assert aid in [a["id"] for a in arts]

    # Editar el contenido (queda 'listo').
    r = cliente.put(f"/api/audio/artefactos/{aid}", json={"contenido": "resumen a mano"})
    assert r.status_code == 200
    assert r.json()["artefacto"]["contenido"] == "resumen a mano"
    assert r.json()["artefacto"]["estado"] == "listo"

    # Borrar.
    assert cliente.delete(f"/api/audio/artefactos/{aid}").status_code == 204
    assert cliente.get(f"/api/audio/artefactos/{aid}").status_code == 404


def test_srt_no_editable(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    srt = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="srt", titulo="Subtítulos (SRT)", contenido="1\n...", formato="srt"
    )
    r = cliente.put(f"/api/audio/artefactos/{srt['id']}", json={"contenido": "hack"})
    assert r.status_code == 400


def test_corregir_desde_preguntas(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    preguntas = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="preguntas", titulo="Preguntas", contenido="¿x?", formato="md"
    )
    _fake_tratamiento(monkeypatch)

    # Sin respuestas -> 400.
    assert cliente.post(f"/api/audio/artefactos/{preguntas['id']}/corregir", json={}).status_code == 400

    r = cliente.post(
        f"/api/audio/artefactos/{preguntas['id']}/corregir",
        json={"respuestas": ["Es Mbappé", "Ganó el América"]},
    )
    assert r.status_code == 201
    assert r.json()["artefacto"]["tipo"] == "corregido"
