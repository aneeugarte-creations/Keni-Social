"""Tests OFFLINE de la GC de media suelta (`dominio.media_gc` + daemon).

Mockean `almacen_media.listar_objetos`/`borrar_objeto` y los repos de referencias
(`listar_publicaciones`, `listar_publicaciones_comerciales`, `listar_media_catalogo`),
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

# Antiguedades sinteticas (epoch): "viejo" = hace 48h, "nuevo" = hace 1h.
_AHORA = time.time()
_VIEJO = _AHORA - 48 * 3600.0
_NUEVO = _AHORA - 1 * 3600.0


@pytest.fixture
def repos_vacios(monkeypatch):
    """Por defecto: sin publicaciones, sin comerciales, sin texto (todo suelto)."""
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones", lambda *a, **k: [])
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: []
    )
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


def test_referencias_unen_publicaciones_y_comerciales(monkeypatch):
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones",
        lambda *a, **k: [{"imagen": "pub.png"}, {"imagen": ""}, {"imagen": "  "}],
    )
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones_comerciales",
        lambda *a, **k: [{"imagen": "com.png"}, {"url": "https://x"}],  # url no aporta
    )
    # Sin catalogo-media: solo cuentan las publicaciones.
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    assert media_gc.referencias_vivas() == {"pub.png", "com.png"}


def test_catalogo_media_es_red_de_seguridad_opcional_si_existe(monkeypatch):
    # Si el repo de catalogo-media existe, sus objetos se suman (red de seguridad).
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones", lambda *a, **k: [])
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: []
    )
    monkeypatch.setattr(
        media_gc.repos, "listar_media_catalogo",
        lambda *a, **k: [{"objeto": "cat.png"}, {"objeto": ""}],
    )
    assert media_gc.referencias_vivas() == {"cat.png"}


def test_gc_no_falla_si_catalogo_media_no_existe(monkeypatch):
    # Cuando se elimine `api/catalogo_media.py`, el repo perdera la funcion: el GC NO debe
    # fallar; simplemente no consulta esa fuente (se basa solo en publicaciones).
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones", lambda *a, **k: [])
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: []
    )
    monkeypatch.delattr(media_gc.repos, "listar_media_catalogo", raising=False)
    assert media_gc.referencias_vivas() == set()
    # Y un suelto viejo se borra igual (sin la red de seguridad de catalogo-media).
    _objetos(monkeypatch, [("suelto.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["suelto.png"] and res["borrados"] == 1


def test_protege_foto_cruda_de_publicacion(monkeypatch):
    # Con render on-demand la foto cruda NO está horneada en `imagen`: debe ser referencia viva.
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones",
        lambda *a, **k: [{"imagen": "", "foto": "foto-cruda.jpg"}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: [])
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
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: [])
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
    monkeypatch.setattr(
        media_gc.repos, "listar_plantillas_diseno",
        lambda *a, **k: [{"miniatura": "mini.png", "documento": doc}],
    )
    vivas = media_gc.referencias_vivas()
    assert {"logo-oficial.png", "mini.png", "fondo.jpg", "logo-spec.png", "muestra.jpg"} <= vivas


def test_protege_fotos_de_collage(monkeypatch):
    # Fotos de collage: JSON array `[{objeto, foco, zoom}, …]` en el campo `fotos`. Todas
    # las fotos del collage deben ser referencias vivas (no sueltas borrables).
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones",
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
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: [])
    monkeypatch.setattr(media_gc.repos, "listar_media_catalogo", lambda *a, **k: [])
    monkeypatch.delattr(media_gc.repos, "listar_documento_versiones", raising=False)

    vivas = media_gc.referencias_vivas()
    assert {"hueco1.jpg", "hueco2.jpg"} <= vivas

    # Las fotos del collage son VIEJAS pero referenciadas por la publicación: NO se borran.
    _objetos(monkeypatch, [("hueco1.jpg", _VIEJO), ("hueco2.jpg", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == [] and res["conservados"] == 2


def test_protege_collage_json_malformado(monkeypatch):
    # Si el JSON de `fotos` está malformado, el GC lo ignora silenciosamente (robusto).
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones",
        lambda *a, **k: [{"id": "pub1", "imagen": "", "foto": "", "fotos": "invalid json"}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: [])
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
        media_gc.repos, "listar_publicaciones",
        lambda *a, **k: [{"id": "pid1", "contenido_id": "cid1", "imagen": "", "foto": ""}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: [])
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
        media_gc.repos, "listar_publicaciones",
        lambda *a, **k: [{"id": "pid1", "contenido_id": "cid1", "imagen": "", "foto": ""}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: [])
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
        media_gc.repos, "listar_publicaciones",
        lambda *a, **k: [{"id": "pid1", "contenido_id": "cid1", "imagen": "", "foto": ""}],
    )
    monkeypatch.setattr(media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: [])
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
        media_gc.repos, "listar_publicaciones", lambda *a, **k: [{"imagen": "viva.png"}]
    )
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: []
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
    _objetos(monkeypatch, [("suelto.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["suelto.png"]
    assert res["borrados"] == 1 and res["conservados"] == 0
    assert res["nombres"] == ["suelto.png"] and res["dry_run"] is False


def test_mezcla_solo_borra_el_suelto_viejo(monkeypatch):
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones", lambda *a, **k: [{"imagen": "viva.png"}]
    )
    monkeypatch.setattr(
        media_gc.repos, "listar_publicaciones_comerciales", lambda *a, **k: []
    )
    monkeypatch.setattr(
        media_gc.repos, "listar_media_catalogo", lambda *a, **k: [{"objeto": "cat.png"}]
    )
    _objetos(
        monkeypatch,
        [
            ("viva.png", _VIEJO),       # referenciada -> conservar
            ("cat.png", _VIEJO),        # catalogada -> conservar
            ("reciente.png", _NUEVO),   # suelta pero reciente -> conservar
            ("basura.png", _VIEJO),     # suelta y vieja -> BORRAR
        ],
    )
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["basura.png"]
    assert res["borrados"] == 1 and res["conservados"] == 3


def test_dry_run_no_borra(monkeypatch, repos_vacios):
    _objetos(monkeypatch, [("suelto.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24, dry_run=True)
    assert borrados == []  # NO se llamo a borrar_objeto
    assert res["dry_run"] is True
    assert res["borrados"] == 0 and res["conservados"] == 0
    assert res["nombres"] == ["suelto.png"]


def test_limpiar_robusto_ante_fallo_por_objeto(monkeypatch, repos_vacios):
    # Dos sueltos viejos: el primer borrado falla, el segundo debe seguir adelante.
    _objetos(monkeypatch, [("falla.png", _VIEJO), ("ok.png", _VIEJO)])
    borrados: list[str] = []

    def _borrar(nombre):
        if nombre == "falla.png":
            raise OSError("disco lleno")
        borrados.append(nombre)

    monkeypatch.setattr(media_gc.almacen_media, "borrar_objeto", _borrar)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["ok.png"]          # el segundo se borro pese al fallo del primero
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
    _objetos(monkeypatch, [("rescatado.png", _VIEJO), ("suelto.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    # 1a llamada (dentro de `sueltos`): nada referenciado. 2a llamada (re-verificacion
    # previa al borrado): "rescatado.png" ya esta referenciado por una pieza nueva.
    llamadas = {"n": 0}

    def _vivas_cambiantes():
        llamadas["n"] += 1
        return set() if llamadas["n"] == 1 else {"rescatado.png"}

    monkeypatch.setattr(media_gc, "referencias_vivas", _vivas_cambiantes)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["suelto.png"]  # el rescatado NO se borro
    assert res["borrados"] == 1
    assert res["conservados"] == 1  # el rescatado cuenta como conservado
    assert "rescatado.png" not in res["nombres"]
