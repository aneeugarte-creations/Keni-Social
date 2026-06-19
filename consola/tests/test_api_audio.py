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
    # La fila liga el job del motor (progreso en vivo) y recuerda los tratamientos elegidos
    # (para pintar los documentos por crear mientras se transcribe).
    assert t["gen_id"] == "gen-asr-1"
    assert t["tratamientos"] == ["resumen", "ideas"]

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


def test_crear_sin_marca_ni_sesion_400(cliente, monkeypatch):
    """Sin marca y sin sesión (token de bootstrap): no se puede saber de quién es el personal -> 400."""
    _mock_subida_y_cola(monkeypatch, {})
    r = cliente.post(
        "/api/audio/transcripciones",
        files={"archivo": ("x.mp3", b"bytes", "audio/mpeg")},
        data={"marca": ""},
    )
    assert r.status_code == 400


def _mock_autor(monkeypatch, uid="u-mike", nombre="Mike"):
    from keni_consola import seguridad

    monkeypatch.setattr(seguridad, "autor_de_peticion", lambda request: {"id": uid, "usuario": nombre})


def test_crear_personal_y_visibilidad(cliente, monkeypatch):
    """Audio PERSONAL (sin marca) con sesión: es del autor; solo lo ve él, no otros."""
    _mock_subida_y_cola(monkeypatch, {})
    _mock_autor(monkeypatch, uid="u-mike")

    r = cliente.post(
        "/api/audio/transcripciones",
        files={"archivo": ("mio.mp3", b"bytes", "audio/mpeg")},
        data={"marca": ""},
    )
    assert r.status_code == 201
    t = r.json()["transcripcion"]
    assert t["es_personal"] is True and t["marca"] == "" and t["autor_id"] == "u-mike"
    assert t["marca_nombre"] == "Personal"

    # Mike lo ve.
    lista = cliente.get("/api/audio/transcripciones").json()["transcripciones"]
    assert t["id"] in [x["id"] for x in lista]
    # Otra persona NO lo ve (es personal de Mike).
    _mock_autor(monkeypatch, uid="u-otro")
    lista2 = cliente.get("/api/audio/transcripciones").json()["transcripciones"]
    assert t["id"] not in [x["id"] for x in lista2]


def test_mover_audio_personal_a_marca(cliente, monkeypatch):
    """PUT marca mueve el ámbito: personal -> de marca (colaborativo)."""
    _mock_subida_y_cola(monkeypatch, {})
    _mock_autor(monkeypatch, uid="u-mike")
    tid = cliente.post(
        "/api/audio/transcripciones",
        files={"archivo": ("mio.mp3", b"bytes", "audio/mpeg")},
        data={"marca": ""},
    ).json()["transcripcion"]["id"]

    r = cliente.put(f"/api/audio/transcripciones/{tid}", json={"marca": _MARCA})
    assert r.status_code == 200
    assert r.json()["transcripcion"]["es_personal"] is False
    assert r.json()["transcripcion"]["marca"] == _MARCA
    # Marca inválida -> 400.
    assert cliente.put(f"/api/audio/transcripciones/{tid}", json={"marca": "no-existe"}).status_code == 400


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


def _fake_tratamiento(monkeypatch, capturado: dict | None = None):
    """`lanzar_tratamiento` mock: crea el artefacto (generando) sin tocar Claude; refleja herencia."""

    def fake(fila, tipo, *, origen=None, autor=None, respuestas=None):
        if capturado is not None:
            capturado["origen"] = origen
        art = repos.crear_audio_artefacto(
            transcripcion_id=fila["id"], tipo=tipo, titulo=tipo.title(),
            formato="md", estado="generando", gen_id="gen-trat",
            origen_id=(origen or {}).get("id", ""),
            origen_version=(origen or {}).get("actualizado", ""),
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


def test_listar_artefactos_reconstruye_srt_legado(cliente):
    """Audio transcrito ANTES del modelo de artefactos (con segmentos, sin filas): se backfillea."""
    import json

    fila = repos.crear_audio_transcripcion(
        marca=_MARCA, nombre="viejo.mp3", estado="transcrito",
        segmentos=json.dumps([{"inicio_ms": 0, "fin_ms": 1500, "texto": "hola mundo"}]),
        texto="hola mundo",
    )
    tid = fila["id"]
    assert repos.listar_audio_artefactos(tid) == []

    arts = cliente.get(f"/api/audio/transcripciones/{tid}/artefactos").json()["artefactos"]
    tipos = {a["tipo"] for a in arts}
    assert "srt" in tipos and "texto" in tipos
    srt = next(a for a in arts if a["tipo"] == "srt")
    assert "hola mundo" in srt["contenido"] and srt["estado"] == "listo"
    # Idempotente: una segunda lectura no duplica.
    arts2 = cliente.get(f"/api/audio/transcripciones/{tid}/artefactos").json()["artefactos"]
    assert len(arts2) == len(arts)


def test_fuente_del_tratamiento_segun_origen():
    """`_fuente_del_tratamiento`: de dónde sale el texto y la herencia según el origen (función pura)."""
    fuente = audio_artefactos._fuente_del_tratamiento
    tr = {
        "id": "t1", "actualizado": "2026-01-01",
        "segmentos": [{"inicio_ms": 0, "texto": "hola mundo"}], "texto": "hola mundo",
    }
    # Sin origen: parte de la transcripción con timestamps; herencia vacía, versión = la del audio.
    bloque, oid, ver = fuente(tr, "resumen", None)
    assert "hola mundo" in bloque and oid == "" and ver == "2026-01-01"

    # Origen SRT: también parte de la transcripción (timestamps), pero hereda del SRT.
    srt = {"id": "a-srt", "tipo": "srt", "contenido": "1\n00:00...", "actualizado": "2026-02-02"}
    bloque, oid, ver = fuente(tr, "resumen", srt)
    assert "hola mundo" in bloque and oid == "a-srt" and ver == "2026-02-02"

    # Origen NO-SRT: parte de su contenido (encadenar tratamientos).
    limpio = {"id": "a-lim", "tipo": "limpio", "contenido": "texto limpio", "actualizado": "2026-03-03"}
    bloque, oid, ver = fuente(tr, "resumen", limpio)
    assert bloque == "texto limpio" and oid == "a-lim" and ver == "2026-03-03"

    # 'corregido' siempre parte de la transcripción, aunque herede del artefacto de preguntas.
    preg = {"id": "a-preg", "tipo": "preguntas", "contenido": "[00:01] «x» — ¿y?", "actualizado": "2026-04-04"}
    bloque, oid, ver = fuente(tr, "corregido", preg)
    assert "hola mundo" in bloque and oid == "a-preg" and ver == "2026-04-04"

    # 'clips' y 'capitulado' NECESITAN tiempos: parten de la transcripción aunque hereden de un
    # artefacto de texto (limpio), no de su contenido sin timestamps.
    for tipo in ("clips", "capitulado"):
        bloque, oid, ver = fuente(tr, tipo, limpio)
        assert "hola mundo" in bloque, tipo
        assert "[00:00]" in bloque, tipo  # con la marca de tiempo del segmento
        assert oid == "a-lim" and ver == "2026-03-03"


def test_tratamientos_clips_y_capitulado_registrados():
    # Los tres extractores están en el registro con su prompt y formato.
    t = audio_artefactos.TRATAMIENTOS
    assert t["ideas"] == ("prompt/audio/ideas", "md", "Ideas")
    assert t["clips"] == ("prompt/audio/clips", "md", "Clips")
    assert t["capitulado"] == ("prompt/audio/capitulado", "txt", "Capítulos")


def test_crear_artefacto_hereda_del_origen(cliente, monkeypatch):
    """Sin `origen_id` parte del SRT (base); con `origen_id` parte de ese artefacto; uno inválido -> 400."""
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    srt = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="srt", titulo="Subtítulos (SRT)", contenido="1\n...", formato="srt"
    )
    cap: dict = {}
    _fake_tratamiento(monkeypatch, cap)

    # Sin origen_id -> el origen es el SRT (base canónica).
    r = cliente.post(f"/api/audio/transcripciones/{tid}/artefacto", json={"tipo": "resumen"})
    assert r.status_code == 201
    assert cap["origen"]["id"] == srt["id"]
    assert r.json()["artefacto"]["origen_id"] == srt["id"]
    assert r.json()["artefacto"]["origen_version"] == srt["actualizado"]

    # Con un origen_id concreto -> parte de ese artefacto (encadenar tratamientos).
    limpio = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="limpio", titulo="Limpio", contenido="texto limpio", formato="txt"
    )
    r = cliente.post(
        f"/api/audio/transcripciones/{tid}/artefacto",
        json={"tipo": "resumen", "origen_id": limpio["id"]},
    )
    assert r.status_code == 201 and cap["origen"]["id"] == limpio["id"]

    # origen_id inexistente -> 400.
    r = cliente.post(
        f"/api/audio/transcripciones/{tid}/artefacto",
        json={"tipo": "resumen", "origen_id": "no-existe"},
    )
    assert r.status_code == 400


def test_srt_no_editable(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    srt = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="srt", titulo="Subtítulos (SRT)", contenido="1\n...", formato="srt"
    )
    r = cliente.put(f"/api/audio/artefactos/{srt['id']}", json={"contenido": "hack"})
    assert r.status_code == 400


def test_respuestas_persisten_en_servidor(cliente, monkeypatch):
    """PUT /artefactos/{id}/respuestas guarda en BD; el GET las devuelve como objeto."""
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    preg = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="preguntas", titulo="Preguntas", contenido="[00:01] x — ¿y?",
        formato="md",
    )
    aid = preg["id"]

    r = cliente.put(
        f"/api/audio/artefactos/{aid}/respuestas",
        json={"respuestas": {"0": "  Piso 15  ", "1": "", "2": "pesos"}},
    )
    assert r.status_code == 200
    # Solo las no vacías, recortadas.
    assert r.json()["artefacto"]["respuestas"] == {"0": "Piso 15", "2": "pesos"}
    # Persisten: una lectura posterior las trae.
    arts = cliente.get(f"/api/audio/transcripciones/{tid}/artefactos").json()["artefactos"]
    guardado = next(a for a in arts if a["id"] == aid)
    assert guardado["respuestas"] == {"0": "Piso 15", "2": "pesos"}

    # Cuerpo inválido -> 400.
    assert cliente.put(f"/api/audio/artefactos/{aid}/respuestas", json={"respuestas": "x"}).status_code == 400


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


# --------------------------------------------------------------------------- #
# Ideas -> Sugerencias                                                         #
# --------------------------------------------------------------------------- #


def test_parsear_ideas_clasifica_por_seccion():
    """`parsear_ideas`: una sugerencia por viñeta; la categoría sale del encabezado (función pura)."""
    md = (
        "## Producto / software\n- **Idea:** Automatizar el deploy\n"
        "## Negocio\n- Vender cursos de IA\n"
        "## Bug\n- Crash al subir audios largos\n"
    )
    items = audio_artefactos.parsear_ideas(md)
    por_titulo = {i["titulo"]: i["categoria"] for i in items}
    assert por_titulo["Automatizar el deploy"] == "producto"  # sin la etiqueta «Idea:» ni markdown
    assert por_titulo["Vender cursos de IA"] == "idea"
    assert por_titulo["Crash al subir audios largos"] == "bug"


def test_a_sugerencias_crea_una_por_idea(cliente, monkeypatch):
    from keni_consola import sugerencias

    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    art = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="ideas", titulo="Ideas", formato="md", estado="listo",
        contenido="## Producto / software\n- Exportar a Slack\n## Contenido\n- Serie sobre el clásico",
    )
    r = cliente.post(f"/api/audio/artefactos/{art['id']}/a-sugerencias")
    assert r.status_code == 200
    assert r.json()["creadas"] == 2
    sugs = sugerencias.listar()
    assert {s["categoria"] for s in sugs} == {"producto", "idea"}
    # El detalle referencia el audio de origen.
    assert all("De audio:" in s["detalle"] for s in sugs)


def test_a_sugerencias_solo_ideas(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    art = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="resumen", titulo="Resumen", formato="md", estado="listo",
        contenido="- algo",
    )
    assert cliente.post(f"/api/audio/artefactos/{art['id']}/a-sugerencias").status_code == 400


def test_a_sugerencias_sin_ideas_400(cliente, monkeypatch):
    _mock_subida_y_cola(monkeypatch, {})
    tid = _crear(cliente).json()["transcripcion"]["id"]
    art = repos.crear_audio_artefacto(
        transcripcion_id=tid, tipo="ideas", titulo="Ideas", formato="md", estado="listo",
        contenido="(sin ideas claras en este audio)",
    )
    # Una sola línea sin viñetas: el parser no saca ideas -> 400.
    assert cliente.post(f"/api/audio/artefactos/{art['id']}/a-sugerencias").status_code == 400
