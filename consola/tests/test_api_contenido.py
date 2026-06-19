"""Tests de la API del TABLERO de contenido unificado (`/api/publicaciones`).

Cubren el CRUD del padre, las filas por plataforma (estado + checklist), el `vencido`
derivado del deadline, la promocion desde el Radar y las validaciones (marca/red/estado/
responsable). Multiusuario con login real; reusa el aislamiento de `entorno` (Postgres) y
los fakes de `conftest`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos
from keni_consola.dominio import extraccion_url

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
    cuerpo = c.get("/api/publicaciones").json()
    assert cuerpo["contenidos"] == []
    cat = cuerpo["catalogos"]
    assert {"importante", "evergreen", "evento"} <= set(cat["flujos"])
    assert any(r["id"] == "web" for r in cat["redes"])
    assert "ana" in {u["usuario"] for u in cat["usuarios"]}


def test_crear_contenido_con_plataformas(entorno):
    c = _cli()
    r = c.post(
        "/api/publicaciones",
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


def test_crear_contenido_nace_con_origen_equipo(entorno):
    """El alta de CONTENIDO desde el tablero/MCP nace con origen 'equipo': la etapa de Redactar
    del pipeline lo recoge y le escribe el copy con el mismo rigor que a cualquier otro origen."""
    c = _cli()
    cont = c.post(
        "/api/publicaciones",
        json={"titulo": "Nota del tablero", "marca": "unotv", "redes": ["x"]},
        headers=_ORIGIN,
    ).json()["contenido"]
    assert cont["origen"] == "equipo"


def test_crear_tarea_no_es_contenido_de_feed(entorno):
    """Una TAREA no es contenido de feed: queda con origen "" y fuera de la auto-generación."""
    c = _cli()
    cont = c.post(
        "/api/publicaciones",
        json={"titulo": "Revisar pendientes", "clase": "tarea"},
        headers=_ORIGIN,
    ).json()["contenido"]
    assert cont["origen"] == ""


def test_crear_con_formato_video_crea_cinco_redes(entorno):
    """`formato=video` crea las 5 redes (foto=3 + youtube + tiktok) con falta_video activo."""
    c = _cli()
    r = c.post(
        "/api/publicaciones",
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
        "/api/publicaciones", json={"titulo": "Foto", "formato": "foto"}, headers=_ORIGIN
    ).json()["contenido"]
    assert {p["red"] for p in cont["plataformas"]} == {"instagram", "x", "facebook"}
    assert all(not p["falta_video"] for p in cont["plataformas"])


def test_flip_a_video_via_patch_contenido(entorno):
    """PATCH /api/publicaciones con {formato:'video'} añade youtube+tiktok y devuelve el resumen."""
    c = _cli()
    cont = c.post(
        "/api/publicaciones", json={"titulo": "Pieza", "formato": "foto"}, headers=_ORIGIN
    ).json()["contenido"]
    r = c.patch(f"/api/publicaciones/{cont['id']}", json={"formato": "video"}, headers=_ORIGIN)
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
        "/api/publicaciones", json={"titulo": "Pieza", "formato": "video"}, headers=_ORIGIN
    ).json()["contenido"]
    yt = next(p for p in cont["plataformas"] if p["red"] == "youtube")
    c.patch(
        f"/api/publicaciones/{cont['id']}/plataformas/{yt['id']}",
        json={"copy": "Guion"},
        headers=_ORIGIN,
    )
    r = c.patch(f"/api/publicaciones/{cont['id']}", json={"formato": "foto"}, headers=_ORIGIN)
    assert r.status_code == 200
    cuerpo = r.json()
    assert "youtube" in cuerpo["ajuste_formato"]["conservadas"]
    assert "aviso" in cuerpo


def test_patch_plataforma_fija_video_y_limpia_falta_video(entorno):
    """Adjuntar {video} en una fila limpia falta_video (espejo de imagen/falta_imagen)."""
    c = _cli()
    cont = c.post(
        "/api/publicaciones", json={"titulo": "Clip", "formato": "video"}, headers=_ORIGIN
    ).json()["contenido"]
    plat = next(p for p in cont["plataformas"] if p["red"] == "tiktok")
    assert plat["falta_video"] is True
    r = c.patch(
        f"/api/publicaciones/{cont['id']}/plataformas/{plat['id']}",
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
    c.post("/api/publicaciones", json={"titulo": "Nota A", "flujo": "evergreen"}, headers=_ORIGIN)
    cuerpo = c.get("/api/publicaciones?flujo=evergreen").json()
    assert [x["titulo"] for x in cuerpo["contenidos"]] == ["Nota A"]


def test_deadline_vencido_se_marca(entorno):
    c = _cli()
    r = c.post(
        "/api/publicaciones",
        json={"titulo": "Atrasada", "fecha_entrega": "2000-01-01"},
        headers=_ORIGIN,
    )
    assert r.json()["contenido"]["vencido"] is True


def test_actualizar_plataforma_estado_y_checklist(entorno):
    c = _cli()
    cont = c.post(
        "/api/publicaciones", json={"titulo": "C", "redes": ["x"]}, headers=_ORIGIN
    ).json()["contenido"]
    plat_id = cont["plataformas"][0]["id"]
    r = c.patch(
        f"/api/publicaciones/{cont['id']}/plataformas/{plat_id}",
        json={"estado": "en_revision", "falta_copy": False, "copy": "¡Listo!"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    plat = r.json()["plataforma"]
    assert plat["estado"] == "en_revision"
    assert plat["falta_copy"] is False
    assert plat["copy"] == "¡Listo!"


def test_estado_plataforma_invalido_se_rechaza(entorno):
    c = _cli()
    cont = c.post(
        "/api/publicaciones", json={"titulo": "C", "redes": ["x"]}, headers=_ORIGIN
    ).json()["contenido"]
    plat_id = cont["plataformas"][0]["id"]
    r = c.patch(
        f"/api/publicaciones/{cont['id']}/plataformas/{plat_id}",
        json={"estado": "inventado"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_agregar_y_borrar_plataforma(entorno):
    c = _cli()
    cont = c.post("/api/publicaciones", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.post(
        f"/api/publicaciones/{cont['id']}/plataformas", json={"red": "tiktok"}, headers=_ORIGIN
    )
    assert r.status_code == 200
    plat_id = r.json()["plataforma"]["id"]
    assert c.request("DELETE", f"/api/publicaciones/{cont['id']}/plataformas/{plat_id}").status_code == 200


def test_crear_rechaza_marca_y_red_invalidas(entorno):
    c = _cli()
    assert c.post("/api/publicaciones", json={"titulo": "X", "marca": "no-existe"}, headers=_ORIGIN).status_code == 400
    assert c.post("/api/publicaciones", json={"titulo": "X", "redes": ["myspace"]}, headers=_ORIGIN).status_code == 400


def test_crear_sin_titulo_400(entorno):
    c = _cli()
    assert c.post("/api/publicaciones", json={"flujo": "importante"}, headers=_ORIGIN).status_code == 400


def test_asignar_responsable_real(entorno):
    c = _cli("ana")
    _cli("luis")
    luis = _id_usuario("luis")
    cont = c.post("/api/publicaciones", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.patch(
        f"/api/publicaciones/{cont['id']}", json={"responsable_id": luis}, headers=_ORIGIN
    )
    assert r.status_code == 200
    assert r.json()["contenido"]["responsable_nombre"] == "luis"


def test_responsable_inexistente_se_rechaza(entorno):
    c = _cli()
    cont = c.post("/api/publicaciones", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.patch(
        f"/api/publicaciones/{cont['id']}", json={"responsable_id": "fantasma"}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_desde_radar_crea_importante(entorno):
    c = _cli()
    r = c.post(
        "/api/publicaciones/desde-radar",
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
    cont = c.post("/api/publicaciones", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    assert c.request("DELETE", f"/api/publicaciones/{cont['id']}").status_code == 200
    assert c.get("/api/publicaciones").json()["contenidos"] == []


def test_adaptar_imagen_por_red_asigna_a_cada_plataforma(entorno, monkeypatch):
    from keni_consola.dominio import estudio_imagen

    c = _cli()
    cont = c.post(
        "/api/publicaciones",
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
        f"/api/publicaciones/{cont['id']}/adaptar-imagen",
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
    tablero = c.get("/api/publicaciones").json()["contenidos"][0]
    assert all(p["imagen"].startswith("adapt-") for p in tablero["plataformas"])


def test_adaptar_imagen_sin_imagen_400(entorno):
    c = _cli()
    cont = c.post(
        "/api/publicaciones", json={"titulo": "X", "redes": ["x"]}, headers=_ORIGIN
    ).json()["contenido"]
    r = c.post(f"/api/publicaciones/{cont['id']}/adaptar-imagen", json={}, headers=_ORIGIN)
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Puerta creativa del equipo: POST /api/publicaciones/aportar (Fase 1 / Flujo A)    #
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
        "/api/publicaciones/aportar",
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
    # El alta enciende la generación de copy EN EL MOMENTO (mismo camino que Radar/usar-noticia):
    # no depende solo del barrido del pipeline.
    assert r.json()["copy_en_proceso"] is True


def test_aportar_persiste_la_categoria_del_plan(entorno):
    """«Crear post» manda la categoría (obligatoria en la UI) y se guarda en el contenido padre:
    así la pieza casa con su franja y se programa sola al aprobarse (sin categoría no habría hueco)."""
    c = _cli()
    r = c.post(
        "/api/publicaciones/aportar",
        data={"marca": "unotv", "material": "Nota del equipo.", "categoria": "mx", "redes": "x"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["categoria"] == "mx"


def test_aportar_exige_marca(entorno):
    c = _cli()
    # Sin marca: la puerta creativa la EXIGE (sin voz no hay auto-generacion).
    r = c.post(
        "/api/publicaciones/aportar",
        data={"titulo": "Idea suelta", "material": "algo"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    # Marca inexistente tambien se rechaza.
    r2 = c.post(
        "/api/publicaciones/aportar",
        data={"titulo": "Idea", "marca": "no-existe"},
        headers=_ORIGIN,
    )
    assert r2.status_code == 400


def test_aportar_sin_titulo_ni_contenido_400(entorno):
    c = _cli()
    # El titulo es opcional, pero un alta SIN titulo y SIN nada que aportar (ni material, ni
    # enlace, ni imagen) no tiene de que generar copy: se rechaza.
    r = c.post(
        "/api/publicaciones/aportar", data={"marca": "unotv"}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_aportar_sin_titulo_deriva_de_material(entorno):
    c = _cli()
    # Sin titulo explicito, se DERIVA de la 1a linea no vacia del material (rotulo del feed).
    r = c.post(
        "/api/publicaciones/aportar",
        data={
            "marca": "unotv",
            "material": "Remontada histórica en el clásico\nGanó 3-2 en el descuento.",
            "redes": "x",
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["titulo"] == "Remontada histórica en el clásico"
    assert "Ganó 3-2" in cont["descripcion"]
    assert cont["origen"] == "equipo"


def test_aportar_desde_url_extrae_texto_y_deriva_titulo(entorno, monkeypatch):
    c = _cli()
    # Se pega SOLO un enlace: la puerta creativa lo VALIDA, descarga la pagina EN EL SERVIDOR
    # (descargador inyectable, sin red real) y pliega su texto al material como nota NO
    # verificada, para que el auto-copy redacte desde el contenido real. El titulo se deriva del
    # titular de la pagina. Parcheamos `validar_url` (evita DNS/SSRF real) y el `_DESCARGADOR`.
    html = (
        "<html><head><title>Gol en el último minuto</title></head>"
        "<body><article><p>El delantero marcó en el 90+4 y el estadio estalló.</p>"
        "</article></body></html>"
    )
    monkeypatch.setattr(extraccion_url, "validar_url", lambda u: (u, None))
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR", lambda url: html)
    r = c.post(
        "/api/publicaciones/aportar",
        data={"marca": "unotv", "url": "https://ejemplo.mx/nota", "redes": "x"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    # Titulo derivado del titular real de la pagina (no de la URL a secas).
    assert cont["titulo"] == "Gol en el último minuto"
    # El texto extraido entra como descripcion (nota base del auto-copy), marcado NO verificado.
    assert "El delantero marcó" in cont["descripcion"]
    assert "NO VERIFICADO" in cont["descripcion"]
    assert cont["origen"] == "equipo"


def test_aportar_url_ilegible_y_sin_mas_contenido_400(entorno, monkeypatch):
    c = _cli()
    # Si el enlace no se puede leer (aqui forzamos un fallo de extraccion) y es lo UNICO que se
    # aporto, no hay de que redactar: se rechaza con mensaje claro (no se crea una pieza vacia).
    def _boom(url):
        raise extraccion_url.ExtraccionError("No se pudo leer la página.")

    monkeypatch.setattr(extraccion_url, "validar_url", lambda u: (u, None))
    monkeypatch.setattr(extraccion_url, "extraer_texto", _boom)
    r = c.post(
        "/api/publicaciones/aportar",
        data={"marca": "unotv", "url": "https://ejemplo.mx/nota"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_aportar_con_imagen_adjunta_se_guarda_como_foto(entorno):
    c = _cli()
    r = c.post(
        "/api/publicaciones/aportar",
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
        "/api/publicaciones/aportar",
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
        "/api/publicaciones/post-directo",
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
    # Y son PIEZAS del feed (mismo motor que el copy generado), no checklist suelto.
    pubs = c.get("/api/piezas").json()["piezas"]
    assert {p["red"] for p in pubs} == {"x", "instagram"}
    assert all(p["contenido"] == "Arranca el Mundial 2026 en CDMX 🎉" for p in pubs)
    assert all(p["publicacion_id"] == cont["id"] for p in pubs)


def test_post_directo_deriva_titulo_y_redes_por_defecto(entorno):
    """Sin título usa la primera línea del copy; sin redes, las del formato foto."""
    c = _cli()
    r = c.post(
        "/api/publicaciones/post-directo",
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
    r = c.post("/api/publicaciones/post-directo", json={"marca": "unotv"}, headers=_ORIGIN)
    assert r.status_code == 400
    # La marca es obligatoria y debe existir.
    r = c.post("/api/publicaciones/post-directo", json={"copy": "Hola"}, headers=_ORIGIN)
    assert r.status_code == 400
    r = c.post(
        "/api/publicaciones/post-directo",
        json={"copy": "Hola", "marca": "no-existe"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    # Una red desconocida (o el canal "web" del tablero) se rechaza: esto crea piezas.
    r = c.post(
        "/api/publicaciones/post-directo",
        json={"copy": "Hola", "marca": "unotv", "redes": ["web"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


# Bytes mínimos de un "clip" (no es un MP4 real: la transcripción real está MOCKEADA).
_CLIP_FALSO = b"\x00\x00\x00\x18ftypmp42fakeclipbytes"


def test_aportar_con_clip_transcribe_en_local(entorno, monkeypatch):
    """El clip de vídeo/audio se transcribe EN LOCAL (mock) y el texto entra como material."""
    from keni_consola import transcripcion

    # Mock del motor de transcripcion: nunca carga faster-whisper ni el modelo reales.
    monkeypatch.setattr(
        transcripcion, "_TRANSCRIPTOR_JSON",
        lambda datos, *, ext, idioma="es", word_level=False: {
            "texto": "Hoy ganamos tres a cero.", "segmentos": []
        },
    )

    c = _cli()
    r = c.post(
        "/api/publicaciones/aportar",
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

    monkeypatch.setattr(
        transcripcion, "_TRANSCRIPTOR_JSON",
        lambda datos, *, ext, idioma="es", word_level=False: {"texto": "lo que se dijo", "segmentos": []},
    )

    c = _cli()
    r = c.post(
        "/api/publicaciones/aportar",
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
        "/api/publicaciones/aportar",
        data={"titulo": "T", "marca": "unotv", "redes": "x"},
        files={"clip": ("notas.txt", b"hola", "text/plain")},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    assert "vídeo o audio" in r.json()["error"].lower()


def test_aportar_clip_sin_habla_no_rompe(entorno, monkeypatch):
    """Un clip que transcribe a vacío crea la pieza igualmente (sin material del clip)."""
    from keni_consola import transcripcion

    monkeypatch.setattr(
        transcripcion, "_TRANSCRIPTOR_JSON",
        lambda datos, *, ext, idioma="es", word_level=False: {"texto": "", "segmentos": []},
    )

    c = _cli()
    r = c.post(
        "/api/publicaciones/aportar",
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
        "/api/publicaciones", json={"titulo": "Cubrir partido"}, headers=_ORIGIN
    ).json()["contenido"]
    assert (cont.get("responsable_id") or "") == ""  # nace libre (sin rota)
    r = c.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_nombre"] == "ana"


def test_coger_doble_da_409_sin_pisar(entorno):
    c_ana = _cli("ana")
    c_luis = _cli("luis")
    cont = c_ana.post(
        "/api/publicaciones", json={"titulo": "Una sola"}, headers=_ORIGIN
    ).json()["contenido"]
    r1 = c_luis.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    assert r1.status_code == 200
    assert r1.json()["contenido"]["responsable_nombre"] == "luis"
    # ana intenta coger lo que ya tiene luis: 409, sin pisar.
    r2 = c_ana.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    assert r2.status_code == 409
    assert r2.json()["responsable_nombre"] == "luis"


def test_coger_idempotente_si_ya_es_mia(entorno):
    c = _cli("ana")
    cont = c.post("/api/publicaciones", json={"titulo": "Mía"}, headers=_ORIGIN).json()["contenido"]
    assert c.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN).status_code == 200
    assert c.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN).status_code == 200


def test_soltar_libera_y_otro_puede_coger(entorno):
    c_ana = _cli("ana")
    c_luis = _cli("luis")
    cont = c_ana.post(
        "/api/publicaciones", json={"titulo": "Para soltar"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    r = c_luis.post(f"/api/publicaciones/{cont['id']}/soltar", headers=_ORIGIN)
    assert r.status_code == 200
    assert (r.json()["contenido"].get("responsable_id") or "") == ""
    # Liberada: ahora ana sí puede cogerla.
    assert c_ana.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN).status_code == 200


def test_soltar_ajeno_da_403(entorno):
    c_ana = _cli("ana")
    c_luis = _cli("luis")
    cont = c_ana.post(
        "/api/publicaciones", json={"titulo": "De luis"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    # ana (editor, no admin) no puede soltar lo de luis.
    assert c_ana.post(f"/api/publicaciones/{cont['id']}/soltar", headers=_ORIGIN).status_code == 403


def test_coger_inexistente_404(entorno):
    c = _cli()
    assert c.post("/api/publicaciones/fantasma/coger", headers=_ORIGIN).status_code == 404


def test_soltar_admin_libera_lo_de_otro(entorno):
    c_luis = _cli("luis")
    c_admin = _cli_admin()
    cont = c_luis.post(
        "/api/publicaciones", json={"titulo": "Balancear"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    r = c_admin.post(f"/api/publicaciones/{cont['id']}/soltar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert (r.json()["contenido"].get("responsable_id") or "") == ""


def test_soltar_ya_libre_idempotente(entorno):
    c = _cli("ana")
    cont = c.post(
        "/api/publicaciones", json={"titulo": "Nadie la tiene"}, headers=_ORIGIN
    ).json()["contenido"]
    assert (cont.get("responsable_id") or "") == ""
    r = c.post(f"/api/publicaciones/{cont['id']}/soltar", headers=_ORIGIN)
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
        "/api/publicaciones", json={"titulo": "Cogida"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    # ana (editor, no admin) intenta robársela para sí misma: 409 con quién la tiene.
    r = c_ana.patch(
        f"/api/publicaciones/{cont['id']}",
        json={"responsable_id": _id_usuario("ana")},
        headers=_ORIGIN,
    )
    assert r.status_code == 409
    assert r.json()["responsable_nombre"] == "luis"
    # Tampoco puede liberarla (eso es `soltar`, con su propia guarda).
    r2 = c_ana.patch(
        f"/api/publicaciones/{cont['id']}", json={"responsable_id": ""}, headers=_ORIGIN
    )
    assert r2.status_code == 409
    # No se pisó: sigue siendo de luis.
    pieza = next(
        i for i in c_ana.get("/api/publicaciones").json()["contenidos"] if i["id"] == cont["id"]
    )
    assert pieza["responsable_id"] == _id_usuario("luis")


def test_patch_holder_reasigna_o_limpia_lo_suyo(entorno):
    c_ana = _cli("ana")
    _cli("luis")
    luis = _id_usuario("luis")
    # Pasar el testigo: ana reasigna SU pieza a luis.
    cont = c_ana.post(
        "/api/publicaciones", json={"titulo": "Testigo"}, headers=_ORIGIN
    ).json()["contenido"]
    c_ana.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    r = c_ana.patch(
        f"/api/publicaciones/{cont['id']}", json={"responsable_id": luis}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_id"] == luis
    # Limpiar lo propio (equivalente a soltar) también está permitido.
    cont2 = c_ana.post(
        "/api/publicaciones", json={"titulo": "Para limpiar"}, headers=_ORIGIN
    ).json()["contenido"]
    c_ana.post(f"/api/publicaciones/{cont2['id']}/coger", headers=_ORIGIN)
    r2 = c_ana.patch(
        f"/api/publicaciones/{cont2['id']}", json={"responsable_id": ""}, headers=_ORIGIN
    )
    assert r2.status_code == 200, r2.text
    assert (r2.json()["contenido"].get("responsable_id") or "") == ""


def test_patch_admin_reasigna_lo_de_otro(entorno):
    c_luis = _cli("luis")
    _cli("ana")
    c_admin = _cli_admin()
    cont = c_luis.post(
        "/api/publicaciones", json={"titulo": "Balanceo"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    r = c_admin.patch(
        f"/api/publicaciones/{cont['id']}",
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
        "/api/publicaciones", json={"titulo": "Libre"}, headers=_ORIGIN
    ).json()["contenido"]
    assert (cont.get("responsable_id") or "") == ""
    r = c_ana.patch(
        f"/api/publicaciones/{cont['id']}", json={"responsable_id": luis}, headers=_ORIGIN
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
        "/api/publicaciones", json={"titulo": "Reparto"}, headers=_ORIGIN
    ).json()["contenido"]
    r = c_admin.post(
        f"/api/publicaciones/{cont['id']}/asignar",
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
        "/api/publicaciones", json={"titulo": "Cambio de manos"}, headers=_ORIGIN
    ).json()["contenido"]
    c_luis.post(f"/api/publicaciones/{cont['id']}/coger", headers=_ORIGIN)
    r = c_admin.post(
        f"/api/publicaciones/{cont['id']}/asignar",
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
        "/api/publicaciones", json={"titulo": "Solo manager"}, headers=_ORIGIN
    ).json()["contenido"]
    r = c_ana.post(
        f"/api/publicaciones/{cont['id']}/asignar",
        json={"responsable_id": luis},
        headers=_ORIGIN,
    )
    assert r.status_code == 403


def test_asignar_persona_invalida_da_400(entorno):
    c_admin = _cli_admin()
    cont = c_admin.post(
        "/api/publicaciones", json={"titulo": "Fantasma"}, headers=_ORIGIN
    ).json()["contenido"]
    r = c_admin.post(
        f"/api/publicaciones/{cont['id']}/asignar",
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
        "/api/publicaciones", json={"titulo": "Vacío"}, headers=_ORIGIN
    ).json()["contenido"]
    c_admin.post(
        f"/api/publicaciones/{cont['id']}/asignar",
        json={"responsable_id": luis},
        headers=_ORIGIN,
    )
    r = c_admin.post(
        f"/api/publicaciones/{cont['id']}/asignar", json={"responsable_id": ""}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_asignar_inexistente_da_404(entorno):
    c_admin = _cli_admin()
    r = c_admin.post(
        "/api/publicaciones/fantasma/asignar",
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
        "/api/publicaciones", json={"titulo": "Avísale"}, headers=_ORIGIN
    ).json()["contenido"]
    c_admin.post(
        f"/api/publicaciones/{cont['id']}/asignar",
        json={"responsable_id": luis},
        headers=_ORIGIN,
    )
    notis = repos.listar_notificaciones(luis, None)
    assert any(
        n["tipo"] == "asignacion" and n["publicacion_id"] == cont["id"] for n in notis
    )


# --------------------------------------------------------------------------- #
# POST /cubrir-evento: la lista de Tareas se llena de EVENTOS; cubrir uno =     #
# find-or-create de su tarea de cobertura (clase='tarea', evento_id) + claim.   #
# --------------------------------------------------------------------------- #


def _crear_evento(titulo: str = "Cruz Azul vs América", fecha: str = "2026-07-01") -> dict:
    return repos.crear_evento_rota(titulo=titulo, fecha=fecha, hora="20:00", marca="claro-sports")


def test_cubrir_evento_self_claim_crea_tarea_de_cobertura(entorno):
    c = _cli("ana")
    ev = _crear_evento()
    r = c.post("/api/publicaciones/cubrir-evento", json={"evento_id": ev["id"]}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["clase"] == "tarea"
    assert cont["evento_id"] == ev["id"]
    assert cont["responsable_id"] == _id_usuario("ana")
    assert cont["titulo"] == "Cruz Azul vs América"


def test_cubrir_evento_idempotente_por_persona(entorno):
    """Cubrir el mismo evento dos veces la MISMA persona NO crea dos tareas: find-or-create
    por (evento_id, responsable)."""
    c = _cli("ana")
    ev = _crear_evento()
    r1 = c.post("/api/publicaciones/cubrir-evento", json={"evento_id": ev["id"]}, headers=_ORIGIN)
    r2 = c.post("/api/publicaciones/cubrir-evento", json={"evento_id": ev["id"]}, headers=_ORIGIN)
    assert r1.status_code == 200 and r2.status_code == 200, r2.text
    assert r1.json()["contenido"]["id"] == r2.json()["contenido"]["id"]
    tareas = [
        x
        for x in c.get("/api/publicaciones?clase=tarea").json()["contenidos"]
        if x["evento_id"] == ev["id"]
    ]
    assert len(tareas) == 1


def test_cubrir_evento_otro_anade_cubridor(entorno):
    """Cubrir un evento que YA cubre otra persona AÑADE cubridor (multi-cobertura), no es 409:
    cada quien tiene su propia tarea de cobertura del mismo evento."""
    c_luis = _cli("luis")
    c_ana = _cli("ana")
    ev = _crear_evento()
    r1 = c_luis.post("/api/publicaciones/cubrir-evento", json={"evento_id": ev["id"]}, headers=_ORIGIN)
    r2 = c_ana.post("/api/publicaciones/cubrir-evento", json={"evento_id": ev["id"]}, headers=_ORIGIN)
    assert r1.status_code == 200 and r2.status_code == 200, r2.text
    tareas = [
        x
        for x in c_ana.get("/api/publicaciones?clase=tarea").json()["contenidos"]
        if x["evento_id"] == ev["id"]
    ]
    assert len(tareas) == 2
    assert {t["responsable_id"] for t in tareas} == {_id_usuario("luis"), _id_usuario("ana")}


def test_cubrir_evento_admin_asigna_a_otro_y_avisa(entorno):
    _cli("luis")
    c_admin = _cli_admin()
    luis = _id_usuario("luis")
    ev = _crear_evento()
    r = c_admin.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "responsable_id": luis},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["responsable_id"] == luis
    assert any(n["tipo"] == "asignacion" for n in repos.listar_notificaciones(luis, None))


def test_cubrir_evento_editor_no_asigna_a_otro_403(entorno):
    c_ana = _cli("ana")
    _cli("luis")
    luis = _id_usuario("luis")
    ev = _crear_evento()
    r = c_ana.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "responsable_id": luis},
        headers=_ORIGIN,
    )
    assert r.status_code == 403


def test_cubrir_evento_inexistente_404(entorno):
    c = _cli("ana")
    r = c.post(
        "/api/publicaciones/cubrir-evento", json={"evento_id": "fantasma"}, headers=_ORIGIN
    )
    assert r.status_code == 404


def test_cubrir_evento_con_rol_persiste_el_formato(entorno):
    """El `formato` (ROL de cobertura) se PERSISTE en la tarea. 'video' (formato del catálogo)
    y 'live' (rol de TEXTO LIBRE, fuera del catálogo de publicación) sobreviven SIN coaccionarse
    a 'foto': la columna es `TEXT` y la cobertura no toca el pipeline formato->redes."""
    c = _cli("ana")
    ev = _crear_evento()
    r = c.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "formato": "video"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["formato"] == "video"

    r2 = c.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "formato": "live"},
        headers=_ORIGIN,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["contenido"]["formato"] == "live"  # NO coaccionado a 'foto'


def test_cubrir_evento_mismo_rol_idempotente(entorno):
    """Misma persona + MISMO rol dos veces = find-or-create por (evento, persona, rol): 1 tarea."""
    c = _cli("ana")
    ev = _crear_evento()
    r1 = c.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "formato": "foto"},
        headers=_ORIGIN,
    )
    r2 = c.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "formato": "foto"},
        headers=_ORIGIN,
    )
    assert r1.status_code == 200 and r2.status_code == 200, r2.text
    assert r1.json()["contenido"]["id"] == r2.json()["contenido"]["id"]
    tareas = [
        x
        for x in c.get("/api/publicaciones?clase=tarea").json()["contenidos"]
        if x["evento_id"] == ev["id"]
    ]
    assert len(tareas) == 1


def test_cubrir_evento_dos_roles_misma_persona_dos_tareas(entorno):
    """Una persona puede llevar VARIOS roles del mismo evento: foto y video = 2 tareas suyas
    (no se pisan: la clave find-or-create incluye el rol)."""
    c = _cli("ana")
    ev = _crear_evento()
    r1 = c.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "formato": "foto"},
        headers=_ORIGIN,
    )
    r2 = c.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "formato": "video"},
        headers=_ORIGIN,
    )
    assert r1.status_code == 200 and r2.status_code == 200, r2.text
    assert r1.json()["contenido"]["id"] != r2.json()["contenido"]["id"]
    tareas = [
        x
        for x in c.get("/api/publicaciones?clase=tarea").json()["contenidos"]
        if x["evento_id"] == ev["id"]
    ]
    assert len(tareas) == 2
    assert {t["formato"] for t in tareas} == {"foto", "video"}
    assert {t["responsable_id"] for t in tareas} == {_id_usuario("ana")}


def test_cubrir_evento_rol_invalido_400(entorno):
    c = _cli("ana")
    ev = _crear_evento()
    r = c.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "formato": "basura"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_cubrir_evento_sin_rol_casa_cualquier_cobertura(entorno):
    """Retrocompat: cubrir SIN `formato` casa con CUALQUIER cobertura previa de la persona
    (no crea una segunda), aunque la previa tuviera un rol concreto."""
    c = _cli("ana")
    ev = _crear_evento()
    r1 = c.post(
        "/api/publicaciones/cubrir-evento",
        json={"evento_id": ev["id"], "formato": "video"},
        headers=_ORIGIN,
    )
    r2 = c.post(
        "/api/publicaciones/cubrir-evento", json={"evento_id": ev["id"]}, headers=_ORIGIN
    )
    assert r1.status_code == 200 and r2.status_code == 200, r2.text
    assert r1.json()["contenido"]["id"] == r2.json()["contenido"]["id"]
    tareas = [
        x
        for x in c.get("/api/publicaciones?clase=tarea").json()["contenidos"]
        if x["evento_id"] == ev["id"]
    ]
    assert len(tareas) == 1


def test_catalogos_usuarios_se_acotan_por_marca(entorno):
    """`catalogos.usuarios` = equipo de cobertura de la MARCA activa (cada marca su equipo);
    sin `?marca` salen todos (vista «Todas» del admin)."""
    c = _cli("ana")  # cobertura=True
    _cli("luis")  # cobertura=True, sin marcas → no es del equipo de claro-sports
    auth.reemplazar_marcas_de_usuario(_id_usuario("ana"), ["claro-sports"])

    con_marca = c.get("/api/publicaciones?clase=tarea&marca=claro-sports").json()["catalogos"]
    ids = {u["id"] for u in con_marca["usuarios"]}
    assert _id_usuario("ana") in ids
    assert _id_usuario("luis") not in ids

    sin_marca = c.get("/api/publicaciones?clase=tarea").json()["catalogos"]
    ids_todas = {u["id"] for u in sin_marca["usuarios"]}
    assert {_id_usuario("ana"), _id_usuario("luis")} <= ids_todas


# --------------------------------------------------------------------------- #
# POST /{id}/aceptar: una TAREA con fecha (propuesta de calendario) se PROMUEVE #
# al calendario de Turnos —crea el evento de la rota— y se consume la tarea.    #
# --------------------------------------------------------------------------- #


def _crear_tarea_propuesta(
    c, *, titulo="La Velada del Año VI", fecha="2026-07-26", detalle="Estadio Santiago Bernabéu"
) -> dict:
    """Crea una tarea SUELTA con fecha (propuesta de calendario) vía la API y la devuelve."""
    r = c.post(
        "/api/publicaciones",
        json={
            "clase": "tarea",
            "titulo": titulo,
            "fecha_objetivo": fecha,
            "descripcion": detalle,
            "marca": "claro-sports",
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    return r.json()["contenido"]


def test_aceptar_promueve_tarea_a_evento_y_la_consume(entorno):
    # Una tarea con fecha (sin evento) es una PROPUESTA: aceptarla crea el evento en la rota y
    # borra la tarea (se «mueve» al calendario, no queda duplicada en el tablero).
    c = _cli("ana")
    tarea = _crear_tarea_propuesta(c)
    r = c.post(f"/api/publicaciones/{tarea['id']}/aceptar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["aceptada"] is True
    ev = cuerpo["evento"]
    assert ev["titulo"] == "La Velada del Año VI"
    assert ev["fecha"] == "2026-07-26"
    assert ev["marca"] == "claro-sports"
    # El evento ya vive en la rota (calendario)...
    assert any(e["id"] == ev["id"] for e in repos.listar_eventos_rota())
    # ...y la tarea-propuesta se consumió (ya no está en el tablero).
    ids = {x["id"] for x in c.get("/api/publicaciones?clase=tarea").json()["contenidos"]}
    assert tarea["id"] not in ids


def test_aceptar_tarea_sin_fecha_da_409(entorno):
    # Sin fecha no es propuesta de calendario (un evento necesita fecha): 409, sin crear evento.
    c = _cli("ana")
    r = c.post(
        "/api/publicaciones", json={"clase": "tarea", "titulo": "Editar el clip"}, headers=_ORIGIN
    )
    tarea = r.json()["contenido"]
    antes = len(repos.listar_eventos_rota())
    r2 = c.post(f"/api/publicaciones/{tarea['id']}/aceptar", headers=_ORIGIN)
    assert r2.status_code == 409, r2.text
    assert len(repos.listar_eventos_rota()) == antes  # no se creó ningún evento


def test_aceptar_evento_existente_no_es_propuesta_da_409(entorno):
    # Una tarea de COBERTURA (con evento_id) NO es una propuesta: ya pertenece a un evento.
    c = _cli("ana")
    ev = _crear_evento()
    cob = c.post(
        "/api/publicaciones/cubrir-evento", json={"evento_id": ev["id"]}, headers=_ORIGIN
    ).json()["contenido"]
    r = c.post(f"/api/publicaciones/{cob['id']}/aceptar", headers=_ORIGIN)
    assert r.status_code == 409, r.text


def test_aceptar_inexistente_404(entorno):
    c = _cli("ana")
    r = c.post("/api/publicaciones/fantasma/aceptar", headers=_ORIGIN)
    assert r.status_code == 404
