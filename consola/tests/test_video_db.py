"""CRUD de `video_composiciones` y `video_subtitulos` (Ola VIDEO). Usa la fixture `entorno`."""

from __future__ import annotations

from keni_consola import db, repos

_MARCA = "claro-sports"


def test_crud_composicion(entorno):
    c = repos.crear_video_composicion(marca=_MARCA, documento='{"version":1}', contenido_id="t1")
    assert c["marca"] == _MARCA
    assert c["contenido_id"] == "t1"
    assert c["documento"] == '{"version":1}'

    leida = repos.obtener_video_composicion(c["id"])
    assert leida is not None and leida["id"] == c["id"]

    act = repos.actualizar_video_composicion(c["id"], {"documento": '{"version":2}'})
    assert act["documento"] == '{"version":2}'

    listadas = repos.listar_video_composiciones(marca=_MARCA)
    assert any(x["id"] == c["id"] for x in listadas)
    assert repos.listar_video_composiciones(contenido_id="t1")[0]["id"] == c["id"]


def test_obtener_composicion_inexistente_none(entorno):
    assert repos.obtener_video_composicion("no-existe") is None
    assert repos.actualizar_video_composicion("no-existe", {"marca": "x"}) is None


def test_crud_subtitulo(entorno):
    c = repos.crear_video_composicion(marca=_MARCA)
    s = repos.crear_video_subtitulo(composicion_id=c["id"])
    assert s["estado"] == "pendiente"
    assert s["idioma"] == "es-MX"

    act = repos.actualizar_video_subtitulo(
        s["id"], {"estado": "transcrito", "segmentos": "[]", "ass": "[Script Info]"}
    )
    assert act["estado"] == "transcrito"
    assert act["ass"] == "[Script Info]"

    porc = repos.listar_video_subtitulos(composicion_id=c["id"])
    assert len(porc) == 1 and porc[0]["id"] == s["id"]
    assert repos.listar_video_subtitulos(estado="transcrito")[0]["id"] == s["id"]


def test_subtitulo_estado_invalido_se_ignora(entorno):
    c = repos.crear_video_composicion(marca=_MARCA)
    # estado fuera del enum al crear -> cae a 'pendiente'.
    s = db.crear_video_subtitulo(composicion_id=c["id"], estado="basura")
    assert s["estado"] == "pendiente"
    # estado invalido al actualizar -> se descarta (no rompe; conserva el anterior).
    act = repos.actualizar_video_subtitulo(s["id"], {"estado": "basura", "idioma": "en"})
    assert act["estado"] == "pendiente"
    assert act["idioma"] == "en"
