"""Tests de la API del TABLERO de contenido unificado (`/api/contenido`).

Cubren el CRUD del padre, las filas por plataforma (estado + checklist), el `vencido`
derivado del deadline, la promocion desde el Radar y las validaciones (marca/red/estado/
responsable). Multiusuario con login real; reusa el aislamiento de `entorno` (Postgres) y
los fakes de `conftest`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

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


def _cli_admin(usuario: str = "jefa") -> TestClient:
    auth.crear_usuario(usuario, _CLAVE, "admin")
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


def test_post_directo_crea_borradores_con_copy(entorno):
    """El alta directa deposita UNA pieza-borrador por red con el copy FINAL del equipo."""
    c = _cli()
    r = c.post(
        "/api/contenido/post-directo",
        json={
            "titulo": "Arranque del Mundial",
            "copy": "Arranca el Mundial 2026 en CDMX 🎉",
            "marca": "unotv",
            "redes": ["x", "instagram"],
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    # Origen propio, EXCLUIDO de la auto-generación: aquí no hay nada que redactar.
    assert cont["origen"] == "post-directo"
    assert {p["red"] for p in cont["plataformas"]} == {"x", "instagram"}
    # Las piezas nacen con el copy del humano y a falta SOLO del arte.
    assert all(p["copy"] == "Arranca el Mundial 2026 en CDMX 🎉" for p in cont["plataformas"])
    assert all(not p["falta_copy"] for p in cont["plataformas"])
    assert all(p["falta_imagen"] for p in cont["plataformas"])
    # Y son PUBLICACIONES del feed (mismo motor que el copy generado), no checklist suelto.
    pubs = c.get("/api/publicaciones").json()["publicaciones"]
    assert {p["red"] for p in pubs} == {"x", "instagram"}
    assert all(p["contenido"] == "Arranca el Mundial 2026 en CDMX 🎉" for p in pubs)
    assert all(p["contenido_id"] == cont["id"] for p in pubs)


def test_post_directo_deriva_titulo_y_redes_por_defecto(entorno):
    """Sin título usa la primera línea del copy; sin redes, las del formato foto."""
    c = _cli()
    r = c.post(
        "/api/contenido/post-directo",
        json={"copy": "Última hora desde el estadio.\n\nMéxico gana 2-1.", "marca": "unotv"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["titulo"] == "Última hora desde el estadio."
    # Mismas redes a las que el flujo automático manda una pieza foto.
    assert {p["red"] for p in cont["plataformas"]} == {"instagram", "x", "facebook"}


def test_post_directo_validaciones_400(entorno):
    c = _cli()
    # Sin copy no hay post (es justo lo que diferencia esta alta).
    r = c.post("/api/contenido/post-directo", json={"marca": "unotv"}, headers=_ORIGIN)
    assert r.status_code == 400
    # La marca es obligatoria y debe existir.
    r = c.post("/api/contenido/post-directo", json={"copy": "Hola"}, headers=_ORIGIN)
    assert r.status_code == 400
    r = c.post(
        "/api/contenido/post-directo",
        json={"copy": "Hola", "marca": "no-existe"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    # Una red desconocida (o el canal "web" del tablero) se rechaza: esto crea publicaciones.
    r = c.post(
        "/api/contenido/post-directo",
        json={"copy": "Hola", "marca": "unotv", "redes": ["web"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


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


# --------------------------------------------------------------------------- #
# "Coger" / "Soltar": reparto de tareas SIN solaparse (la lista de ClaroSports)
# --------------------------------------------------------------------------- #


def test_coger_asigna_al_usuario(entorno):
    c = _cli("ana")
    cont = c.post(
        "/api/contenido", json={"titulo": "Cubrir partido"}, headers=_ORIGIN
    ).json()["contenido"]
    assert (cont.get("responsable_id") or "") == ""  # nace libre (sin rota)
    r = c.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_nombre"] == "ana"


def test_coger_doble_da_409_sin_pisar(entorno):
    c_ana = _cli("ana")
    c_luis = _cli("luis")
    cont = c_ana.post(
        "/api/contenido", json={"titulo": "Una sola"}, headers=_ORIGIN
    ).json()["contenido"]
    r1 = c_luis.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    assert r1.status_code == 200
    assert r1.json()["contenido"]["responsable_nombre"] == "luis"
    # ana intenta coger lo que ya tiene luis: 409, sin pisar.
    r2 = c_ana.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    assert r2.status_code == 409
    assert r2.json()["responsable_nombre"] == "luis"


def test_coger_idempotente_si_ya_es_mia(entorno):
    c = _cli("ana")
    cont = c.post("/api/contenido", json={"titulo": "Mía"}, headers=_ORIGIN).json()["contenido"]
    assert c.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN).status_code == 200
    assert c.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN).status_code == 200


def test_soltar_libera_y_otro_puede_coger(entorno):
    c_ana = _cli("ana")
    c_luis = _cli("luis")
    cont = c_ana.post(
        "/api/contenido", json={"titulo": "Para soltar"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    r = c_luis.post(f"/api/contenido/{cont['id']}/soltar", headers=_ORIGIN)
    assert r.status_code == 200
    assert (r.json()["contenido"].get("responsable_id") or "") == ""
    # Liberada: ahora ana sí puede cogerla.
    assert c_ana.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN).status_code == 200


def test_soltar_ajeno_da_403(entorno):
    c_ana = _cli("ana")
    c_luis = _cli("luis")
    cont = c_ana.post(
        "/api/contenido", json={"titulo": "De luis"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    # ana (editor, no admin) no puede soltar lo de luis.
    assert c_ana.post(f"/api/contenido/{cont['id']}/soltar", headers=_ORIGIN).status_code == 403


def test_coger_inexistente_404(entorno):
    c = _cli()
    assert c.post("/api/contenido/fantasma/coger", headers=_ORIGIN).status_code == 404


def test_soltar_admin_libera_lo_de_otro(entorno):
    c_luis = _cli("luis")
    c_admin = _cli_admin()
    cont = c_luis.post(
        "/api/contenido", json={"titulo": "Balancear"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    r = c_admin.post(f"/api/contenido/{cont['id']}/soltar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert (r.json()["contenido"].get("responsable_id") or "") == ""


def test_soltar_ya_libre_idempotente(entorno):
    c = _cli("ana")
    cont = c.post(
        "/api/contenido", json={"titulo": "Nadie la tiene"}, headers=_ORIGIN
    ).json()["contenido"]
    assert (cont.get("responsable_id") or "") == ""
    r = c.post(f"/api/contenido/{cont['id']}/soltar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert (r.json()["contenido"].get("responsable_id") or "") == ""


# --------------------------------------------------------------------------- #
# PATCH responsable_id: el claim no se roba por la puerta de atrás              #
# --------------------------------------------------------------------------- #


def test_patch_no_roba_ni_limpia_el_claim_de_otro(entorno):
    """Reasignar o limpiar por PATCH una pieza cogida por otra persona -> 409 sin pisar."""
    c_ana = _cli("ana")
    c_luis = _cli("luis")
    cont = c_ana.post(
        "/api/contenido", json={"titulo": "Cogida"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    # ana (editor, no admin) intenta robársela para sí misma: 409 con quién la tiene.
    r = c_ana.patch(
        f"/api/contenido/{cont['id']}",
        json={"responsable_id": _id_usuario("ana")},
        headers=_ORIGIN,
    )
    assert r.status_code == 409
    assert r.json()["responsable_nombre"] == "luis"
    # Tampoco puede liberarla (eso es `soltar`, con su propia guarda).
    r2 = c_ana.patch(
        f"/api/contenido/{cont['id']}", json={"responsable_id": ""}, headers=_ORIGIN
    )
    assert r2.status_code == 409
    # No se pisó: sigue siendo de luis.
    pieza = next(
        i for i in c_ana.get("/api/contenido").json()["contenidos"] if i["id"] == cont["id"]
    )
    assert pieza["responsable_id"] == _id_usuario("luis")


def test_patch_holder_reasigna_o_limpia_lo_suyo(entorno):
    c_ana = _cli("ana")
    _cli("luis")
    luis = _id_usuario("luis")
    # Pasar el testigo: ana reasigna SU pieza a luis.
    cont = c_ana.post(
        "/api/contenido", json={"titulo": "Testigo"}, headers=_ORIGIN
    ).json()["contenido"]
    c_ana.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    r = c_ana.patch(
        f"/api/contenido/{cont['id']}", json={"responsable_id": luis}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_id"] == luis
    # Limpiar lo propio (equivalente a soltar) también está permitido.
    cont2 = c_ana.post(
        "/api/contenido", json={"titulo": "Para limpiar"}, headers=_ORIGIN
    ).json()["contenido"]
    c_ana.post(f"/api/contenido/{cont2['id']}/coger", headers=_ORIGIN)
    r2 = c_ana.patch(
        f"/api/contenido/{cont2['id']}", json={"responsable_id": ""}, headers=_ORIGIN
    )
    assert r2.status_code == 200, r2.text
    assert (r2.json()["contenido"].get("responsable_id") or "") == ""


def test_patch_admin_reasigna_lo_de_otro(entorno):
    c_luis = _cli("luis")
    _cli("ana")
    c_admin = _cli_admin()
    cont = c_luis.post(
        "/api/contenido", json={"titulo": "Balanceo"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    r = c_admin.patch(
        f"/api/contenido/{cont['id']}",
        json={"responsable_id": _id_usuario("ana")},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_nombre"] == "ana"


def test_patch_asignar_pieza_libre_sigue_abierto(entorno):
    """Asignar una pieza LIBRE vía PATCH lo puede hacer cualquiera (flujo de tareas)."""
    c_ana = _cli("ana")
    _cli("luis")
    luis = _id_usuario("luis")
    cont = c_ana.post(
        "/api/contenido", json={"titulo": "Libre"}, headers=_ORIGIN
    ).json()["contenido"]
    assert (cont.get("responsable_id") or "") == ""
    r = c_ana.patch(
        f"/api/contenido/{cont['id']}", json={"responsable_id": luis}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_id"] == luis


# --------------------------------------------------------------------------- #
# POST /asignar: el manager EMPUJA a una persona (2ª puerta del responsable)    #
# self-claim = `coger` (CAS contra vacío); asignar = override del admin (push). #
# --------------------------------------------------------------------------- #


def test_asignar_admin_empuja_a_persona_libre(entorno):
    """El admin asigna una pieza LIBRE a un compañero concreto (push, no self-claim)."""
    _cli("luis")
    c_admin = _cli_admin()
    luis = _id_usuario("luis")
    cont = c_admin.post(
        "/api/contenido", json={"titulo": "Reparto"}, headers=_ORIGIN
    ).json()["contenido"]
    r = c_admin.post(
        f"/api/contenido/{cont['id']}/asignar",
        json={"responsable_id": luis},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_id"] == luis
    assert r.json()["contenido"]["responsable_nombre"] == "luis"


def test_asignar_admin_reasigna_pisando_a_otro(entorno):
    """Reasignar (override): el admin pasa a OTRA persona una pieza ya cogida, sin 409."""
    c_luis = _cli("luis")
    _cli("ana")
    c_admin = _cli_admin()
    ana = _id_usuario("ana")
    cont = c_luis.post(
        "/api/contenido", json={"titulo": "Cambio de manos"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/contenido/{cont['id']}/coger", headers=_ORIGIN)
    r = c_admin.post(
        f"/api/contenido/{cont['id']}/asignar",
        json={"responsable_id": ana},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_id"] == ana


def test_asignar_no_admin_da_403(entorno):
    """Un editor NO empuja trabajo a otros: reparte cogiendo del pool, no asignando."""
    c_ana = _cli("ana")
    _cli("luis")
    luis = _id_usuario("luis")
    cont = c_ana.post(
        "/api/contenido", json={"titulo": "Solo manager"}, headers=_ORIGIN
    ).json()["contenido"]
    r = c_ana.post(
        f"/api/contenido/{cont['id']}/asignar",
        json={"responsable_id": luis},
        headers=_ORIGIN,
    )
    assert r.status_code == 403


def test_asignar_persona_invalida_da_400(entorno):
    c_admin = _cli_admin()
    cont = c_admin.post(
        "/api/contenido", json={"titulo": "Fantasma"}, headers=_ORIGIN
    ).json()["contenido"]
    r = c_admin.post(
        f"/api/contenido/{cont['id']}/asignar",
        json={"responsable_id": "no-existe"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_asignar_sin_persona_da_400(entorno):
    """`asignar` exige a quién; liberar es `soltar`, no asignar a vacío."""
    _cli("luis")
    c_admin = _cli_admin()
    luis = _id_usuario("luis")
    cont = c_admin.post(
        "/api/contenido", json={"titulo": "Vacío"}, headers=_ORIGIN
    ).json()["contenido"]
    c_admin.post(
        f"/api/contenido/{cont['id']}/asignar",
        json={"responsable_id": luis},
        headers=_ORIGIN,
    )
    r = c_admin.post(
        f"/api/contenido/{cont['id']}/asignar", json={"responsable_id": ""}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_asignar_inexistente_da_404(entorno):
    c_admin = _cli_admin()
    r = c_admin.post(
        "/api/contenido/fantasma/asignar",
        json={"responsable_id": _id_usuario("jefa")},
        headers=_ORIGIN,
    )
    assert r.status_code == 404


def test_asignar_notifica_al_asignado(entorno):
    """La señal que retira el «te paso esto» del chat: el asignado recibe una notificación."""
    _cli("luis")
    c_admin = _cli_admin()
    luis = _id_usuario("luis")
    cont = c_admin.post(
        "/api/contenido", json={"titulo": "Avísale"}, headers=_ORIGIN
    ).json()["contenido"]
    c_admin.post(
        f"/api/contenido/{cont['id']}/asignar",
        json={"responsable_id": luis},
        headers=_ORIGIN,
    )
    notis = repos.listar_notificaciones(luis, None)
    assert any(
        n["tipo"] == "asignacion" and n["contenido_id"] == cont["id"] for n in notis
    )
