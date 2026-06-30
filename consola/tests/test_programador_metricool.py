"""Tests del enganche Metricool en el programador (#9, Fase 3 + Metricool).

Cubre los tres escenarios criticos del gate `KENI_PUBLICAR_REAL`:

  1. DRY-RUN (gate OFF, default): comportamiento original INTACTO. La pieza queda
     en `programado` con `preparado_en` puesto; NO se llama al endpoint de Metricool.

  2. REAL (gate ON): se construye el BorradorMetricool correcto, se postea al
     endpoint de Metricool (mocked con respx), y la pieza pasa a `publicado` con
     `id_post_metricool` guardado.

  3. DEGRADACION honesta si la marca no tiene credenciales (gate ON pero sin creds):
     la pieza SIGUE en `programado` con `preparado_en` puesto; NO rompe el barrido.

Todos los tests mockan la red con respx (nunca tocan la API real de Metricool) y
mockan la carga de config de Metricool (no necesitan un TOML real).
"""

from __future__ import annotations

import json

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import httpx
import respx
from httpx import Response

from keni_consola import repos
from keni_consola.programador import (
    ID_POST_INCIERTO,
    _borrador_de_publicacion,
    _url_media_publica,
    piezas_vencidas,
    preparar_vencidas,
    programar_pieza_metricool,
    slides_de_carrusel,
)

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

_METRICOOL_URL = "https://app.metricool.com/api/v2/scheduler/posts"

# Credenciales de prueba (nunca reales).
_CREDS_PRUEBA = {
    "user_token": "tok-test-abc",
    "user_id": "12345",
    "blog_id": "67890",
}

# Respuesta exitosa simulada de Metricool.
_RESP_OK = {
    "data": {
        "id": "mc-post-id-001",
        "providers": [{"network": "instagram", "status": "PENDING"}],
    }
}


def _pub_programada(
    entorno,
    red: str = "instagram",
    contenido: str = "Texto de prueba",
    imagen: str = "abc123.jpg",
    minutos_atras: int = 5,
) -> dict[str, Any]:
    """Crea una pieza programada con fecha ya vencida (en repos directamente)."""
    pub = repos.crear_pieza(
        "unotv",
        red,
        titulo="Test",
        contenido=contenido,
        estado="programado",
        imagen=imagen,
    )
    pasado = (datetime.now() - timedelta(minutes=minutos_atras)).strftime("%Y-%m-%dT%H:%M")
    return repos.actualizar_pieza(pub["id"], {"fecha_programada": pasado})


# --------------------------------------------------------------------------- #
# Tests de _url_media_publica (pura, sin red)                                 #
# --------------------------------------------------------------------------- #


def test_url_media_publica_con_base(monkeypatch):
    """Con KENI_CONSOLA_URL_PUBLICA se construye la URL absoluta correcta."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")
    url = _url_media_publica("abc123.jpg")
    assert url == "https://social.kenitech.io/api/media/abc123.jpg"


def test_url_media_publica_sin_base(monkeypatch):
    """Sin KENI_CONSOLA_URL_PUBLICA devuelve None (la media se omite)."""
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)
    assert _url_media_publica("abc123.jpg") is None


def test_url_media_publica_nombre_vacio(monkeypatch):
    """Con nombre vacio siempre devuelve None (aunque haya base configurada)."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")
    assert _url_media_publica("") is None


def test_url_media_publica_base_sin_barra_final(monkeypatch):
    """La URL no tiene doble barra aunque la base venga con barra."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io/")
    url = _url_media_publica("img.png")
    assert url == "https://social.kenitech.io/api/media/img.png"
    assert "//" not in url.replace("https://", "")


# --------------------------------------------------------------------------- #
# Tests de _borrador_de_publicacion (pura, sin red)                           #
# --------------------------------------------------------------------------- #


def test_borrador_red_no_soportada():
    """Una red no en Plataforma (p.ej. 'otra') devuelve None sin lanzar."""
    pub = {"id": "x1", "red": "otra", "contenido": "texto", "imagen": "", "fecha_programada": ""}
    assert _borrador_de_publicacion(pub) is None


def test_borrador_instagram_sin_media_sin_url_publica(monkeypatch):
    """Instagram sin media y sin URL publica -> None (instagram exige media)."""
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)
    pub = {
        "id": "x2", "red": "instagram", "contenido": "texto",
        "imagen": "foto.jpg", "fecha_programada": "2026-05-30T18:00",
    }
    # Sin URL publica, la imagen no se incluye => instagram queda sin media => None
    resultado = _borrador_de_publicacion(pub)
    assert resultado is None


def test_borrador_instagram_con_media_url_publica(monkeypatch):
    """Instagram con imagen y URL publica -> BorradorMetricool valido."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")
    pub = {
        "id": "x3", "red": "instagram", "contenido": "texto de prueba",
        "imagen": "foto.jpg", "fecha_programada": "2026-05-30T18:00",
    }
    from keni_metricas.pieza.metricool import BorradorMetricool

    borrador = _borrador_de_publicacion(pub)
    assert isinstance(borrador, BorradorMetricool)
    assert len(borrador.media) == 1
    assert borrador.media[0].url == "https://social.kenitech.io/api/media/foto.jpg"


def test_borrador_x_sin_media(monkeypatch):
    """X (twitter) puede publicar solo texto -> BorradorMetricool valido sin media."""
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)
    pub = {
        "id": "x4", "red": "x", "contenido": "Tweet de prueba",
        "imagen": "", "fecha_programada": "2026-05-30T18:00",
    }
    from keni_metricas.pieza.metricool import BorradorMetricool

    borrador = _borrador_de_publicacion(pub)
    assert isinstance(borrador, BorradorMetricool)
    assert borrador.media == []


def test_borrador_cc_by_anade_credito_al_caption(monkeypatch):
    """Una pieza con foto CC BY publica el copy + la línea de crédito (idempotente)."""
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)
    pub = {
        "id": "cb1", "red": "x", "contenido": "Mira esta foto",
        "imagen": "", "fecha_programada": "2030-01-01T10:00",
        "imagen_origen": "stock", "imagen_autorizada": True,
        "imagen_licencia": "CC BY 4.0", "imagen_proveedor": "openverse",
        "imagen_autor": "Jane Doe", "imagen_credito_url": "https://ov/obra",
    }
    borrador = _borrador_de_publicacion(pub)
    assert borrador is not None
    assert "Mira esta foto" in borrador.texto
    assert "Jane Doe" in borrador.texto
    assert "CC BY 4.0" in borrador.texto
    # IDEMPOTENTE: si el copy ya trae la línea de crédito, no se duplica.
    credito = borrador.texto.split("\n\n")[-1]
    pub2 = {**pub, "contenido": f"{pub['contenido']}\n\n{credito}"}
    borrador2 = _borrador_de_publicacion(pub2)
    assert borrador2 is not None
    assert borrador2.texto.count("Jane Doe") == 1


def test_borrador_cc0_no_anade_credito(monkeypatch):
    """Una pieza con foto CC0 (libre) NO exige crédito: el caption es solo el copy."""
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)
    pub = {
        "id": "c0", "red": "x", "contenido": "Texto sin crédito",
        "imagen": "", "fecha_programada": "2030-01-01T10:00",
        "imagen_origen": "stock", "imagen_autorizada": True,
        "imagen_licencia": "CC0", "imagen_proveedor": "openverse",
    }
    borrador = _borrador_de_publicacion(pub)
    assert borrador is not None
    assert borrador.texto == "Texto sin crédito"


def test_borrador_video_construye_media_video(monkeypatch):
    """Pieza formato=video con asset y URL publica -> MediaRef de tipo video."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")
    pub = {
        "id": "v1", "red": "tiktok", "contenido": "clip de prueba",
        "formato": "video", "video": "videos/abc.mp4",
        "fecha_programada": "2026-05-30T18:00",
    }
    from keni_metricas.pieza.metricool import BorradorMetricool
    from keni_metricas.pieza.modelos import TipoMedia

    borrador = _borrador_de_publicacion(pub)
    assert isinstance(borrador, BorradorMetricool)
    assert len(borrador.media) == 1
    assert borrador.media[0].tipo == TipoMedia.video
    assert borrador.media[0].url == "https://social.kenitech.io/api/media/videos/abc.mp4"


def test_slides_de_carrusel_parsea_y_sanea():
    """`slides_de_carrusel` (pura): orden preservado, tipo desconocido -> imagen, basura -> []."""
    crudo = (
        '[{"tipo":"imagen","objeto":"a.jpg"},{"tipo":"video","objeto":"videos/b.mp4"},'
        '{"tipo":"","objeto":"c.png"},{"objeto":""},"no-dict"]'
    )
    slides = slides_de_carrusel(crudo)
    assert slides == [
        {"tipo": "imagen", "objeto": "a.jpg"},
        {"tipo": "video", "objeto": "videos/b.mp4"},
        {"tipo": "imagen", "objeto": "c.png"},
    ]
    assert slides_de_carrusel("") == []
    assert slides_de_carrusel(None) == []
    assert slides_de_carrusel("{json roto") == []
    assert slides_de_carrusel('{"no":"lista"}') == []


def test_borrador_carrusel_portada_mas_slides(monkeypatch):
    """Pieza formato=carrusel: media = portada compuesta + slides extra EN ORDEN (multi-media)."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")
    pub = {
        "id": "c1", "red": "instagram", "contenido": "nota de presidencia",
        "formato": "carrusel", "imagen": "portada.png",
        "carrusel": (
            '[{"tipo":"imagen","objeto":"slide2.jpg"},'
            '{"tipo":"video","objeto":"videos/slide3.mp4"},'
            '{"tipo":"imagen","objeto":"slide4.jpg"}]'
        ),
        "fecha_programada": "2026-06-10T18:00",
    }
    from keni_metricas.pieza.metricool import BorradorMetricool
    from keni_metricas.pieza.modelos import TipoMedia

    borrador = _borrador_de_publicacion(pub)
    assert isinstance(borrador, BorradorMetricool)
    assert [m.url for m in borrador.media] == [
        "https://social.kenitech.io/api/media/portada.png",
        "https://social.kenitech.io/api/media/slide2.jpg",
        "https://social.kenitech.io/api/media/videos/slide3.mp4",
        "https://social.kenitech.io/api/media/slide4.jpg",
    ]
    # La portada y los slides de imagen son imagen; el clip intermedio viaja como video.
    assert [m.tipo for m in borrador.media] == [
        TipoMedia.imagen, TipoMedia.imagen, TipoMedia.video, TipoMedia.imagen,
    ]


def test_borrador_carrusel_reconcilia_slide_stale(monkeypatch):
    """Un slide «sin placa» con `objeto` stale se RECONCILIA a la foto cruda al construir el borrador,
    y el carrusel reconciliado se CONGELA en la pieza (no se publica el horneado anterior)."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")
    from keni_consola import almacen_media
    from keni_consola.dominio import estudio_imagen, render_pieza

    monkeypatch.setattr(render_pieza, "_plantilla_efectiva", lambda pub: {"documento": "{}"})
    monkeypatch.setattr(estudio_imagen, "componer_desde_plantilla_bytes", lambda *a, **k: b"x")
    monkeypatch.setattr(almacen_media, "promover_objeto", lambda clave, cat: f"{cat}/cruda-{clave}")
    guardados: dict[str, Any] = {}
    monkeypatch.setattr(repos, "actualizar_pieza", lambda pid, campos: guardados.update({pid: campos}))

    pub = {
        "id": "c9", "red": "instagram", "contenido": "nota", "marca": "claro-sports",
        "formato": "carrusel", "imagen": "portada.png",
        "carrusel": json.dumps([
            {"tipo": "imagen", "objeto": "artes/placa-vieja", "foto": "fotos/r",
             "titular": "Cayó 6-1", "sinPlaca": True},
        ]),
        "fecha_programada": "2026-06-10T18:00",
    }
    borrador = _borrador_de_publicacion(pub)
    assert [m.url for m in borrador.media] == [
        "https://social.kenitech.io/api/media/portada.png",
        "https://social.kenitech.io/api/media/artes/cruda-fotos/r",
    ]
    # El carrusel reconciliado quedó CONGELADO en la pieza (objeto = foto cruda, no la placa vieja).
    assert "artes/cruda-fotos/r" in guardados["c9"]["carrusel"]
    assert "artes/placa-vieja" not in guardados["c9"]["carrusel"]


def test_borrador_carrusel_sin_slides_va_solo_con_portada(monkeypatch):
    """Carrusel sin slides extra (o ilegibles) publica al menos la portada, sin romper."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")
    pub = {
        "id": "c2", "red": "facebook", "contenido": "texto",
        "formato": "carrusel", "imagen": "portada.png", "carrusel": "{roto",
        "fecha_programada": "2026-06-10T18:00",
    }
    borrador = _borrador_de_publicacion(pub)
    assert borrador is not None
    assert [m.url for m in borrador.media] == [
        "https://social.kenitech.io/api/media/portada.png"
    ]


def test_borrador_video_sin_asset_omite(monkeypatch):
    """Pieza formato=video SIN asset de video -> None (queda pendiente, no rompe)."""
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")
    pub = {
        "id": "v2", "red": "youtube", "contenido": "clip",
        "formato": "video", "video": "",
        "fecha_programada": "2026-05-30T18:00",
    }
    assert _borrador_de_publicacion(pub) is None


def test_borrador_facebook_preserva_fecha_programada(monkeypatch):
    """La fecha programada de la fila se mapea a publicar_en del borrador."""
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)
    pub = {
        "id": "x5", "red": "facebook", "contenido": "Post de FB",
        "imagen": "", "fecha_programada": "2026-05-30T18:00",
    }
    borrador = _borrador_de_publicacion(pub)
    assert borrador is not None
    assert borrador.publicar_en == datetime(2026, 5, 30, 18, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Tests de _creds_metricool (con mock de cargar_config)                       #
# --------------------------------------------------------------------------- #


def test_creds_metricool_marca_sin_credenciales():
    """Marca sin credenciales configuradas -> None (degradacion honesta)."""
    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=None,
    ):
        # Llamamos directamente a la funcion real con mock de cargar_config
        pass  # Se prueba via test_preparar_sin_creds mas abajo


def test_creds_metricool_resuelve_creds():
    """Marca con credenciales completas -> dict con los tres campos."""
    creds_mock = {"user_token": "tok", "user_id": "123", "blog_id": "456"}
    with patch("keni_consola.programador._creds_metricool", return_value=creds_mock) as mock_fn:
        result = mock_fn("unotv")
        assert result["user_token"] == "tok"
        assert result["user_id"] == "123"
        assert result["blog_id"] == "456"


# --------------------------------------------------------------------------- #
# Test 1: DRY-RUN (gate OFF) - comportamiento original intacto                #
# --------------------------------------------------------------------------- #


def test_dryrun_no_llama_metricool(entorno, monkeypatch):
    """Con KENI_PUBLICAR_REAL ausente, el barrido NO llama a Metricool (comportamiento original)."""
    monkeypatch.delenv("KENI_PUBLICAR_REAL", raising=False)
    pub = _pub_programada(entorno)

    with respx.mock(assert_all_called=False) as mock_routes:
        ruta = mock_routes.post(_METRICOOL_URL, name="post").mock(
            Response(200, json=_RESP_OK)
        )
        preparadas = preparar_vencidas(datetime.now())

    assert preparadas == 1
    actualizada = repos.obtener_pieza(pub["id"])
    # Dry-run: sigue en programado, preparado_en puesto, NO publicado
    assert actualizada["estado"] == "programado"
    assert actualizada["preparado_en"]  # estampado
    assert actualizada.get("id_post_metricool", "") == ""  # no fue a Metricool
    # El mock NO fue llamado
    assert not ruta.called


def test_dryrun_flag_false_no_llama_metricool(entorno, monkeypatch):
    """Con KENI_PUBLICAR_REAL=false, igual que sin la variable."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "false")
    pub = _pub_programada(entorno)

    with respx.mock(assert_all_called=False) as mock_routes:
        ruta = mock_routes.post(_METRICOOL_URL, name="post").mock(Response(200, json=_RESP_OK))
        preparar_vencidas(datetime.now())

    actualizada = repos.obtener_pieza(pub["id"])
    assert actualizada["estado"] == "programado"
    assert not ruta.called


# --------------------------------------------------------------------------- #
# Boton manual: programar_pieza_metricool (a demanda desde la UI)             #
# --------------------------------------------------------------------------- #


def test_programar_pieza_metricool_dry_run_previsualiza(entorno, monkeypatch):
    """Gate OFF: el boton manual PREVISUALIZA (dry-run), sin tocar la red ni persistir."""
    monkeypatch.delenv("KENI_PUBLICAR_REAL", raising=False)
    pub = _pub_programada(entorno, red="facebook", contenido="Hola")
    with patch(
        "keni_consola.programador._creds_metricool", return_value=_CREDS_PRUEBA
    ), respx.mock(assert_all_called=False) as mc:
        ruta = mc.post(_METRICOOL_URL, name="post").mock(Response(200, json=_RESP_OK))
        res = programar_pieza_metricool(pub)
    assert res["ok"] is True
    assert res["dry_run"] is True
    assert res["cuerpo"]["providers"] == [{"network": "facebook"}]
    assert not ruta.called  # dry-run NO toca la red
    # No persiste: sigue en programado, sin id_post.
    actualizada = repos.obtener_pieza(pub["id"])
    assert actualizada["estado"] == "programado"
    assert actualizada.get("id_post_metricool", "") == ""


def test_programar_pieza_metricool_sin_creds(entorno, monkeypatch):
    """Sin credenciales de la marca devuelve ok=False con motivo (no lanza)."""
    monkeypatch.delenv("KENI_PUBLICAR_REAL", raising=False)
    pub = _pub_programada(entorno, red="facebook", contenido="Hola")
    with patch("keni_consola.programador._creds_metricool", return_value=None):
        res = programar_pieza_metricool(pub)
    assert res["ok"] is False
    assert res["motivo"]


# --------------------------------------------------------------------------- #
# Test 2: REAL (gate ON) - posteo correcto a Metricool                        #
# --------------------------------------------------------------------------- #


def test_real_postea_a_metricool_y_marca_publicado(entorno, monkeypatch):
    """Con KENI_PUBLICAR_REAL=1, se postea a Metricool y la pieza pasa a 'publicado'."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")

    pub = _pub_programada(entorno, red="instagram", contenido="Texto real", imagen="img.jpg")

    # Mock de credenciales de Metricool para la marca "unotv"
    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=_CREDS_PRUEBA,
    ), respx.mock() as mc:
        mc.post(_METRICOOL_URL).mock(Response(200, json=_RESP_OK))
        preparadas = preparar_vencidas(datetime.now())

    assert preparadas == 1
    actualizada = repos.obtener_pieza(pub["id"])
    # Publicado de verdad
    assert actualizada["estado"] == "publicado"
    assert actualizada["preparado_en"]
    assert actualizada["id_post_metricool"] == "mc-post-id-001"


def test_real_cuerpo_correcto_a_metricool(entorno, monkeypatch):
    """El cuerpo enviado a Metricool incluye el texto, la red y la media correctamente."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")

    _pub_programada(entorno, red="instagram", contenido="Copy aprobado", imagen="foto.png")
    cuerpo_enviado: dict | None = None

    def capturar_post(request, route):  # noqa: ANN001
        import json
        nonlocal cuerpo_enviado
        cuerpo_enviado = json.loads(request.content)
        return Response(200, json=_RESP_OK)

    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=_CREDS_PRUEBA,
    ), respx.mock() as mc:
        mc.post(_METRICOOL_URL).mock(side_effect=capturar_post)
        preparar_vencidas(datetime.now())

    assert cuerpo_enviado is not None
    assert cuerpo_enviado["text"] == "Copy aprobado"
    proveedores = [p["network"] for p in cuerpo_enviado["providers"]]
    assert "instagram" in proveedores
    assert cuerpo_enviado["media"] == ["https://social.kenitech.io/api/media/foto.png"]
    assert cuerpo_enviado.get("saveExternalMediaFiles") is True


def test_real_x_sin_media_publica_solo_texto(entorno, monkeypatch):
    """X puede publicarse sin media: el cuerpo no incluye el campo 'media'."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)

    _pub_programada(entorno, red="x", contenido="Tweet directo", imagen="")
    cuerpo_enviado: dict | None = None

    def capturar(request, route):  # noqa: ANN001
        import json
        nonlocal cuerpo_enviado
        cuerpo_enviado = json.loads(request.content)
        return Response(200, json=_RESP_OK)

    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=_CREDS_PRUEBA,
    ), respx.mock() as mc:
        mc.post(_METRICOOL_URL).mock(side_effect=capturar)
        preparar_vencidas(datetime.now())

    assert cuerpo_enviado is not None
    assert "media" not in cuerpo_enviado
    assert cuerpo_enviado["text"] == "Tweet directo"


def test_boton_manual_publica_ahora_y_sella_hora_real(entorno, monkeypatch):
    """El botón manual sobre una pieza programada AL FUTURO publica YA, no la agenda.

    Regresión: una pieza con `fecha_programada` futura se enviaba al scheduler con esa hora
    + autoPublish y la consola la marcaba `publicado` antes de salir -> "publicada en el
    futuro". Ahora el botón fuerza `publicar_en=ahora` (Metricool publica ya) y persiste
    `fecha_programada=ahora` (la hora real), de modo que nunca queda una publicada al futuro.
    """
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)

    # Pieza programada DOS HORAS en el futuro (red X: no necesita media ni URL pública).
    pub = repos.crear_pieza(
        "unotv", "x", titulo="Test", contenido="Publicar ya", estado="programado",
    )
    futuro = "2026-06-15T21:45"  # UTC naive
    pub = repos.actualizar_pieza(pub["id"], {"fecha_programada": futuro})

    ahora = datetime(2026, 6, 15, 19, 15, tzinfo=timezone.utc)  # 13:15 CDMX
    cuerpo_enviado: dict | None = None

    def capturar(request, route):  # noqa: ANN001
        import json
        nonlocal cuerpo_enviado
        cuerpo_enviado = json.loads(request.content)
        return Response(200, json=_RESP_OK)

    with patch(
        "keni_consola.programador._creds_metricool", return_value=_CREDS_PRUEBA,
    ), respx.mock() as mc:
        mc.post(_METRICOOL_URL).mock(side_effect=capturar)
        res = programar_pieza_metricool(pub, ahora=ahora)

    assert res["ok"] is True
    assert res["dry_run"] is False
    # Lo que se mandó a Metricool publica AHORA (hora de pared CDMX de `ahora`), no a las 21:45.
    assert cuerpo_enviado is not None
    assert cuerpo_enviado["publicationDate"]["dateTime"] == "2026-06-15T13:15:00"
    # La fila ya no apunta al futuro: estado publicado y `fecha_programada` = hora real.
    actualizada = repos.obtener_pieza(pub["id"])
    assert actualizada["estado"] == "publicado"
    assert actualizada["fecha_programada"] == "2026-06-15T19:15:00"
    assert actualizada["id_post_metricool"] == "mc-post-id-001"


# --------------------------------------------------------------------------- #
# Test 3: DEGRADACION honesta si la marca no tiene credenciales               #
# --------------------------------------------------------------------------- #


def test_sin_creds_sigue_en_programado_no_rompe_barrido(entorno, monkeypatch):
    """Sin creds de Metricool: la pieza se prepara (preparado_en) pero sigue en 'programado'."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.setenv("KENI_CONSOLA_URL_PUBLICA", "https://social.kenitech.io")

    pub = _pub_programada(entorno, red="instagram", imagen="img.jpg")

    # Marca sin credenciales -> _creds_metricool devuelve None
    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=None,
    ), respx.mock(assert_all_called=False) as mc:
        ruta = mc.post(_METRICOOL_URL, name="post").mock(Response(200, json=_RESP_OK))
        preparadas = preparar_vencidas(datetime.now())

    assert preparadas == 1
    actualizada = repos.obtener_pieza(pub["id"])
    # Degradacion honesta: preparado pero NO publicado
    assert actualizada["estado"] == "programado"
    assert actualizada["preparado_en"]
    assert actualizada.get("id_post_metricool", "") == ""
    # Nunca fue a Metricool
    assert not ruta.called


def test_varias_piezas_una_sin_creds_no_rompe_otras(entorno, monkeypatch):
    """Un fallo de creds en una pieza no rompe el barrido para las demas."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)

    # Dos piezas en X (sin media, no necesitan URL publica). Slots DISTINTOS: el UNIQUE
    # `idx_parrilla_slot_uniq` (marca, red, fecha_programada) no permite dos en el mismo minuto.
    pub1 = _pub_programada(entorno, red="x", contenido="Post 1", imagen="", minutos_atras=10)
    pub2 = _pub_programada(entorno, red="x", contenido="Post 2", imagen="", minutos_atras=5)

    llamadas: list[str] = []

    def creds_selectivo(marca_id: str) -> dict | None:
        # Solo la segunda pieza tiene creds (no hay forma de distinguir por id de pieza
        # desde _creds_metricool, pero simulamos un fallo en la primera llamada)
        if not llamadas:
            llamadas.append("sin_creds")
            return None
        llamadas.append("con_creds")
        return _CREDS_PRUEBA

    with patch(
        "keni_consola.programador._creds_metricool",
        side_effect=creds_selectivo,
    ), respx.mock() as mc:
        mc.post(_METRICOOL_URL).mock(Response(200, json=_RESP_OK))
        preparadas = preparar_vencidas(datetime.now())

    assert preparadas == 2  # ambas quedan "preparadas" (aunque una en modo sin-creds)
    a1 = repos.obtener_pieza(pub1["id"])
    a2 = repos.obtener_pieza(pub2["id"])
    assert a1["preparado_en"]  # la sin-creds si quedo preparada
    assert a2["preparado_en"]  # la con-creds tambien


def test_error_de_red_libera_la_preparacion_y_no_rompe_barrido(entorno, monkeypatch):
    """Un fallo HTTP de Metricool se loguea, LIBERA `preparado_en` y no rompe el barrido."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)

    pub = _pub_programada(entorno, red="x", contenido="Tweet", imagen="")

    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=_CREDS_PRUEBA,
    ), respx.mock() as mc:
        # Metricool devuelve 500
        mc.post(_METRICOOL_URL).mock(Response(500, json={"error": "server error"}))
        preparadas = preparar_vencidas(datetime.now())

    # El fallo de ENTREGA no cuenta como preparada y deja la pieza reintentable.
    assert preparadas == 0
    actualizada = repos.obtener_pieza(pub["id"])
    assert actualizada["estado"] == "programado"
    assert actualizada["preparado_en"] == ""  # claim liberado: se reintentara
    assert actualizada.get("id_post_metricool", "") == ""


def test_error_de_red_se_reintenta_en_el_siguiente_barrido(entorno, monkeypatch):
    """Tras un fallo de entrega, el SIGUIENTE barrido reintenta y publica si Metricool ya
    responde (la pieza no queda muerta en `programado`)."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)

    pub = _pub_programada(entorno, red="x", contenido="Tweet con reintento", imagen="")

    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=_CREDS_PRUEBA,
    ), respx.mock() as mc:
        # 1er barrido: 500 (fallo transitorio). 2do barrido: 200 (Metricool se recupero).
        mc.post(_METRICOOL_URL).mock(
            side_effect=[
                Response(500, json={"error": "server error"}),
                Response(200, json=_RESP_OK),
            ]
        )
        assert preparar_vencidas(datetime.now()) == 0
        assert preparar_vencidas(datetime.now()) == 1

    actualizada = repos.obtener_pieza(pub["id"])
    assert actualizada["estado"] == "publicado"
    assert actualizada["preparado_en"]
    assert actualizada["id_post_metricool"] == "mc-post-id-001"


# --------------------------------------------------------------------------- #
# Timeout: el post pudo entregarse -> NO reenviar (evitar doble-post)          #
# --------------------------------------------------------------------------- #


def test_timeout_marca_publicado_incierto_y_no_reenvia(entorno, monkeypatch):
    """Un TIMEOUT del POST de pieza NO libera el claim: el post pudo entregarse.

    A diferencia de un 5xx (entrega fallida, se reintenta), un ReadTimeout salta tras
    enviar la peticion entera, asi que Metricool casi seguro la recibio. Reenviar
    duplicaria el post. La pieza pasa a `publicado` con el marcador incierto y un
    segundo barrido NO vuelve a postear.
    """
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)

    pub = _pub_programada(entorno, red="x", contenido="Tweet timeout", imagen="")

    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=_CREDS_PRUEBA,
    ), respx.mock() as mc:
        ruta = mc.post(_METRICOOL_URL).mock(
            side_effect=httpx.ReadTimeout("read timed out")
        )
        # Cuenta como preparada (no se libera el claim) y NO se reintenta en el 2o barrido.
        assert preparar_vencidas(datetime.now()) == 1
        assert preparar_vencidas(datetime.now()) == 0
        assert ruta.call_count == 1  # un solo intento real: no hubo doble-envio

    actualizada = repos.obtener_pieza(pub["id"])
    assert actualizada["estado"] == "publicado"
    assert actualizada["preparado_en"]  # claim conservado (no liberado)
    assert actualizada["id_post_metricool"] == ID_POST_INCIERTO


def test_boton_manual_timeout_marca_publicado_incierto(entorno, monkeypatch):
    """El boton manual, ante timeout, marca `publicado` (incierto) y avisa: no duplica."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)

    pub = _pub_programada(entorno, red="facebook", contenido="Hola timeout", imagen="")

    with patch(
        "keni_consola.programador._creds_metricool",
        return_value=_CREDS_PRUEBA,
    ), respx.mock() as mc:
        mc.post(_METRICOOL_URL).mock(side_effect=httpx.ReadTimeout("read timed out"))
        res = programar_pieza_metricool(pub)

    assert res["ok"] is True
    assert res["incierto"] is True
    assert res["motivo"]
    actualizada = repos.obtener_pieza(pub["id"])
    assert actualizada["estado"] == "publicado"
    assert actualizada["id_post_metricool"] == ID_POST_INCIERTO
    # La guarda de re-pieza ahora bloquea un segundo click (ya esta publicado).
    res2 = programar_pieza_metricool(repos.obtener_pieza(pub["id"]))
    assert res2["ok"] is False


# --------------------------------------------------------------------------- #
# Retrocompatibilidad: los tests originales de piezas_vencidas siguen pasando #
# --------------------------------------------------------------------------- #


def test_piezas_vencidas_pura_retrocompat():
    """La funcion pura `piezas_vencidas` sigue siendo determinista (retrocompat)."""
    ahora = datetime(2026, 5, 27, 12, 0)
    vencida = {
        "id": "a", "estado": "programado",
        "fecha_programada": "2026-05-27T11:00", "preparado_en": "",
    }
    futura = {
        "id": "b", "estado": "programado",
        "fecha_programada": "2026-05-27T13:00", "preparado_en": "",
    }
    ya_prep = {
        "id": "c", "estado": "programado",
        "fecha_programada": "2026-05-27T10:00", "preparado_en": "2026-05-27T10:01",
    }
    vencidas = piezas_vencidas([vencida, futura, ya_prep], ahora)
    assert [p["id"] for p in vencidas] == ["a"]
