"""Tests de la API del TABLERO de contenido unificado (`/api/contenido`).

Cubren el CRUD del padre, las filas por plataforma (estado + checklist), el `vencido`
derivado del deadline, la promocion desde el Radar y las validaciones (marca/red/estado/
responsable). Multiusuario con login real; reusa el aislamiento de `entorno` (Postgres) y
los fakes de `conftest`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba"


def _app():
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)


def _cli(usuario: str = "ana", *, cobertura: bool = True) -> TestClient:
    auth.crear_usuario(usuario, _CLAVE, "editor")
    if cobertura:
        for u in auth.listar_usuarios():
            if u["usuario"] == usuario:
                auth.actualizar_perfil(u["id"], cobertura=True)
    c = TestClient(_app())
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _id_usuario(nombre: str) -> str:
    for u in auth.listar_usuarios():
        if u["usuario"] == nombre:
            return u["id"]
    raise AssertionError(f"usuario {nombre!r} no existe")


def test_tablero_vacio_devuelve_catalogos(entorno):
    c = _cli()
    cuerpo = c.get("/api/contenido").json()
    assert cuerpo["contenidos"] == []
    cat = cuerpo["catalogos"]
    assert {"importante", "evergreen", "evento"} <= set(cat["flujos"])
    assert any(r["id"] == "web" for r in cat["redes"])
    assert "ana" in {u["usuario"] for u in cat["usuarios"]}


def test_crear_contenido_con_plataformas(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido",
        json={
            "titulo": "Sismo CDMX",
            "flujo": "importante",
            "prioridad": "alta",
            "redes": ["instagram", "x", "web"],
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    cont = r.json()["contenido"]
    assert cont["titulo"] == "Sismo CDMX"
    assert cont["prioridad"] == "alta"
    assert cont["autor_nombre"] == "ana"
    # Una fila por red, ordenadas por orden canonico (x antes que instagram), web al final.
    assert [p["red"] for p in cont["plataformas"]] == ["x", "instagram", "web"]
    # Checklist por defecto: falta todo.
    assert all(p["falta_copy"] and p["falta_imagen"] for p in cont["plataformas"])


def test_crear_con_formato_video_crea_cinco_redes(entorno):
    """`formato=video` crea las 5 redes (foto=3 + youtube + tiktok) con falta_video activo."""
    c = _cli()
    r = c.post(
        "/api/contenido",
        json={"titulo": "Clip", "formato": "video"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    cont = r.json()["contenido"]
    assert cont["formato"] == "video"
    assert {p["red"] for p in cont["plataformas"]} == {
        "instagram", "x", "facebook", "youtube", "tiktok"
    }
    assert all(p["falta_video"] for p in cont["plataformas"])


def test_crear_con_formato_foto_crea_tres_redes(entorno):
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "Foto", "formato": "foto"}, headers=_ORIGIN
    ).json()["contenido"]
    assert {p["red"] for p in cont["plataformas"]} == {"instagram", "x", "facebook"}
    assert all(not p["falta_video"] for p in cont["plataformas"])


def test_flip_a_video_via_patch_contenido(entorno):
    """PATCH /api/contenido con {formato:'video'} añade youtube+tiktok y devuelve el resumen."""
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "Pieza", "formato": "foto"}, headers=_ORIGIN
    ).json()["contenido"]
    r = c.patch(f"/api/contenido/{cont['id']}", json={"formato": "video"}, headers=_ORIGIN)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["contenido"]["formato"] == "video"
    assert set(cuerpo["ajuste_formato"]["creadas"]) == {"youtube", "tiktok"}
    assert {p["red"] for p in cuerpo["contenido"]["plataformas"]} == {
        "instagram", "x", "facebook", "youtube", "tiktok"
    }


def test_flip_a_foto_conserva_extra_con_trabajo_y_avisa(entorno):
    """video->foto con trabajo en youtube: se conserva, se reporta y la API avisa."""
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "Pieza", "formato": "video"}, headers=_ORIGIN
    ).json()["contenido"]
    yt = next(p for p in cont["plataformas"] if p["red"] == "youtube")
    c.patch(
        f"/api/contenido/{cont['id']}/plataformas/{yt['id']}",
        json={"copy": "Guion"},
        headers=_ORIGIN,
    )
    r = c.patch(f"/api/contenido/{cont['id']}", json={"formato": "foto"}, headers=_ORIGIN)
    assert r.status_code == 200
    cuerpo = r.json()
    assert "youtube" in cuerpo["ajuste_formato"]["conservadas"]
    assert "aviso" in cuerpo


def test_patch_plataforma_fija_video_y_limpia_falta_video(entorno):
    """Adjuntar {video} en una fila limpia falta_video (espejo de imagen/falta_imagen)."""
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "Clip", "formato": "video"}, headers=_ORIGIN
    ).json()["contenido"]
    plat = next(p for p in cont["plataformas"] if p["red"] == "tiktok")
    assert plat["falta_video"] is True
    r = c.patch(
        f"/api/contenido/{cont['id']}/plataformas/{plat['id']}",
        json={"video": "videos/abc.mp4"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    actualizado = r.json()["plataforma"]
    assert actualizado["video"] == "videos/abc.mp4"
    assert actualizado["video_url"] == "/api/media/videos/abc.mp4"
    assert actualizado["falta_video"] is False


def test_listar_incluye_el_creado(entorno):
    c = _cli()
    c.post("/api/contenido", json={"titulo": "Nota A", "flujo": "evergreen"}, headers=_ORIGIN)
    cuerpo = c.get("/api/contenido?flujo=evergreen").json()
    assert [x["titulo"] for x in cuerpo["contenidos"]] == ["Nota A"]


def test_deadline_vencido_se_marca(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido",
        json={"titulo": "Atrasada", "fecha_entrega": "2000-01-01"},
        headers=_ORIGIN,
    )
    assert r.json()["contenido"]["vencido"] is True


def test_actualizar_plataforma_estado_y_checklist(entorno):
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "C", "redes": ["x"]}, headers=_ORIGIN
    ).json()["contenido"]
    plat_id = cont["plataformas"][0]["id"]
    r = c.patch(
        f"/api/contenido/{cont['id']}/plataformas/{plat_id}",
        json={"estado": "aprobado", "falta_copy": False, "copy": "¡Listo!"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    plat = r.json()["plataforma"]
    assert plat["estado"] == "aprobado"
    assert plat["falta_copy"] is False
    assert plat["copy"] == "¡Listo!"


def test_estado_plataforma_invalido_se_rechaza(entorno):
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "C", "redes": ["x"]}, headers=_ORIGIN
    ).json()["contenido"]
    plat_id = cont["plataformas"][0]["id"]
    r = c.patch(
        f"/api/contenido/{cont['id']}/plataformas/{plat_id}",
        json={"estado": "inventado"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_agregar_y_borrar_plataforma(entorno):
    c = _cli()
    cont = c.post("/api/contenido", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.post(
        f"/api/contenido/{cont['id']}/plataformas", json={"red": "tiktok"}, headers=_ORIGIN
    )
    assert r.status_code == 200
    plat_id = r.json()["plataforma"]["id"]
    assert c.request("DELETE", f"/api/contenido/{cont['id']}/plataformas/{plat_id}").status_code == 200


def test_crear_rechaza_marca_y_red_invalidas(entorno):
    c = _cli()
    assert c.post("/api/contenido", json={"titulo": "X", "marca": "no-existe"}, headers=_ORIGIN).status_code == 400
    assert c.post("/api/contenido", json={"titulo": "X", "redes": ["myspace"]}, headers=_ORIGIN).status_code == 400


def test_crear_sin_titulo_400(entorno):
    c = _cli()
    assert c.post("/api/contenido", json={"flujo": "importante"}, headers=_ORIGIN).status_code == 400


def test_asignar_responsable_real(entorno):
    c = _cli("ana")
    _cli("luis")
    luis = _id_usuario("luis")
    cont = c.post("/api/contenido", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.patch(
        f"/api/contenido/{cont['id']}", json={"responsable_id": luis}, headers=_ORIGIN
    )
    assert r.status_code == 200
    assert r.json()["contenido"]["responsable_nombre"] == "luis"


def test_responsable_inexistente_se_rechaza(entorno):
    c = _cli()
    cont = c.post("/api/contenido", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.patch(
        f"/api/contenido/{cont['id']}", json={"responsable_id": "fantasma"}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_desde_radar_crea_importante(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido/desde-radar",
        json={"titulo": "Tendencia: Mundial", "redes": ["x", "instagram"], "prioridad": "alta"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    cont = r.json()["contenido"]
    assert cont["flujo"] == "importante"
    assert cont["origen"] == "radar"
    assert cont["prioridad"] == "alta"
    assert len(cont["plataformas"]) == 2


def test_borrar_contenido(entorno):
    c = _cli()
    cont = c.post("/api/contenido", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    assert c.request("DELETE", f"/api/contenido/{cont['id']}").status_code == 200
    assert c.get("/api/contenido").json()["contenidos"] == []


def test_adaptar_imagen_por_red_asigna_a_cada_plataforma(entorno, monkeypatch):
    from keni_consola.dominio import estudio_imagen

    c = _cli()
    cont = c.post(
        "/api/contenido",
        json={"titulo": "Sismo", "redes": ["x", "instagram"]},
        headers=_ORIGIN,
    ).json()["contenido"]

    # Marca sin plantilla -> recorte DETERMINISTA por formato (mock de `editar`, sin red ni IA).
    monkeypatch.setattr(estudio_imagen, "marca_tiene_plantilla", lambda _m: False)
    monkeypatch.setattr(
        estudio_imagen,
        "editar",
        lambda imagen, op, params: {"id": f"adapt-{params['formato']}.png", "url": "/x"},
    )

    r = c.post(
        f"/api/contenido/{cont['id']}/adaptar-imagen",
        json={"imagen": "origen.png"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["adaptadas"] == 2
    # Cada plataforma recibió una imagen adaptada al formato de su red.
    imgs = {p["red"]: p["imagen"] for p in cuerpo["plataformas"]}
    assert imgs["x"].startswith("adapt-")
    assert imgs["instagram"].startswith("adapt-")
    # Persistido: el tablero refleja las imágenes asignadas por plataforma.
    tablero = c.get("/api/contenido").json()["contenidos"][0]
    assert all(p["imagen"].startswith("adapt-") for p in tablero["plataformas"])


def test_adaptar_imagen_sin_imagen_400(entorno):
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "X", "redes": ["x"]}, headers=_ORIGIN
    ).json()["contenido"]
    r = c.post(f"/api/contenido/{cont['id']}/adaptar-imagen", json={}, headers=_ORIGIN)
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Puerta creativa del equipo: POST /api/contenido/aportar (Fase 1 / Flujo A)    #
# --------------------------------------------------------------------------- #

# PNG minimo valido (1x1) para adjuntar como foto aportada por el equipo.
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_aportar_crea_con_origen_equipo(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido/aportar",
        data={
            "titulo": "Gol de último minuto",
            "marca": "unotv",
            "material": "El equipo grabó la jugada desde la grada.",
            "intencion": "breaking",
            "redes": "x,instagram",
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    # El alta creativa nace con el origen que enciende la auto-generacion (no opt-in).
    assert cont["origen"] == "equipo"
    # La imagen la trae el equipo de fuera => tipo "galeria" (no IA ni fuente).
    assert cont["tipo_contenido"] == "galeria"
    # "breaking" mapea a flujo "importante".
    assert cont["flujo"] == "importante"
    # El material crudo entra como descripcion (nota base del auto-copy).
    assert "grabó la jugada" in cont["descripcion"]
    # Una fila por red pedida, con la checklist pendiente.
    assert {p["red"] for p in cont["plataformas"]} == {"x", "instagram"}
    assert all(p["falta_copy"] for p in cont["plataformas"])


def test_aportar_exige_marca(entorno):
    c = _cli()
    # Sin marca: la puerta creativa la EXIGE (sin voz no hay auto-generacion).
    r = c.post(
        "/api/contenido/aportar",
        data={"titulo": "Idea suelta", "material": "algo"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    # Marca inexistente tambien se rechaza.
    r2 = c.post(
        "/api/contenido/aportar",
        data={"titulo": "Idea", "marca": "no-existe"},
        headers=_ORIGIN,
    )
    assert r2.status_code == 400


def test_aportar_sin_titulo_400(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido/aportar", data={"marca": "unotv"}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_aportar_con_imagen_adjunta_se_guarda_como_foto(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido/aportar",
        data={"titulo": "Foto de la rueda de prensa", "marca": "unotv", "redes": "x"},
        files={"imagen": ("foto.png", _PNG_1x1, "image/png")},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    plats = r.json()["contenido"]["plataformas"]
    assert len(plats) == 1
    # La foto aportada se adjunta como `foto` (foto cruda de fondo) de la red.
    assert plats[0]["foto"].endswith(".png")


def test_aportar_sin_redes_usa_canonicas(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido/aportar",
        data={"titulo": "Nota sin redes", "marca": "unotv", "intencion": "evergreen"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["flujo"] == "evergreen"
    # Sin redes explicitas, se crean las canonicas del catalogo.
    assert len(cont["plataformas"]) >= 1
    assert all(p["red"] != "web" for p in cont["plataformas"])


# Bytes mínimos de un "clip" (no es un MP4 real: la transcripción real está MOCKEADA).
_CLIP_FALSO = b"\x00\x00\x00\x18ftypmp42fakeclipbytes"


def test_aportar_con_clip_transcribe_en_local(entorno, monkeypatch):
    """El clip de vídeo/audio se transcribe EN LOCAL (mock) y el texto entra como material."""
    from keni_consola import transcripcion

    # Mock del transcriptor LOCAL: nunca toca whisper/ffmpeg reales.
    monkeypatch.setattr(
        transcripcion, "_TRANSCRIPTOR", lambda datos, *, ext: "Hoy ganamos tres a cero."
    )

    c = _cli()
    r = c.post(
        "/api/contenido/aportar",
        data={"titulo": "Declaración del DT", "marca": "unotv", "redes": "x"},
        files={"clip": ("declaracion.mp4", _CLIP_FALSO, "video/mp4")},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    # La transcripción entra como material base (descripción), marcada como NO verificada.
    assert "Hoy ganamos tres a cero" in cont["descripcion"]
    assert "sin verificar" in cont["descripcion"].lower()
    # Sigue siendo alta del equipo (enciende el auto-copy igual que una nota).
    assert cont["origen"] == "equipo"


def test_aportar_clip_se_concatena_al_material(entorno, monkeypatch):
    """Si hay material escrito Y clip, la transcripción se anexa (no lo pisa)."""
    from keni_consola import transcripcion

    monkeypatch.setattr(transcripcion, "_TRANSCRIPTOR", lambda datos, *, ext: "lo que se dijo")

    c = _cli()
    r = c.post(
        "/api/contenido/aportar",
        data={"titulo": "T", "marca": "unotv", "material": "contexto escrito", "redes": "x"},
        files={"clip": ("a.m4a", _CLIP_FALSO, "audio/mp4")},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    desc = r.json()["contenido"]["descripcion"]
    assert "contexto escrito" in desc
    assert "lo que se dijo" in desc


def test_aportar_clip_formato_no_soportado_400(entorno):
    """Un fichero que no es vídeo/audio se rechaza con 400 (mensaje en español)."""
    c = _cli()
    r = c.post(
        "/api/contenido/aportar",
        data={"titulo": "T", "marca": "unotv", "redes": "x"},
        files={"clip": ("notas.txt", b"hola", "text/plain")},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    assert "vídeo o audio" in r.json()["error"].lower()


def test_aportar_clip_sin_habla_no_rompe(entorno, monkeypatch):
    """Un clip que transcribe a vacío crea la pieza igualmente (sin material del clip)."""
    from keni_consola import transcripcion

    monkeypatch.setattr(transcripcion, "_TRANSCRIPTOR", lambda datos, *, ext: "")

    c = _cli()
    r = c.post(
        "/api/contenido/aportar",
        data={"titulo": "Solo música", "marca": "unotv", "redes": "x"},
        files={"clip": ("clip.mp4", _CLIP_FALSO, "video/mp4")},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["descripcion"] == ""
