from __future__ import annotations

import tomllib

import pytest

from keni_metricas.agregador import FuenteCompuesta
from keni_metricas.config import (
    ConfigInvalida,
    FuenteScoped,
    cargar_config,
    construir_fuente,
)
from keni_metricas.fuentes.base import CuentaNoEncontrada
from keni_metricas.fuentes.muestra import FuenteMuestra


def _escribir_config(monkeypatch, tmp_path, contenido: str):
    """Escribe un config.toml temporal y lo apunta via env, aislando las env vars."""
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    ruta = tmp_path / "config.toml"
    ruta.write_text(contenido, encoding="utf-8")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    return ruta


def test_default_es_metricool(monkeypatch, tmp_path):
    """La fuente única por defecto es `metricool`.

    Sin credenciales degrada a una `FuenteMetricool` VACÍA (estado honesto, sin
    cuentas), nunca a la fuente de muestra: el producto no muestra datos de demo por
    defecto.
    """
    from keni_metricas.fuentes.metricool import FuenteMetricool

    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("METRICOOL_USER_TOKEN", raising=False)
    monkeypatch.delenv("METRICOOL_USER_ID", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteMetricool)
    assert fuente.nombre == "metricool"


def test_fuente_muestra_explicita_por_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteMuestra)
    assert fuente.nombre == "muestra"


def test_fuente_real_requiere_flag_opt_in(monkeypatch, tmp_path):
    """`real` se rechaza sin el flag `KENI_METRICAS_PERMITIR_REAL`."""
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "real")
    monkeypatch.delenv("KENI_METRICAS_PERMITIR_REAL", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    assert "metricool" in str(exc.value)


def test_fuente_real_con_flag_construye_compuesta(monkeypatch, tmp_path):
    """Con el flag opt-in, `real` instancia la FuenteCompuesta (adaptadores)."""
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "real")
    monkeypatch.setenv("KENI_METRICAS_PERMITIR_REAL", "1")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteCompuesta)
    assert fuente.nombre == "real"


# --- T2.B: fuente `metricool` (consumidor de la API REST) --------------------
def test_metricool_sin_credenciales_no_muestra_datos_falsos(monkeypatch, tmp_path):
    """fuente='metricool' sin token -> fuente Metricool VACÍA (sin cuentas), no `muestra`.

    El producto no debe mostrar datos de demostración: sin credenciales se ve un estado
    vacío honesto (sin cuentas), nunca cifras inventadas.
    """
    from keni_metricas.fuentes.metricool import FuenteMetricool

    monkeypatch.delenv("METRICOOL_USER_TOKEN", raising=False)
    monkeypatch.delenv("METRICOOL_USER_ID", raising=False)
    _escribir_config(monkeypatch, tmp_path, 'fuente = "metricool"\n')
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteMetricool)
    assert fuente.nombre == "metricool"
    assert not isinstance(fuente, FuenteMuestra)
    assert fuente.cuentas() == []  # sin credenciales: ninguna cuenta, ningún dato


def test_metricool_credenciales_por_toml(monkeypatch, tmp_path):
    """El mapeo de marcas (blogId) y la identidad se leen del TOML."""
    monkeypatch.delenv("METRICOOL_USER_TOKEN", raising=False)
    monkeypatch.delenv("METRICOOL_USER_ID", raising=False)
    _escribir_config(
        monkeypatch,
        tmp_path,
        'fuente = "metricool"\n'
        "[metricool]\n"
        'user_token = "TOK"\n'
        'user_id = "999"\n'
        "[metricool.marcas.claro_sports]\n"
        'blog_id = "1234567"\n'
        'nombre = "Claro Sports"\n',
    )
    cfg = cargar_config()
    assert cfg.metricool.configurada
    assert cfg.metricool.user_token == "TOK"
    assert cfg.metricool.marcas["claro_sports"]["blog_id"] == "1234567"
    # construir_fuente devuelve el adapter real (no muestra) con credenciales.
    from keni_metricas.fuentes.metricool import FuenteMetricool

    assert isinstance(construir_fuente(cfg), FuenteMetricool)


def test_metricool_env_pisa_toml(monkeypatch, tmp_path):
    """METRICOOL_USER_TOKEN / METRICOOL_USER_ID tienen prioridad sobre el TOML."""
    _escribir_config(
        monkeypatch,
        tmp_path,
        "[metricool]\n"
        'user_token = "DEL_TOML"\n'
        'user_id = "111"\n'
        "[metricool.marcas.m]\n"
        'blog_id = "1"\n',
    )
    monkeypatch.setenv("METRICOOL_USER_TOKEN", "DEL_ENV")
    monkeypatch.setenv("METRICOOL_USER_ID", "222")
    cfg = cargar_config()
    assert cfg.metricool.user_token == "DEL_ENV"
    assert cfg.metricool.user_id == "222"


# --- B1: TOML mal formado -> ConfigInvalida en espanol, sin traceback tomllib --
def test_b1_toml_mal_formado_lanza_config_invalida(monkeypatch, tmp_path):
    ruta = _escribir_config(monkeypatch, tmp_path, 'fuente = "muestra"\n[[cuenta]\nid = "x"\n')
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    # mensaje en espanol, con la ruta y (en 3.11+) la linea del fallo
    assert "error de sintaxis TOML" in msg
    assert str(ruta) in msg
    assert "linea 2" in msg
    # es capturable como ValueError (contrato para los CLIs y el doctor)
    assert isinstance(exc.value, ValueError)


# --- B4: cuenta sin nombre / plataforma invalida -> ConfigInvalida que cuenta ---
def test_b4_cuenta_sin_nombre(monkeypatch, tmp_path):
    _escribir_config(monkeypatch, tmp_path, '[[cuenta]]\nid = "amx"\n')
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "nombre" in msg
    assert "amx" in msg  # identifica QUE cuenta falla


def test_b4_cuenta_sin_id(monkeypatch, tmp_path):
    _escribir_config(monkeypatch, tmp_path, '[[cuenta]]\nnombre = "AMX"\n')
    with pytest.raises(ConfigInvalida, match="id"):
        cargar_config()


def test_b4_plataforma_invalida(monkeypatch, tmp_path):
    _escribir_config(
        monkeypatch,
        tmp_path,
        '[[cuenta]]\nid = "amx"\nnombre = "AMX"\n'
        '[cuenta.plataformas]\nmyspace = "@amx"\n',
    )
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "myspace" in msg  # nombra la plataforma invalida
    assert "facebook" in msg and "instagram" in msg  # lista las validas


def test_b4_cuenta_valida_se_carga(monkeypatch, tmp_path):
    _escribir_config(
        monkeypatch,
        tmp_path,
        '[[cuenta]]\nid = "amx"\nnombre = "AMX"\n'
        '[cuenta.plataformas]\ninstagram = "@amx"\n',
    )
    cfg = cargar_config()
    assert len(cfg.cuentas) == 1
    assert cfg.cuentas[0].nombre == "AMX"


# --- B5: fuente desconocida -> ConfigInvalida listando las validas -------------
def test_b5_fuente_desconocida_lanza_config_invalida(monkeypatch, tmp_path):
    _escribir_config(monkeypatch, tmp_path, 'fuente = "magia"\n')
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "magia" in msg
    assert "muestra" in msg and "real" in msg  # lista los valores validos


def test_b5_fuente_invalida_por_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "ninguna")
    with pytest.raises(ConfigInvalida, match="muestra, real"):
        cargar_config()


# --- B4 (mas ramas): cuenta no-tabla / plataformas con forma invalida ----------
def test_b4_cuenta_no_es_tabla(monkeypatch, tmp_path):
    # Un array de cuentas donde un elemento no es una tabla [[cuenta]].
    # (TOML no permite "cuenta = [\"x\"]" como [[cuenta]] directamente, pero el
    # array-of-tables admite que se cuele un escalar segun como se declare.)
    _escribir_config(monkeypatch, tmp_path, 'cuenta = ["no-soy-una-tabla"]\n')
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "#1" in msg  # identifica la cuenta por posicion 1-based
    assert "tabla" in msg


def test_b4_plataformas_no_es_tabla(monkeypatch, tmp_path):
    # `plataformas` declarado como string en vez de tabla plataforma->handle.
    _escribir_config(
        monkeypatch,
        tmp_path,
        '[[cuenta]]\nid = "amx"\nnombre = "AMX"\nplataformas = "instagram"\n',
    )
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "plataformas" in msg
    assert "amx" in msg  # identifica la cuenta


def test_b4_cuenta_id_vacio_es_invalido(monkeypatch, tmp_path):
    # id presente pero vacio/espacios -> invalido (no basta con que exista la clave).
    _escribir_config(monkeypatch, tmp_path, '[[cuenta]]\nid = "   "\nnombre = "AMX"\n')
    with pytest.raises(ConfigInvalida, match="id"):
        cargar_config()


def test_b4_cuenta_valida_materializa_plataforma(monkeypatch, tmp_path):
    # La plataforma valida se mapea a su enum y conserva el handle como str.
    from keni_metricas.schema import Plataforma

    _escribir_config(
        monkeypatch,
        tmp_path,
        '[[cuenta]]\nid = "amx"\nnombre = "AMX"\n'
        '[cuenta.plataformas]\ninstagram = "@amx"\n',
    )
    cfg = cargar_config()
    plats = cfg.cuentas[0].plataformas
    assert plats[Plataforma.instagram] == "@amx"


# --- TOML mal formado: extraccion de linea PORTABLE (3.11-3.14) ----------------
def test_toml_error_linea_desde_mensaje_sin_lineno(monkeypatch, tmp_path):
    """El fallback regex ('at line N') se usa cuando no hay atributo `lineno`.

    En 3.14 `TOMLDecodeError` trae `lineno`; en 3.11-3.13 no, y la linea se saca
    del mensaje. Forzamos la rama 3.11-3.13 simulando un error SIN `lineno` cuyo
    mensaje lleve 'at line 7', y comprobamos que el mensaje en espanol incluye
    'linea 7' en CUALQUIER version.
    """
    ruta = _escribir_config(monkeypatch, tmp_path, 'fuente = "muestra"\n')

    class _ErrSinLineno(tomllib.TOMLDecodeError):
        # No exponemos `lineno`: emula el shape de Python 3.11-3.13.
        def __init__(self, msg):
            ValueError.__init__(self, msg)

    def _loads_falla(_texto):
        raise _ErrSinLineno("roto at line 7, column 3")

    monkeypatch.setattr("keni_metricas.config.tomllib.loads", _loads_falla)
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "linea 7" in msg
    assert str(ruta) in msg
    assert "error de sintaxis TOML" in msg


def test_toml_error_sin_numero_de_linea_no_inventa_ubicacion(monkeypatch, tmp_path):
    """Si ni hay `lineno` ni el mensaje trae 'at line N', no se anota ubicacion."""
    _escribir_config(monkeypatch, tmp_path, 'fuente = "muestra"\n')

    class _ErrSinLineno(tomllib.TOMLDecodeError):
        def __init__(self, msg):
            ValueError.__init__(self, msg)

    def _loads_falla(_texto):
        raise _ErrSinLineno("algo roto sin ubicacion")

    monkeypatch.setattr("keni_metricas.config.tomllib.loads", _loads_falla)
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "error de sintaxis TOML" in msg
    # No se anota la ubicacion "(linea N)" cuando no se pudo determinar.
    assert "(linea" not in msg


# --- OSError al leer el config -> ConfigInvalida en espanol --------------------
def test_oserror_de_lectura_se_envuelve(monkeypatch, tmp_path):
    """Un fallo de E/S al leer el config se reporta como ConfigInvalida, no crudo."""
    ruta = _escribir_config(monkeypatch, tmp_path, 'fuente = "muestra"\n')

    def _read_falla(*_a, **_k):
        raise OSError("disco ocupado")

    monkeypatch.setattr("pathlib.Path.read_text", _read_falla)
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "No se pudo leer el config" in msg
    assert str(ruta) in msg
    assert isinstance(exc.value, ValueError)


# --- Scoping de marcas (KENI_METRICAS_MARCAS / campo `marcas`) ------------------
def test_marcas_por_env_envuelve_en_fuente_scoped(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.setenv("KENI_METRICAS_MARCAS", "claro_sports, unotv")
    cfg = cargar_config()
    # La env var se parsea respetando orden y descartando vacios/duplicados.
    assert cfg.marcas == ["claro_sports", "unotv"]
    fuente = construir_fuente(cfg)
    assert isinstance(fuente, FuenteScoped)
    ids = {c.id for c in fuente.cuentas()}
    assert ids == {"claro_sports", "unotv"}


def test_marcas_campo_config_cuando_no_hay_env(monkeypatch, tmp_path):
    _escribir_config(
        monkeypatch,
        tmp_path,
        'fuente = "muestra"\nmarcas = ["unotv", "unotv", ""]\n',
    )
    cfg = cargar_config()
    # duplicados y vacios descartados, orden preservado
    assert cfg.marcas == ["unotv"]


def test_env_marcas_tiene_prioridad_sobre_campo_config(monkeypatch, tmp_path):
    _escribir_config(monkeypatch, tmp_path, 'fuente = "muestra"\nmarcas = ["unotv"]\n')
    monkeypatch.setenv("KENI_METRICAS_MARCAS", "claro_sports")
    cfg = cargar_config()
    assert cfg.marcas == ["claro_sports"]


def test_sin_marcas_no_envuelve(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteMuestra)
    assert not isinstance(fuente, FuenteScoped)


# --- FuenteScoped: comportamiento de alcance -----------------------------------
def test_fuente_scoped_resumen_dentro_de_alcance():
    scoped = FuenteScoped(FuenteMuestra(), ["claro_sports"])
    res = scoped.resumen("claro_sports", "semana")
    assert res.cuenta == "claro_sports"


def test_fuente_scoped_resumen_fuera_de_alcance_rechaza():
    scoped = FuenteScoped(FuenteMuestra(), ["claro_sports"])
    with pytest.raises(CuentaNoEncontrada) as exc:
        # unotv existe en la fuente subyacente pero NO en el alcance.
        scoped.resumen("unotv", "semana")
    assert "unotv" in str(exc.value)
    assert "claro_sports" in str(exc.value)  # lista las disponibles


def test_fuente_scoped_delega_campanias_ads_dentro_de_alcance():
    """FuenteScoped DEBE exponer `campanias_ads` (delegando): una campaña es siempre
    por-marca (envuelta), y sin esto su inorgánico (y el del dashboard por-marca) salía
    SIEMPRE vacío. Regresión del bug de Ads inorgánico."""

    class _ConAds(FuenteMuestra):
        def campanias_ads(self, cuenta_id, rango):
            return [{"nombre": "ALCANCE CAMPAÑA CHIHUAHUA", "cuenta": cuenta_id, "rango": rango}]

    scoped = FuenteScoped(_ConAds(), ["claro_sports"])
    assert scoped.campanias_ads("claro_sports", "mes") == [
        {"nombre": "ALCANCE CAMPAÑA CHIHUAHUA", "cuenta": "claro_sports", "rango": "mes"}
    ]


def test_fuente_scoped_campanias_ads_fuera_de_alcance_rechaza():
    class _ConAds(FuenteMuestra):
        def campanias_ads(self, cuenta_id, rango):
            return []

    scoped = FuenteScoped(_ConAds(), ["claro_sports"])
    with pytest.raises(CuentaNoEncontrada):
        scoped.campanias_ads("unotv", "mes")


def test_fuente_scoped_sin_ads_propaga_attributeerror():
    """Una fuente envuelta SIN Ads (muestra) propaga AttributeError; `construir_ads` lo
    captura y degrada a inorgánico vacío (no enmascara el wrap)."""
    scoped = FuenteScoped(FuenteMuestra(), ["claro_sports"])
    with pytest.raises(AttributeError):
        scoped.campanias_ads("claro_sports", "mes")


def test_fuente_scoped_mejores_piezas_dentro_y_fuera():
    scoped = FuenteScoped(FuenteMuestra(), ["claro_sports"])
    piezas = scoped.mejores_piezas("claro_sports", "semana", 2)
    assert len(piezas) == 2
    with pytest.raises(CuentaNoEncontrada):
        scoped.mejores_piezas("unotv", "semana", 2)


def test_fuente_scoped_alcance_vacio_mensaje():
    scoped = FuenteScoped(FuenteMuestra(), [])
    with pytest.raises(CuentaNoEncontrada) as exc:
        scoped.resumen("claro_sports", "semana")
    assert "ninguna en tu alcance" in str(exc.value)


def test_fuente_scoped_propaga_nombre():
    base = FuenteMuestra()
    scoped = FuenteScoped(base, ["claro_sports"])
    assert scoped.nombre == base.nombre


def test_construir_fuente_carga_config_si_no_se_pasa(monkeypatch, tmp_path):
    # construir_fuente() sin cfg debe cargar la config del entorno.
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    fuente = construir_fuente()
    assert isinstance(fuente, FuenteMuestra)
