"""Tests del modulo de configuracion CENTRAL (`keni_consola.config`), R-CONFIG-SPRAWL (#126).

Antes ~30 lecturas `os.environ.get("KENI_...")` vivian dispersas por todo el paquete.
Ahora `config` es la FUENTE UNICA: declara cada nombre `KENI_*` una vez y expone un
accesor por variable con su default/parseo/precedencia. Estos tests fijan ese contrato
(defaults cuando la var no esta, parseo tolerante, precedencia) para que la
centralizacion no cambie comportamiento.

Todo OFFLINE. NO usan la fixture `entorno` (que fija muchas vars): cada test limpia o
fija SOLO lo que prueba, leyendo siempre via accesor (lectura en tiempo de llamada).
"""

from __future__ import annotations

import pytest

from keni_consola import config

# Todas las vars que los accesores tocan: se limpian para ejercitar los DEFAULTS.
_TODAS = (
    config.ENV_HOST,
    config.ENV_PORT,
    config.ENV_TOKEN,
    config.ENV_COOKIE_SECURE,
    config.ENV_HTTPS,
    config.ENV_SESION_HORAS,
    config.ENV_ADMIN_USER,
    config.ENV_ADMIN_PASS,
    config.ENV_LOG_LEVEL,
    config.ENV_MAX_JOBS,
    config.ENV_MAX_COLA,
    config.ENV_CLAUDE_TIMEOUT,
    config.ENV_CLAUDE_MAX_USD,
    config.ENV_CLAUDE_MAX_TURNS,
    config.ENV_CLAUDE_SKIP_PERMISSIONS,
    config.ENV_SKILLS_CWD,
    config.ENV_SKILLS_EJECUCION_CWD,
    config.ENV_SKILLS_DIR,
    config.ENV_SKILLS_MAX_SUBIDA_MB,
    config.ENV_COMERCIAL_INTERVALO_SEGUNDOS,
    config.ENV_COMERCIAL_INTERVALO_HORAS,
    config.ENV_PROGRAMADOR_INTERVALO_SEGUNDOS,
)


@pytest.fixture
def limpio(monkeypatch):
    """Limpia TODAS las `KENI_*` que tocan los accesores, para probar los defaults."""
    for var in _TODAS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# --------------------------------------------------------------------------- #
# Nombres canonicos: el resto del paquete los re-exporta desde aqui            #
# --------------------------------------------------------------------------- #


def test_nombres_son_la_fuente_unica():
    """Los nombres `KENI_*` literales coinciden con los que usa el deploy/tests."""
    assert config.ENV_HOST == "KENI_CONSOLA_HOST"
    assert config.ENV_PORT == "KENI_CONSOLA_PORT"
    assert config.ENV_TOKEN == "KENI_CONSOLA_TOKEN"
    assert config.ENV_SESION_HORAS == "KENI_CONSOLA_SESION_HORAS"
    assert config.ENV_ADMIN_USER == "KENI_CONSOLA_ADMIN_USER"
    assert config.ENV_ADMIN_PASS == "KENI_CONSOLA_ADMIN_PASS"
    assert config.ENV_MAX_JOBS == "KENI_MAX_JOBS"
    assert config.ENV_MAX_COLA == "KENI_MAX_COLA"
    assert config.ENV_CLAUDE_TIMEOUT == "KENI_CLAUDE_TIMEOUT"
    assert config.ENV_CLAUDE_MAX_USD == "KENI_CLAUDE_MAX_USD"
    assert config.ENV_CLAUDE_MAX_TURNS == "KENI_CLAUDE_MAX_TURNS"
    assert config.ENV_CLAUDE_SKIP_PERMISSIONS == "KENI_CLAUDE_SKIP_PERMISSIONS"
    assert config.ENV_SKILLS_CWD == "KENI_SKILLS_CWD"
    assert config.ENV_DATA_DIR == "KENI_DATA_DIR"
    assert config.ENV_GENERACIONES == "KENI_CONSOLA_GENERACIONES"


def test_reexports_apuntan_a_config(limpio):
    """Los modulos re-exportan el MISMO nombre que declara `config` (no se duplica)."""
    from keni_consola import observabilidad, secretos, seguridad
    from keni_consola.auth import _comun, bootstrap

    assert seguridad.ENV_TOKEN == config.ENV_TOKEN
    assert seguridad.ENV_COOKIE_SECURE == config.ENV_COOKIE_SECURE
    assert seguridad.ENV_HTTPS == config.ENV_HTTPS
    assert observabilidad.ENV_NIVEL == config.ENV_LOG_LEVEL
    assert secretos.ENV_IMAGEN_API_KEY == config.ENV_IMAGEN_API_KEY
    assert secretos.ENV_IMAGEN_PROVEEDOR == config.ENV_IMAGEN_PROVEEDOR
    assert _comun.ENV_SESION_HORAS == config.ENV_SESION_HORAS
    assert _comun.SESION_HORAS_DEF == config.SESION_HORAS_DEF
    assert bootstrap.ENV_ADMIN_USER == config.ENV_ADMIN_USER
    assert bootstrap.ENV_ADMIN_PASS == config.ENV_ADMIN_PASS
    assert bootstrap.ADMIN_POR_DEFECTO == config.ADMIN_USER_DEF


# --------------------------------------------------------------------------- #
# Defaults cuando la var NO esta                                               #
# --------------------------------------------------------------------------- #


def test_defaults_cuando_no_hay_env(limpio):
    """Sin ninguna var puesta, cada accesor devuelve su default historico."""
    assert config.host() == "127.0.0.1"
    assert config.port() == 8765
    assert config.token() is None
    assert config.cookie_secure() is False
    assert config.flag_https() is False
    assert config.sesion_horas() == 12
    assert config.admin_user() == "admin"
    assert config.admin_pass() == ""
    assert config.log_level() == "INFO"
    assert config.max_jobs() == 4
    assert config.max_cola() == 16
    assert config.claude_timeout() == 600
    assert config.claude_max_usd() is None
    assert config.claude_max_turns() is None
    assert config.claude_skip_permisos() is True
    assert config.skills_cwd() is None
    assert config.skills_dir() is None
    assert config.skills_max_subida_mb() is None
    assert config.comercial_intervalo_segundos() is None
    assert config.comercial_intervalo_horas() is None
    assert config.programador_intervalo_segundos() is None


# --------------------------------------------------------------------------- #
# Parseo tolerante (numeros): valor valido vs invalido -> default              #
# --------------------------------------------------------------------------- #


def test_port_valido_e_invalido(limpio):
    limpio.setenv(config.ENV_PORT, "9123")
    assert config.port() == 9123
    limpio.setenv(config.ENV_PORT, "no-numero")
    assert config.port() == 8765


def test_max_jobs_minimo_1(limpio):
    limpio.setenv(config.ENV_MAX_JOBS, "8")
    assert config.max_jobs() == 8
    limpio.setenv(config.ENV_MAX_JOBS, "0")
    assert config.max_jobs() == 1  # clamp al minimo 1
    limpio.setenv(config.ENV_MAX_JOBS, "basura")
    assert config.max_jobs() == 4  # default


def test_max_cola_minimo_0(limpio):
    limpio.setenv(config.ENV_MAX_COLA, "3")
    assert config.max_cola() == 3
    limpio.setenv(config.ENV_MAX_COLA, "-5")
    assert config.max_cola() == 0  # clamp al minimo 0
    limpio.setenv(config.ENV_MAX_COLA, "x")
    assert config.max_cola() == 16  # default


def test_sesion_horas(limpio):
    limpio.setenv(config.ENV_SESION_HORAS, "24")
    assert config.sesion_horas() == 24
    limpio.setenv(config.ENV_SESION_HORAS, "0")
    assert config.sesion_horas() == 12  # <=0 cae al default
    limpio.setenv(config.ENV_SESION_HORAS, "no")
    assert config.sesion_horas() == 12


def test_claude_timeout(limpio):
    limpio.setenv(config.ENV_CLAUDE_TIMEOUT, "30")
    assert config.claude_timeout() == 30
    limpio.setenv(config.ENV_CLAUDE_TIMEOUT, "0")
    assert config.claude_timeout() == 600  # <=0 cae al default
    limpio.setenv(config.ENV_CLAUDE_TIMEOUT, "x")
    assert config.claude_timeout() == 600


def test_claude_max_usd(limpio):
    limpio.setenv(config.ENV_CLAUDE_MAX_USD, "0.50")
    assert config.claude_max_usd() == 0.5
    limpio.setenv(config.ENV_CLAUDE_MAX_USD, "0")
    assert config.claude_max_usd() is None  # <=0 = sin tope
    limpio.setenv(config.ENV_CLAUDE_MAX_USD, "no-num")
    assert config.claude_max_usd() is None


def test_claude_max_turns(limpio):
    limpio.setenv(config.ENV_CLAUDE_MAX_TURNS, "8")
    assert config.claude_max_turns() == 8
    limpio.setenv(config.ENV_CLAUDE_MAX_TURNS, "-3")
    assert config.claude_max_turns() is None
    limpio.setenv(config.ENV_CLAUDE_MAX_TURNS, "x")
    assert config.claude_max_turns() is None


def test_skills_max_subida_mb(limpio):
    limpio.setenv(config.ENV_SKILLS_MAX_SUBIDA_MB, "5")
    assert config.skills_max_subida_mb() == 5
    limpio.setenv(config.ENV_SKILLS_MAX_SUBIDA_MB, "0")
    assert config.skills_max_subida_mb() is None
    limpio.setenv(config.ENV_SKILLS_MAX_SUBIDA_MB, "x")
    assert config.skills_max_subida_mb() is None


# --------------------------------------------------------------------------- #
# Flags afirmativos/negativos                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("valor", ["1", "true", "yes", "si", "sí", "on", "TRUE", "On"])
def test_flag_https_afirmativo(limpio, valor):
    limpio.setenv(config.ENV_HTTPS, valor)
    assert config.flag_https() is True


@pytest.mark.parametrize("valor", ["0", "false", "no", "off", ""])
def test_flag_https_negativo(limpio, valor):
    limpio.setenv(config.ENV_HTTPS, valor)
    assert config.flag_https() is False


def test_cookie_secure_precedencia(limpio):
    """`COOKIE_SECURE` explicito > derivado de `HTTPS` > default False."""
    # default
    assert config.cookie_secure() is False
    # derivado de HTTPS
    limpio.setenv(config.ENV_HTTPS, "1")
    assert config.cookie_secure() is True
    # explicito gana sobre HTTPS (lo apaga)
    limpio.setenv(config.ENV_COOKIE_SECURE, "0")
    assert config.cookie_secure() is False
    # explicito gana sobre HTTPS (lo enciende)
    limpio.delenv(config.ENV_HTTPS, raising=False)
    limpio.setenv(config.ENV_COOKIE_SECURE, "1")
    assert config.cookie_secure() is True


@pytest.mark.parametrize("valor", ["0", "false", "no", "off", ""])
def test_claude_skip_permisos_apagado(limpio, valor):
    """Falsy apaga el skip de permisos; cualquier otro valor lo deja ON (default)."""
    limpio.setenv(config.ENV_CLAUDE_SKIP_PERMISSIONS, valor)
    assert config.claude_skip_permisos() is False


def test_claude_skip_permisos_encendido_por_defecto_y_con_valor(limpio):
    assert config.claude_skip_permisos() is True  # def ON
    limpio.setenv(config.ENV_CLAUDE_SKIP_PERMISSIONS, "1")
    assert config.claude_skip_permisos() is True


# --------------------------------------------------------------------------- #
# Strings (admin user/pass): strip vs no-strip                                 #
# --------------------------------------------------------------------------- #


def test_admin_user_strip_y_default(limpio):
    limpio.setenv(config.ENV_ADMIN_USER, "  jefa  ")
    assert config.admin_user() == "jefa"  # se recorta
    limpio.setenv(config.ENV_ADMIN_USER, "   ")
    assert config.admin_user() == "admin"  # vacio tras strip -> default


def test_admin_pass_conserva_espacios(limpio):
    """La contrasena NO se recorta (un espacio puede ser significativo)."""
    limpio.setenv(config.ENV_ADMIN_PASS, "  con espacios  ")
    assert config.admin_pass() == "  con espacios  "


# --------------------------------------------------------------------------- #
# Intervalos de los programadores en segundo plano                             #
# --------------------------------------------------------------------------- #


def test_comercial_intervalo_segundos_min_1(limpio):
    limpio.setenv(config.ENV_COMERCIAL_INTERVALO_SEGUNDOS, "0.5")
    assert config.comercial_intervalo_segundos() == 1.0  # clamp min 1.0
    limpio.setenv(config.ENV_COMERCIAL_INTERVALO_SEGUNDOS, "5")
    assert config.comercial_intervalo_segundos() == 5.0
    limpio.setenv(config.ENV_COMERCIAL_INTERVALO_SEGUNDOS, "x")
    assert config.comercial_intervalo_segundos() is None


def test_comercial_intervalo_horas_crudo(limpio):
    """Devuelve las HORAS crudas (>0); el clamp a 60 s lo hace el llamante."""
    limpio.setenv(config.ENV_COMERCIAL_INTERVALO_HORAS, "2")
    assert config.comercial_intervalo_horas() == 2.0
    limpio.setenv(config.ENV_COMERCIAL_INTERVALO_HORAS, "x")
    assert config.comercial_intervalo_horas() is None


def test_programador_intervalo_segundos_min_1(limpio):
    limpio.setenv(config.ENV_PROGRAMADOR_INTERVALO_SEGUNDOS, "0.1")
    assert config.programador_intervalo_segundos() == 1.0  # clamp min 1.0
    limpio.setenv(config.ENV_PROGRAMADOR_INTERVALO_SEGUNDOS, "30")
    assert config.programador_intervalo_segundos() == 30.0
    limpio.setenv(config.ENV_PROGRAMADOR_INTERVALO_SEGUNDOS, "x")
    assert config.programador_intervalo_segundos() is None


# --------------------------------------------------------------------------- #
# override_ruta: override especifico de cada recurso (maxima prioridad)        #
# --------------------------------------------------------------------------- #


def test_override_ruta_ausente_es_none(limpio):
    limpio.delenv(config.ENV_DB, raising=False)
    assert config.override_ruta(config.ENV_DB) is None


def test_override_ruta_expande_tilde(limpio, tmp_path):
    """El override de ruta expande `~` (consistente con todos los recursos)."""
    limpio.setenv(config.ENV_DB, "~/sub/consola.db")
    resuelto = config.override_ruta(config.ENV_DB)
    assert resuelto is not None
    assert "~" not in str(resuelto)
    assert resuelto.name == "consola.db"

    # Una ruta absoluta se respeta tal cual.
    abs_ruta = tmp_path / "x" / "consola.db"
    limpio.setenv(config.ENV_DB, str(abs_ruta))
    assert config.override_ruta(config.ENV_DB) == abs_ruta
