"""Tests OFFLINE de la GC de media huerfana (`dominio.media_gc` + daemon).

Mockean `almacen_media.listar_objetos`/`borrar_objeto` y los repos de referencias
(`listar_publicaciones`, `listar_publicaciones_comerciales`, `listar_media_catalogo`),
asi NO necesitan Postgres ni almacen real. Verifican la definicion CONSERVADORA de huerfano:
no borra referenciados, ni catalogados, ni recientes (umbral); SI borra el huerfano viejo; y
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
    """Por defecto: sin publicaciones, sin comerciales, sin texto (todo huerfano)."""
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
    # Y un huerfano viejo se borra igual (sin la red de seguridad de catalogo-media).
    _objetos(monkeypatch, [("huerfano.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)
    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["huerfano.png"] and res["borrados"] == 1


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


# --------------------------------------------------------------------------- #
# huerfanos / limpiar: la definicion conservadora                              #
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


def test_no_borra_reciente_aunque_huerfano(monkeypatch, repos_vacios):
    # Sin referencias, pero el objeto es NUEVO (1h < umbral 24h): se conserva.
    _objetos(monkeypatch, [("nuevo.png", _NUEVO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == []
    assert res["borrados"] == 0 and res["conservados"] == 1


def test_borra_el_huerfano_viejo(monkeypatch, repos_vacios):
    _objetos(monkeypatch, [("huerfano.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["huerfano.png"]
    assert res["borrados"] == 1 and res["conservados"] == 0
    assert res["nombres"] == ["huerfano.png"] and res["dry_run"] is False


def test_mezcla_solo_borra_el_huerfano_viejo(monkeypatch):
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
            ("reciente.png", _NUEVO),   # huerfana pero reciente -> conservar
            ("basura.png", _VIEJO),     # huerfana y vieja -> BORRAR
        ],
    )
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24)
    assert borrados == ["basura.png"]
    assert res["borrados"] == 1 and res["conservados"] == 3


def test_dry_run_no_borra(monkeypatch, repos_vacios):
    _objetos(monkeypatch, [("huerfano.png", _VIEJO)])
    borrados = _captura_borrados(monkeypatch)

    res = media_gc.limpiar(antiguedad_horas=24, dry_run=True)
    assert borrados == []  # NO se llamo a borrar_objeto
    assert res["dry_run"] is True
    assert res["borrados"] == 0 and res["conservados"] == 0
    assert res["nombres"] == ["huerfano.png"]


def test_limpiar_robusto_ante_fallo_por_objeto(monkeypatch, repos_vacios):
    # Dos huerfanos viejos: el primer borrado falla, el segundo debe seguir adelante.
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
