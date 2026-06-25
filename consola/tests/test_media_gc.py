"""Tests OFFLINE de la GC de media suelta (`dominio.media_gc` + daemon).

Mockean `almacen_media.listar_objetos`/`borrar_objeto` y los repos de referencias
(`listar_piezas`, `listar_media_catalogo`),
asi NO necesitan Postgres ni almacen real. Verifican la definicion CONSERVADORA de suelto:
no borra referenciados, ni catalogados, ni recientes (umbral); SI borra el suelto viejo; y
`dry_run` no toca nada. Mas un test de que el daemon respeta el gate (`KENI_MEDIA_GC` off).
"""

from __future__ import annotations

import time

import pytest

from keni_consola import ajustes, config, daemon_util, media_gc_daemon
from keni_consola.dominio import media_gc


@pytest.fixture(autouse=True)
def _store_aislado(monkeypatch, tmp_path):
    """Aisla el store de ajustes en tmp para que `config.media_gc_activo` lea solo la env."""
    monkeypatch.setenv("KENI_CONSOLA_AJUSTES", str(tmp_path / "ajustes.toml"))
    ajustes._CACHE_RUTA = None
    ajustes._CACHE_MTIME = -1.0
    ajustes._CACHE_DATOS = {}


@pytest.fixture(autouse=True)
def _recursos_marca_vacios(monkeypatch):
    """Por defecto, sin plantillas del estudio ni activos de marca (referencias de render).

    `referencias_vivas` consulta estas fuentes para proteger los ORIGINALES del render
    on-demand; sin mock irían a la BD. Las pruebas que verifican esa protección los
    sobrescriben. Así el resto sigue siendo determinista (no aportan referencias)."""
    monkeypatch.setattr(media_gc.repos, "listar_plantillas_diseno", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_marca_activos", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "media_ids_audio_transcripciones", lambda: [])

# Antiguedades sinteticas (epoch): "viejo" = hace 48h, "nuevo" = hace 1h.
_AHORA = time.time()
_VIEJO = _AHORA - 48 * 3600.0
_NUEVO = _AHORA - 1 * 3600.0


@pytest.fixture
def repos_vacios(monkeypatch):
    """Por defecto: sin piezas ni catálogo de media (todo suelto)."""
    monkeypatch.setattr(media_gc.repos, "listar_piezas", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])


def _objetos(monkeypatch, objetos):
    """Mockea `almacen_media.listar_objetos` con la lista dada de `(nombre, mtime)`."""
    monkeypatch.setattr(media_gc.almacen_media, "listar_objetos", lambda: list(objetos))


def _captura_borrados(monkeypatch):
    """Sustituye `borrar_objeto` por un capturador; devuelve la lista de nombres borrados."""
    borrados: list[str] = []
    monkeypatch.setattr(
        media_gc.almacen_media, "borrar_objeto", lambda nombre: borrados.append(nombre)
    )
    return borrados


# --------------------------------------------------------------------------- #
# referencias_vivas                                                            #
# --------------------------------------------------------------------------- #


def test_referencias_unen_publicaciones(monkeypatch):
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [{"imagen": "pub.png"}, {"imagen": ""}, {"imagen": "  "}],
    )
    # Sin catalogo-media: solo cuentan las piezas.
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    assert media_gc.referencias_vivas() == {"pub.png"}


def test_protege_media_de_audio(monkeypatch):
    """El audio original de una transcripción NO es suelto: se conserva aunque sea viejo."""
    monkeypatch.setattr(media_gc.repos, "listar_piezas", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.setattr(
        media_gc.repos, "media_ids_audio_transcripciones", lambda: ["audios/abc.mp3"]
    )
    assert "audios/abc.mp3" in media_gc.referencias_vivas()

    # `audios/` no es categoría borrable por el GC: aunque el audio quedara sin fila, no se
    # recolecta. El huérfano que SÍ se borra es una caché regenerable (`render/`).
    _objetos(monkeypatch, [("audios/abc.mp3", _VIEJO), ("render/huerfano.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)
    media_gc.limpiar(antiguedad_horas=24)
    # Borra el huérfano viejo regenerable, conserva el del audio referenciado.
    assert borrados == ["render/huerfano.png"]


def test_catalogo_media_es_red_de_seguridad_opcional_si_existe(monkeypatch):
    # Si el repo de catalogo-media existe, sus objetos se suman (red de seguridad).
    monkeypatch.setattr(media_gc.repos, "listar_piezas", lambda *a, **k: [])
    monkeypatch.setattr(
        media_gc.repos, "listar_media_catalogo",
        lambda *a, **k: [{"objeto": "cat.png"}, {"objeto": ""}],
    )
    assert media_gc.referencias_vivas() == {"cat.png"}


def test_gc_no_falla_si_catalogo_media_no_existe(monkeypatch):
    # Cuando se elimine `api/catalogo_media.py`, el repo perdera la funcion: el GC NO debe
    # fallar; simplemente no consulta esa fuente (se basa solo en piezas).
    monkeypatch.setattr(media_gc.repos, "listar_piezas", lambda *a, **k: [])
    monkeypatch.delattr(media_gc.repos, "listar_media_catalogo", raising=False)
    assert media_gc.referencias_vivas() == set()
    # Y un suelto viejo regenerable se borra igual (sin la red de seguridad de catalogo-media).
    _objetos(monkeypatch, [("render/suelto.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["render/suelto.png"] and res["borrados"] == 1


def test_protege_foto_cruda_de_publicacion(monkeypatch):
    # Con render on-demand la foto cruda NO está horneada en `imagen`: debe ser referencia viva.
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [{"imagen": "", "foto": "foto-cruda.jpg"}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    assert "foto-cruda.jpg" in media_gc.referencias_vivas()
    # Y un GC viejo NO la borra aunque `imagen` esté vacío.
    _objetos(monkeypatch, [("foto-cruda.jpg", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == [] and res["conservados"] == 1


def test_protege_recursos_de_marca_y_plantillas(monkeypatch):
    # Logos/tipografías (activos de marca) y media_id de plantillas del estudio son originales
    # del render: no se borran.
    monkeypatch.setattr(media_gc.repos, "listar_piezas", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.setattr(
        media_gc.repos, "listar_marca_activos",
        lambda *a, **k: [{"objeto": "logo-oficial.png"}, {"objeto": ""}],
    )
    doc = (
        '{"fondo":{"tipo":"imagen","imagen":{"media_id":"fondo.jpg"}},'
        '"capas":[{"tipo":"logo","tipo_logo":"imagen","media_id":"logo-spec.png"},'
        '{"tipo":"grupo","capas":[{"tipo":"imagen","objeto":"muestra.jpg"}]}]}'
    )
    # `foto_muestra` es columna propia (fondo de ejemplo de la galería), NO va dentro de
    # `documento`: el GC la protege por separado o el barrido borra el fondo de muestra.
    monkeypatch.setattr(
        media_gc.repos, "listar_plantillas_diseno",
        lambda *a, **k: [
            {"miniatura": "mini.png", "documento": doc, "foto_muestra": "plantillas/fondo-muestra.jpg"}
        ],
    )
    vivas = media_gc.referencias_vivas()
    assert {
        "logo-oficial.png", "mini.png", "fondo.jpg", "logo-spec.png", "muestra.jpg",
        "plantillas/fondo-muestra.jpg",
    } <= vivas


def test_protege_fotos_de_collage(monkeypatch):
    # Fotos de collage: JSON array `[{objeto, foco, zoom}, …]` en el campo `fotos`. Todas
    # las fotos del collage deben ser referencias vivas (no sueltas borrables).
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [
            {
                "id": "pub1",
                "imagen": "",
                "foto": "",
                "fotos": '[{"objeto":"hueco1.jpg","foco":[0.5,0.5],"zoom":1},'
                '{"objeto":"hueco2.jpg","foco":[0.3,0.7],"zoom":1.2}]',
            },
            {"id": "pub2", "imagen": "", "foto": "", "fotos": ""},  # sin collage
        ],
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.delattr(media_gc.repos, "listar_documento_versiones", raising=False)

    vivas = media_gc.referencias_vivas()
    assert {"hueco1.jpg", "hueco2.jpg"} <= vivas

    # Las fotos del collage son VIEJAS pero referenciadas por la publicación: NO se borran.
    _objetos(monkeypatch, [("hueco1.jpg", _VIEJO), ("hueco2.jpg", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == [] and res["conservados"] == 2


def test_protege_slides_de_carrusel(monkeypatch):
    # Slides de carrusel: JSON array `[{tipo, objeto, foto?}, …]` en el campo `carrusel`. La
    # placa horneada (`objeto`) y la procedencia (`foto`) de cada slide son referencias vivas.
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [
            {
                "id": "pub1",
                "imagen": "render/portada.png",
                "foto": "",
                "fotos": "",
                "carrusel": '[{"tipo":"imagen","objeto":"artes/slide1.png","foto":"originales/fondo1.jpg"},'
                '{"tipo":"imagen","objeto":"artes/slide2.png"}]',
            },
            {"id": "pub2", "imagen": "", "foto": "", "fotos": "", "carrusel": ""},  # sin carrusel
        ],
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.delattr(media_gc.repos, "listar_documento_versiones", raising=False)

    vivas = media_gc.referencias_vivas()
    assert {"artes/slide1.png", "artes/slide2.png", "originales/fondo1.jpg"} <= vivas

    # Slides VIEJAS pero referenciadas por el carrusel: NO se borran.
    _objetos(
        monkeypatch,
        [("artes/slide1.png", _VIEJO), ("artes/slide2.png", _VIEJO), ("originales/fondo1.jpg", _VIEJO)],
    )
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == [] and res["conservados"] == 3


def test_protege_carrusel_json_malformado(monkeypatch):
    # Si el JSON de `carrusel` está malformado, el GC lo ignora silenciosamente (robusto).
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [{"id": "p", "imagen": "", "foto": "", "fotos": "", "carrusel": "{bad"}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.delattr(media_gc.repos, "listar_documento_versiones", raising=False)
    assert media_gc.referencias_vivas() == set()


def test_protege_collage_json_malformado(monkeypatch):
    # Si el JSON de `fotos` está malformado, el GC lo ignora silenciosamente (robusto).
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [{"id": "pub1", "imagen": "", "foto": "", "fotos": "invalid json"}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.delattr(media_gc.repos, "listar_documento_versiones", raising=False)

    # No debe fallar, simplemente no suma referencias del collage malformado.
    vivas = media_gc.referencias_vivas()
    assert vivas == set()


def test_protege_documento_versiones_render_objeto(monkeypatch):
    # Cada versión del documento tiene `render_objeto` (PNG renderizado). Estos PNGs son
    # referencias vivas (no sueltos borrables).
    def _listar_docs(cid, pid):
        return [
            {
                "id": "v1",
                "version": 1,
                "render_objeto": "render-v1.png",
                "documento": "{}",
            },
            {
                "id": "v2",
                "version": 2,
                "render_objeto": "render-v2.png",
                "documento": "{}",
            },
        ]

    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [{"id": "pid1", "publicacion_id": "cid1", "imagen": "", "foto": ""}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_documento_versiones", _listar_docs)

    vivas = media_gc.referencias_vivas()
    assert {"render-v1.png", "render-v2.png"} <= vivas

    # Los PNGs renderizados son VIEJOS pero referenciados por las versiones: NO se borran.
    _objetos(monkeypatch, [("render-v1.png", _VIEJO), ("render-v2.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == [] and res["conservados"] == 2


def test_protege_documento_versiones_media_del_documento(monkeypatch):
    # El JSON `documento` de cada versión contiene referencias a media (capas con objeto,
    # fondos con imagen.media_id, logos, etc.). Estas referencias son vivas (no sueltas).
    doc_v1 = (
        '{"fondo":{"tipo":"imagen","imagen":{"media_id":"fondo-v1.jpg"}},'
        '"capas":[{"tipo":"imagen","objeto":"imagen-v1.png"}]}'
    )
    doc_v2 = (
        '{"fondo":{"tipo":"imagen","imagen":{"media_id":"fondo-v2.jpg"}},'
        '"capas":[{"tipo":"logo","tipo_logo":"imagen","media_id":"logo-v2.png"}]}'
    )

    def _listar_docs(cid, pid):
        return [
            {
                "id": "v1",
                "version": 1,
                "render_objeto": "render-v1.png",
                "documento": doc_v1,
            },
            {
                "id": "v2",
                "version": 2,
                "render_objeto": "render-v2.png",
                "documento": doc_v2,
            },
        ]

    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [{"id": "pid1", "publicacion_id": "cid1", "imagen": "", "foto": ""}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_documento_versiones", _listar_docs)

    vivas = media_gc.referencias_vivas()
    # render_objeto + media del documento de ambas versiones.
    assert {
        "render-v1.png", "render-v2.png",
        "fondo-v1.jpg", "imagen-v1.png",
        "fondo-v2.jpg", "logo-v2.png",
    } <= vivas

    # Todos VIEJOS pero referenciados por las versiones: NO se borran.
    _objetos(monkeypatch, [
        ("render-v1.png", _VIEJO),
        ("fondo-v1.jpg", _VIEJO),
        ("imagen-v1.png", _VIEJO),
        ("render-v2.png", _VIEJO),
        ("fondo-v2.jpg", _VIEJO),
        ("logo-v2.png", _VIEJO),
    ])
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == [] and res["conservados"] == 6


def test_documento_versiones_malformado_es_ignorado(monkeypatch):
    # Si el JSON `documento` está malformado, el GC lo ignora (robusto).
    def _listar_docs(cid, pid):
        return [
            {
                "id": "v1",
                "version": 1,
                "render_objeto": "render-v1.png",
                "documento": "invalid json",  # malformado
            },
        ]

    monkeypatch.setattr(
        media_gc.repos, "listar_piezas",
        lambda *a, **k: [{"id": "pid1", "publicacion_id": "cid1", "imagen": "", "foto": ""}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_documento_versiones", _listar_docs)

    # No debe fallar, simplemente suma solo el render_objeto (el documento JSON es inútil).
    vivas = media_gc.referencias_vivas()
    assert "render-v1.png" in vivas


# --------------------------------------------------------------------------- #
# sueltos / limpiar: la definicion conservadora                              #
# --------------------------------------------------------------------------- #


def test_no_borra_referenciado_por_publicacion(monkeypatch):
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas", lambda *a, **k: [{"imagen": "viva.png"}]
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    # "viva.png" es VIEJA pero referenciada: NO debe borrarse.
    _objetos(monkeypatch, [("viva.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar()
    assert borrados == []
    assert res["borrados"] == 0 and res["conservados"] == 1


def test_no_borra_catalogado_en_texto(monkeypatch, repos_vacios):
    monkeypatch.setattr(
        media_gc.repos, "listar_media_catalogo", lambda *a, **k: [{"objeto": "cat.png"}]
    )
    _objetos(monkeypatch, [("cat.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar()
    assert borrados == []
    assert res["borrados"] == 0 and res["conservados"] == 1


def test_no_borra_reciente_aunque_suelto(monkeypatch, repos_vacios):
    # Sin referencias, pero el objeto es NUEVO (1h < umbral 24h): se conserva.
    _objetos(monkeypatch, [("nuevo.png", _NUEVO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == []
    assert res["borrados"] == 0 and res["conservados"] == 1


def test_borra_el_suelto_viejo(monkeypatch, repos_vacios):
    _objetos(monkeypatch, [("render/suelto.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["render/suelto.png"]
    assert res["borrados"] == 1 and res["conservados"] == 0
    assert res["nombres"] == ["render/suelto.png"] and res["dry_run"] is False


def test_mezcla_solo_borra_el_suelto_viejo(monkeypatch):
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas", lambda *a, **k: [{"imagen": "viva.png"}]
    )
    monkeypatch.setattr(
        media_gc.repos, "listar_media_catalogo", lambda *a, **k: [{"objeto": "cat.png"}]
    )
    _objetos(
        monkeypatch,
        [
            ("viva.png", _VIEJO),       # referenciada -> conservar
            ("cat.png", _VIEJO),        # catalogada -> conservar
            ("generadas/reciente.png", _NUEVO),  # suelta pero reciente -> conservar
            ("render/basura.png", _VIEJO),        # suelta, vieja y regenerable -> BORRAR
        ],
    )
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["render/basura.png"]
    assert res["borrados"] == 1 and res["conservados"] == 3


def test_borra_copyright_viejo_al_cambiar_la_foto(monkeypatch):
    # Stock SIN LICENCIA: la pieza apunta ahora a `copyright/nueva.jpg` (se cambió la foto).
    # La anterior `copyright/vieja.jpg` ya no la referencia nadie -> el GC la borra.
    monkeypatch.setattr(
        media_gc.repos, "listar_piezas", lambda *a, **k: [{"foto": "copyright/nueva.jpg"}]
    )
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    _objetos(
        monkeypatch,
        [
            ("copyright/nueva.jpg", _VIEJO),  # referenciada por la pieza -> conservar
            ("copyright/vieja.jpg", _VIEJO),  # huérfana tras el cambio -> BORRAR
        ],
    )
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["copyright/vieja.jpg"]
    assert res["borrados"] == 1 and res["conservados"] == 1


def test_no_borra_foto_de_biblioteca_aunque_sin_uso(monkeypatch, repos_vacios):
    # DEFENSA: la biblioteca persiste por sí misma. Una foto original/portal/subida/del archivo
    # fotográfico (y los artes/plantillas/logos reusables) NO es borrable por el GC aunque sea
    # vieja y NINGUNA pieza la use: solo lo son las efímeras (copyright) y las cachés.
    _objetos(
        monkeypatch,
        [
            ("originales/foto.jpg", _VIEJO),
            ("portal/nota.jpg", _VIEJO),
            ("fotos/subida.jpg", _VIEJO),
            ("fotografias/cancha.jpg", _VIEJO),
            ("artes/arte.png", _VIEJO),
            ("plantillas/plantilla.png", _VIEJO),
            ("logos/logo.png", _VIEJO),
        ],
    )
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == []
    assert res["borrados"] == 0 and res["conservados"] == 7


def test_borra_caches_regenerables_y_copyright_sin_uso(monkeypatch, repos_vacios):
    # Solo categorías efímeras/regenerables: stock sin licencia (copyright) y cachés
    # (render/deriv/previews/generadas) viejas y sin uso SÍ se recolectan.
    _objetos(
        monkeypatch,
        [
            ("copyright/stock.jpg", _VIEJO),
            ("render/r.png", _VIEJO),
            ("deriv/d.webp", _VIEJO),
            ("previews/p.png", _VIEJO),
            ("generadas/g.png", _VIEJO),
        ],
    )
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert sorted(borrados) == [
        "copyright/stock.jpg", "deriv/d.webp", "generadas/g.png",
        "previews/p.png", "render/r.png",
    ]
    assert res["borrados"] == 5 and res["conservados"] == 0


def test_dry_run_no_borra(monkeypatch, repos_vacios):
    _objetos(monkeypatch, [("render/suelto.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24, dry_run=True)
    assert borrados == []  # NO se llamo a borrar_objeto
    assert res["dry_run"] is True
    assert res["borrados"] == 0 and res["conservados"] == 0
    assert res["nombres"] == ["render/suelto.png"]


def test_limpiar_robusto_ante_fallo_por_objeto(monkeypatch, repos_vacios):
    # Dos sueltos viejos: el primer borrado falla, el segundo debe seguir adelante.
    _objetos(monkeypatch, [("render/falla.png", _VIEJO), ("render/ok.png", _VIEJO)])
    borrados: list[str] = []

    def _borrar(nombre):
        if nombre == "render/falla.png":
            raise OSError("disco lleno")
        borrados.append(nombre)

    monkeypatch.setattr(media_gc.almacen_media, "borrar_objeto", _borrar)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["render/ok.png"]   # el segundo se borro pese al fallo del primero
    assert res["borrados"] == 1            # solo cuenta el que de verdad se borro
    assert res["conservados"] == 0


# --------------------------------------------------------------------------- #
# Daemon: respeta el gate (KENI_MEDIA_GC off por defecto -> no barre)           #
# --------------------------------------------------------------------------- #


def test_daemon_no_barre_si_gate_apagado(monkeypatch):
    # Sin KENI_MEDIA_GC el daemon esta gateado: bucle_gateado no debe invocar el barrido.
    monkeypatch.delenv(config.ENV_MEDIA_GC, raising=False)
    assert config.media_gc_activo() is False

    llamadas = {"n": 0}

    def _sweep():
        llamadas["n"] += 1

    daemon_util.bucle_gateado(
        activo_fn=config.media_gc_activo,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=_sweep,
        tick_seg=0.0,
        log=media_gc_daemon._log,
        _max_vueltas=3,
    )
    assert llamadas["n"] == 0  # gate OFF -> nunca barrio


def test_daemon_barre_si_gate_encendido(monkeypatch):
    monkeypatch.setenv(config.ENV_MEDIA_GC, "1")
    assert config.media_gc_activo() is True

    llamadas = {"n": 0}

    def _sweep():
        llamadas["n"] += 1

    daemon_util.bucle_gateado(
        activo_fn=config.media_gc_activo,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=_sweep,
        tick_seg=0.0,
        log=media_gc_daemon._log,
        _max_vueltas=1,
    )
    assert llamadas["n"] == 1  # encendido -> barrio de inmediato


def test_limpiar_reverifica_referencias_antes_de_borrar(monkeypatch, repos_vacios):
    """Anti-TOCTOU: si un objeto se vuelve REFERENCIADO entre el calculo de sueltos y el
    borrado (una pieza nueva lo fija como imagen), el barrido lo RESCATA (no lo borra)."""
    _objetos(monkeypatch, [("render/rescatado.png", _VIEJO), ("render/suelto.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    # 1a llamada (dentro de `sueltos`): nada referenciado. 2a llamada (re-verificacion
    # previa al borrado): "render/rescatado.png" ya esta referenciado por una pieza nueva.
    llamadas = {"n": 0}

    def _vivas_cambiantes():
        llamadas["n"] += 1
        return set() if llamadas["n"] == 1 else {"render/rescatado.png"}

    monkeypatch.setattr(media_gc, "referencias_vivas", _vivas_cambiantes)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["render/suelto.png"]  # el rescatado NO se borro
    assert res["borrados"] == 1
    assert res["conservados"] == 1  # el rescatado cuenta como conservado
    assert "render/rescatado.png" not in res["nombres"]
