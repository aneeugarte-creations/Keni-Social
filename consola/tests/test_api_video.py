"""Tests de la API del motor de VIDEO (/api/video/*). OFFLINE: NUNCA toca la red ni ffmpeg.

Cubre:
  - GET /api/video/formatos               presets + redes por formato.
  - CRUD de composiciones                 crear -> obtener -> actualizar -> listar (filtro marca).
  - Validacion                            documento invalido (400), marca invalida (400), 404.
  - render / transcribir                  flag OFF -> 409; flag ON (monkeypatch) -> encola gen_id.
  - subtitulos                            GET por composicion, PUT (segmentos + estado, ass).

El encolado real (`generaciones.encolar_job_proceso`) se MONKEYPATCHEA para no ejecutar nada
(ni cola, ni worker, ni claude): solo verificamos que la API lo invoca con los params correctos.
"""

from __future__ import annotations

import pytest

from keni_consola import config, generaciones
from keni_consola.api import video
from keni_consola.dominio import jobspec

# Documento de composicion MINIMO valido (pasa `keni_shared.video.validar_composicion`).
_DOC_OK = {
    "version": 1,
    "formato": {"w": 1080, "h": 1920, "fps": 30, "preset": "9:16"},
    "duracion_ms": 30000,
    "pistas": [{"id": "base", "tipo": "video", "clips": []}],
}


def _crear(cliente, *, marca="unotv", documento=None) -> dict:
    """Crea una composicion via API y devuelve el JSON de respuesta."""
    r = cliente.post(
        "/api/video/composiciones",
        json={"marca": marca, "documento": documento or _DOC_OK},
    )
    return r


# --------------------------------------------------------------------------- #
# GET /api/video/formatos                                                      #
# --------------------------------------------------------------------------- #


def test_formatos(cliente):
    r = cliente.get("/api/video/formatos")
    assert r.status_code == 200
    formatos = r.json()["formatos"]
    presets = {f["preset"] for f in formatos}
    assert {"9:16", "1:1", "16:9"} <= presets
    porpreset = {f["preset"]: f for f in formatos}
    # El preset trae resolucion + zonas seguras.
    assert porpreset["9:16"]["w"] == 1080 and porpreset["9:16"]["h"] == 1920
    assert "safe_top" in porpreset["9:16"] and "safe_bottom" in porpreset["9:16"]
    # X usa 16:9; las demas redes 9:16 (mapeo de VIDEO_SPECS).
    assert "x" in porpreset["16:9"]["redes"]
    assert "tiktok" in porpreset["9:16"]["redes"]


# --------------------------------------------------------------------------- #
# CRUD de composiciones                                                        #
# --------------------------------------------------------------------------- #


def test_ciclo_crud_composicion(cliente):
    # crear
    r = _crear(cliente, marca="unotv")
    assert r.status_code == 200
    comp_id = r.json()["id"]
    assert comp_id

    # obtener
    r = cliente.get(f"/api/video/composiciones/{comp_id}")
    assert r.status_code == 200
    comp = r.json()["composicion"]
    assert comp["id"] == comp_id
    assert comp["marca"] == "unotv"
    assert comp["marca_nombre"]  # nombre legible resuelto en servidor
    assert isinstance(comp["documento"], dict)  # documento parseado, no string
    assert comp["documento"]["formato"]["w"] == 1080

    # actualizar (cambia la duracion del documento)
    doc2 = {**_DOC_OK, "duracion_ms": 15000}
    r = cliente.put(f"/api/video/composiciones/{comp_id}", json={"documento": doc2})
    assert r.status_code == 200
    assert r.json()["composicion"]["documento"]["duracion_ms"] == 15000

    # listar (sin filtro)
    r = cliente.get("/api/video/composiciones")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["composiciones"]]
    assert comp_id in ids


def test_listar_filtra_por_marca(cliente):
    a = _crear(cliente, marca="unotv").json()["id"]
    b = _crear(cliente, marca="claro-sports").json()["id"]

    r = cliente.get("/api/video/composiciones", params={"marca": "unotv"})
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()["composiciones"]}
    assert a in ids
    assert b not in ids


def test_crear_documento_invalido_400(cliente):
    # 'pistas' no es lista -> el validador de keni_shared lanza ValueError -> 400.
    r = cliente.post(
        "/api/video/composiciones",
        json={"marca": "unotv", "documento": {"formato": {"w": 1080, "h": 1920}, "pistas": "x"}},
    )
    assert r.status_code == 400
    assert "pistas" in r.json()["error"].lower()


def test_crear_marca_invalida_400(cliente):
    r = cliente.post(
        "/api/video/composiciones", json={"marca": "marca-fantasma", "documento": _DOC_OK}
    )
    assert r.status_code == 400


def test_crear_sin_marca_400(cliente):
    r = cliente.post("/api/video/composiciones", json={"documento": _DOC_OK})
    assert r.status_code == 400


def test_crear_sin_documento_400(cliente):
    r = cliente.post("/api/video/composiciones", json={"marca": "unotv"})
    assert r.status_code == 400


def test_obtener_inexistente_404(cliente):
    assert cliente.get("/api/video/composiciones/noexiste").status_code == 404


def test_actualizar_inexistente_404(cliente):
    r = cliente.put("/api/video/composiciones/noexiste", json={"documento": _DOC_OK})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# DRAFTS: titulo + estado (borrador/listo)                                     #
# --------------------------------------------------------------------------- #


def test_crear_con_titulo_y_estado(cliente):
    r = cliente.post(
        "/api/video/composiciones",
        json={"marca": "unotv", "documento": _DOC_OK, "titulo": "Mi borrador", "estado": "listo"},
    )
    assert r.status_code == 200
    comp = cliente.get(f"/api/video/composiciones/{r.json()['id']}").json()["composicion"]
    assert comp["titulo"] == "Mi borrador"
    assert comp["estado"] == "listo"


def test_crear_defaults_titulo_estado(cliente):
    comp = cliente.get(f"/api/video/composiciones/{_crear(cliente).json()['id']}").json()[
        "composicion"
    ]
    assert comp["titulo"] == ""
    assert comp["estado"] == "borrador"


def test_crear_estado_invalido_400(cliente):
    r = cliente.post(
        "/api/video/composiciones",
        json={"marca": "unotv", "documento": _DOC_OK, "estado": "fantasma"},
    )
    assert r.status_code == 400


def test_listar_devuelve_titulo_estado(cliente):
    cid = cliente.post(
        "/api/video/composiciones",
        json={"marca": "unotv", "documento": _DOC_OK, "titulo": "T", "estado": "listo"},
    ).json()["id"]
    fila = next(
        c for c in cliente.get("/api/video/composiciones").json()["composiciones"] if c["id"] == cid
    )
    assert fila["titulo"] == "T" and fila["estado"] == "listo"


def test_put_renombra_y_cambia_estado_sin_documento(cliente):
    cid = _crear(cliente).json()["id"]
    r = cliente.put(
        f"/api/video/composiciones/{cid}", json={"titulo": "Nuevo nombre", "estado": "listo"}
    )
    assert r.status_code == 200
    comp = r.json()["composicion"]
    assert comp["titulo"] == "Nuevo nombre"
    assert comp["estado"] == "listo"
    # El documento previo se conserva (no se perdio por no reenviarlo).
    assert comp["documento"]["formato"]["w"] == 1080


def test_put_estado_invalido_400(cliente):
    cid = _crear(cliente).json()["id"]
    r = cliente.put(f"/api/video/composiciones/{cid}", json={"estado": "fantasma"})
    assert r.status_code == 400


def test_put_vacio_400(cliente):
    cid = _crear(cliente).json()["id"]
    assert cliente.put(f"/api/video/composiciones/{cid}", json={}).status_code == 400


def test_delete_borra_y_luego_404(cliente):
    cid = _crear(cliente).json()["id"]
    r = cliente.delete(f"/api/video/composiciones/{cid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Tras borrar, ya no existe.
    assert cliente.get(f"/api/video/composiciones/{cid}").status_code == 404


def test_delete_inexistente_404(cliente):
    assert cliente.delete("/api/video/composiciones/noexiste").status_code == 404


# --------------------------------------------------------------------------- #
# render                                                                       #
# --------------------------------------------------------------------------- #


def test_render_flag_off_409(cliente, monkeypatch):
    comp_id = _crear(cliente).json()["id"]
    monkeypatch.setattr(config, "video_render_gateado", lambda: False)
    r = cliente.post(f"/api/video/composiciones/{comp_id}/render")
    assert r.status_code == 409
    assert "apagado" in r.json()["error"].lower()


def test_render_inexistente_404(cliente, monkeypatch):
    monkeypatch.setattr(config, "video_render_gateado", lambda: True)
    assert cliente.post("/api/video/composiciones/noexiste/render").status_code == 404


def test_render_flag_on_encola(cliente, monkeypatch):
    comp_id = _crear(cliente, marca="unotv").json()["id"]
    monkeypatch.setattr(config, "video_render_gateado", lambda: True)

    capturado = {}

    def fake_encolar(*, kind, params, marca=None, etiqueta=None):
        capturado.update(kind=kind, params=params, marca=marca)
        return {"id": "gen-render-1"}

    monkeypatch.setattr(generaciones, "encolar_job_proceso", fake_encolar)

    r = cliente.post(f"/api/video/composiciones/{comp_id}/render")
    assert r.status_code == 200
    assert r.json()["gen_id"] == "gen-render-1"
    assert capturado["kind"] == jobspec.PROC_RENDER_VIDEO
    assert capturado["params"] == {"composicion_id": comp_id}
    assert capturado["marca"] == "unotv"


# --------------------------------------------------------------------------- #
# transcribir                                                                  #
# --------------------------------------------------------------------------- #


def test_transcribir_flag_off_409(cliente, monkeypatch):
    comp_id = _crear(cliente).json()["id"]
    monkeypatch.setattr(config, "transcripcion_gateada", lambda: False)
    r = cliente.post(
        f"/api/video/composiciones/{comp_id}/transcribir",
        json={"media_id": "videos/abc.mp4"},
    )
    assert r.status_code == 409
    assert "apagado" in r.json()["error"].lower()


def test_transcribir_sin_media_400(cliente, monkeypatch):
    comp_id = _crear(cliente).json()["id"]
    monkeypatch.setattr(config, "transcripcion_gateada", lambda: True)
    r = cliente.post(f"/api/video/composiciones/{comp_id}/transcribir", json={})
    assert r.status_code == 400


def test_transcribir_flag_on_crea_subtitulo_y_encola(cliente, monkeypatch):
    comp_id = _crear(cliente, marca="unotv").json()["id"]
    monkeypatch.setattr(config, "transcripcion_gateada", lambda: True)

    capturado = {}

    def fake_encolar(*, kind, params, marca=None, etiqueta=None):
        capturado.update(kind=kind, params=params, marca=marca)
        return {"id": "gen-trans-1"}

    monkeypatch.setattr(generaciones, "encolar_job_proceso", fake_encolar)

    r = cliente.post(
        f"/api/video/composiciones/{comp_id}/transcribir",
        json={"media_id": "videos/abc.mp4", "idioma": "es-MX"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["gen_id"] == "gen-trans-1"
    sub_id = body["subtitulo_id"]
    assert sub_id

    # Se creo la fila de subtitulos (estado pendiente) y se pasaron los params correctos.
    assert capturado["kind"] == jobspec.PROC_TRANSCRIBIR
    assert capturado["params"]["composicion_id"] == comp_id
    assert capturado["params"]["subtitulo_id"] == sub_id
    assert capturado["params"]["media_id"] == "videos/abc.mp4"
    assert capturado["params"]["idioma"] == "es-MX"

    # Una segunda transcripcion REUTILIZA la misma fila (no duplica).
    r2 = cliente.post(
        f"/api/video/composiciones/{comp_id}/transcribir",
        json={"media_id": "videos/abc.mp4"},
    )
    assert r2.status_code == 200
    assert r2.json()["subtitulo_id"] == sub_id


# --------------------------------------------------------------------------- #
# subtitulos (GET / PUT)                                                       #
# --------------------------------------------------------------------------- #


def test_subtitulos_get_vacio(cliente):
    comp_id = _crear(cliente).json()["id"]
    r = cliente.get("/api/video/subtitulos", params={"composicion_id": comp_id})
    assert r.status_code == 200
    assert r.json()["subtitulo"] is None


def test_subtitulos_get_sin_composicion_400(cliente):
    assert cliente.get("/api/video/subtitulos").status_code == 400


def _crear_subtitulo(cliente, monkeypatch) -> tuple[str, str]:
    """Crea composicion + fila de subtitulos via el endpoint de transcribir. -> (comp_id, sub_id)."""
    comp_id = _crear(cliente, marca="unotv").json()["id"]
    monkeypatch.setattr(config, "transcripcion_gateada", lambda: True)
    monkeypatch.setattr(
        generaciones, "encolar_job_proceso", lambda **k: {"id": "g"}
    )
    r = cliente.post(
        f"/api/video/composiciones/{comp_id}/transcribir", json={"media_id": "videos/x.mp4"}
    )
    return comp_id, r.json()["subtitulo_id"]


def test_subtitulos_get_devuelve_fila(cliente, monkeypatch):
    comp_id, sub_id = _crear_subtitulo(cliente, monkeypatch)
    r = cliente.get("/api/video/subtitulos", params={"composicion_id": comp_id})
    assert r.status_code == 200
    sub = r.json()["subtitulo"]
    assert sub["id"] == sub_id
    assert sub["estado"] == "pendiente"
    assert sub["segmentos"] == []  # parseado a lista, no string crudo


def test_subtitulos_put_segmentos_y_estado_sin_motor(cliente, monkeypatch):
    """PUT corrige segmentos y marca estado; sin motor de ASR el ass no se regenera (None)."""
    comp_id, sub_id = _crear_subtitulo(cliente, monkeypatch)
    segmentos = [{"inicio_ms": 0, "fin_ms": 500, "texto": "Hola"}]

    # Aseguramos que el regenerador de ASS reporta "motor no disponible".
    monkeypatch.setattr(video, "_regenerar_ass", lambda segs: None)

    r = cliente.put(
        f"/api/video/subtitulos/{sub_id}",
        json={"segmentos": segmentos, "estado": "editado"},
    )
    assert r.status_code == 200
    sub = r.json()["subtitulo"]
    assert sub["estado"] == "editado"
    assert sub["segmentos"] == segmentos
    assert not sub["ass"]  # sin motor, no se genero ass


def test_subtitulos_put_regenera_ass_con_motor(cliente, monkeypatch):
    """Si el motor de ASR expone `segmentos_a_ass`, el PUT regenera el ass desde los segmentos."""
    comp_id, sub_id = _crear_subtitulo(cliente, monkeypatch)
    segmentos = [{"inicio_ms": 0, "fin_ms": 500, "texto": "Hola"}]

    monkeypatch.setattr(video, "_regenerar_ass", lambda segs: "[Script Info]\nASS-FAKE")

    r = cliente.put(f"/api/video/subtitulos/{sub_id}", json={"segmentos": segmentos})
    assert r.status_code == 200
    sub = r.json()["subtitulo"]
    assert sub["segmentos"] == segmentos
    assert "ASS-FAKE" in sub["ass"]


def test_subtitulos_put_marca_listo(cliente, monkeypatch):
    comp_id, sub_id = _crear_subtitulo(cliente, monkeypatch)
    r = cliente.put(f"/api/video/subtitulos/{sub_id}", json={"estado": "listo"})
    assert r.status_code == 200
    assert r.json()["subtitulo"]["estado"] == "listo"


def test_subtitulos_put_estado_invalido_400(cliente, monkeypatch):
    comp_id, sub_id = _crear_subtitulo(cliente, monkeypatch)
    r = cliente.put(f"/api/video/subtitulos/{sub_id}", json={"estado": "inventado"})
    assert r.status_code == 400


def test_subtitulos_put_inexistente_404(cliente):
    r = cliente.put("/api/video/subtitulos/noexiste", json={"estado": "listo"})
    assert r.status_code == 404


@pytest.mark.parametrize("payload", [{}, {"segmentos": "no-lista"}])
def test_subtitulos_put_payload_invalido_400(cliente, monkeypatch, payload):
    comp_id, sub_id = _crear_subtitulo(cliente, monkeypatch)
    r = cliente.put(f"/api/video/subtitulos/{sub_id}", json=payload)
    assert r.status_code == 400
