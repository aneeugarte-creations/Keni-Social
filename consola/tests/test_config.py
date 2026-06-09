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
    config.ENV_MAQUINA,
    config.ENV_HOST,
    config.ENV_PORT,
    config.ENV_TOKEN,
    config.ENV_ORIGENES,
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
    config.ENV_COMERCIAL_INTERVALO_SEGUNDOS,
    config.ENV_COMERCIAL_INTERVALO_HORAS,
    config.ENV_PROGRAMADOR_INTERVALO_SEGUNDOS,
    config.ENV_DATABASE_URL,
    config.ENV_PG_USER,
    config.ENV_PG_PASSWORD,
    config.ENV_PG_DB,
    config.ENV_PG_HOST,
    config.ENV_PG_PORT,
    config.ENV_S3_ENDPOINT,
    config.ENV_S3_REGION,
    config.ENV_S3_BUCKET,
    config.ENV_S3_ACCESS_KEY,
    config.ENV_S3_SECRET_KEY,
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
    assert config.ENV_ORIGENES == "KENI_CONSOLA_ORIGENES"
    assert config.ENV_SESION_HORAS == "KENI_CONSOLA_SESION_HORAS"
    assert config.ENV_ADMIN_USER == "KENI_CONSOLA_ADMIN_USER"
    assert config.ENV_ADMIN_PASS == "KENI_CONSOLA_ADMIN_PASS"
    assert config.ENV_MAX_JOBS == "KENI_MAX_JOBS"
    assert config.ENV_MAX_COLA == "KENI_MAX_COLA"
    assert config.ENV_CLAUDE_TIMEOUT == "KENI_CLAUDE_TIMEOUT"
    assert config.ENV_CLAUDE_MAX_USD == "KENI_CLAUDE_MAX_USD"
    assert config.ENV_CLAUDE_MAX_TURNS == "KENI_CLAUDE_MAX_TURNS"
    assert config.ENV_CLAUDE_SKIP_PERMISSIONS == "KENI_CLAUDE_SKIP_PERMISSIONS"
    assert config.ENV_DATA_DIR == "KENI_DATA_DIR"
    assert config.ENV_GENERACIONES == "KENI_CONSOLA_GENERACIONES"
    # Persistencia hosted (#130): NOMBRES EXACTOS de deploy/.env.example (no se renombran).
    assert config.ENV_DATABASE_URL == "DATABASE_URL"
    assert config.ENV_PG_USER == "POSTGRES_USER"
    assert config.ENV_PG_PASSWORD == "POSTGRES_PASSWORD"
    assert config.ENV_PG_DB == "POSTGRES_DB"
    assert config.ENV_PG_HOST == "POSTGRES_HOST"
    assert config.ENV_PG_PORT == "POSTGRES_PORT"
    assert config.ENV_S3_ENDPOINT == "S3_ENDPOINT"
    assert config.ENV_S3_REGION == "S3_REGION"
    assert config.ENV_S3_BUCKET == "S3_BUCKET"
    assert config.ENV_S3_ACCESS_KEY == "S3_ACCESS_KEY"
    assert config.ENV_S3_SECRET_KEY == "S3_SECRET_KEY"


# --------------------------------------------------------------------------- #
# Persistencia hosted: DATABASE_URL + S3_* (#130)                              #
# --------------------------------------------------------------------------- #


def test_database_url_ausente_es_none(limpio):
    assert config.database_url() is None


def test_database_url_presente(limpio, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/keni")
    assert config.database_url() == "postgresql://u:p@db:5432/keni"


def test_database_url_vacia_es_none(limpio, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")
    assert config.database_url() is None


def test_database_url_explicita_gana_a_postgres(limpio, monkeypatch):
    """Una DATABASE_URL explicita es OVERRIDE: se devuelve tal cual aunque haya POSTGRES_*."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@externo:5432/keni")
    monkeypatch.setenv("POSTGRES_USER", "keni")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secreta")
    monkeypatch.setenv("POSTGRES_DB", "keni_social")
    assert config.database_url() == "postgresql://u:p@externo:5432/keni"


def test_database_url_derivada_de_postgres_con_password_especial(limpio, monkeypatch):
    """Sin DATABASE_URL, se DERIVA de POSTGRES_*; la password se %-codifica (anti-drift).

    Una password base64 puede llevar `+`/`/`/`=`, que romperian el parseo de la URL: se
    %-codifican (`a+b/c=d` -> `a%2Bb%2Fc%3Dd`). Host default `db`, port default `5432`.
    """
    monkeypatch.setenv("POSTGRES_USER", "keni")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a+b/c=d")
    monkeypatch.setenv("POSTGRES_DB", "keni_social")
    assert (
        config.database_url()
        == "postgresql://keni:a%2Bb%2Fc%3Dd@db:5432/keni_social"
    )


def test_database_url_derivada_respeta_host_y_port(limpio, monkeypatch):
    """POSTGRES_HOST/PORT, si estan, sustituyen los defaults `db`/`5432`."""
    monkeypatch.setenv("POSTGRES_USER", "keni")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secreta")
    monkeypatch.setenv("POSTGRES_DB", "keni_social")
    monkeypatch.setenv("POSTGRES_HOST", "pg.interno")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    assert (
        config.database_url()
        == "postgresql://keni:secreta@pg.interno:6543/keni_social"
    )


def test_database_url_postgres_incompleto_es_none(limpio, monkeypatch):
    """Faltando cualquier componente requerido (user/pass/db) NO se deriva: None (SQLite)."""
    monkeypatch.setenv("POSTGRES_USER", "keni")
    monkeypatch.setenv("POSTGRES_DB", "keni_social")  # falta POSTGRES_PASSWORD
    assert config.database_url() is None


def test_s3_defaults(limpio):
    assert config.s3_endpoint() is None
    assert config.s3_access_key() is None
    assert config.s3_secret_key() is None
    assert config.s3_region() == "garage"
    assert config.s3_bucket() == "keni-media"
    assert config.s3_configurado() is False


def test_s3_configurado_exige_endpoint_y_credenciales(limpio, monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT", "http://files:3900")
    assert config.s3_configurado() is False  # faltan credenciales
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    assert config.s3_configurado() is False  # falta el secret
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    assert config.s3_configurado() is True


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


# --------------------------------------------------------------------------- #
# origenes_permitidos(): allowlist CSRF detras de proxy (#130)                 #
# --------------------------------------------------------------------------- #


def test_origenes_permitidos_default_vacio(limpio):
    """Sin `KENI_CONSOLA_ORIGENES`, la allowlist esta vacia (modo local)."""
    assert config.origenes_permitidos() == frozenset()


def test_origenes_permitidos_acepta_origen_completo_y_host(limpio):
    """Acepta tanto un origen con esquema como un host pelado; normaliza a host[:puerto]."""
    limpio.setenv(config.ENV_ORIGENES, "https://social.kenitech.io, otro.example:8443")
    assert config.origenes_permitidos() == frozenset({"social.kenitech.io", "otro.example:8443"})


def test_origenes_permitidos_normaliza_mayusculas_y_descarta_ruido(limpio):
    """Minusculiza, ignora items vacios y descarta la ruta de un origen con path."""
    limpio.setenv(config.ENV_ORIGENES, " HTTPS://Social.Kenitech.IO/app , , ")
    assert config.origenes_permitidos() == frozenset({"social.kenitech.io"})


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


def test_pipeline_admision_default_y_clamp(limpio):
    """Los DOS knobs de admisión del flujo continuo: ajustables por env, default y clamp min 1.

    Los topes por etapa (QA/Copy/autogen/revisar) y el intervalo del barrido YA NO EXISTEN:
    el volumen lo regula la admisión (estos dos) + el backpressure de la cola.
    """
    assert config.pipeline_max() == 3
    assert config.pipeline_en_vuelo_max() == 8
    limpio.setenv(config.ENV_PIPELINE_EN_VUELO_MAX, "12")
    assert config.pipeline_en_vuelo_max() == 12
    limpio.setenv(config.ENV_PIPELINE_MAX, "5")
    assert config.pipeline_max() == 5
    # Clamp min 1 (un 0/negativo no apaga la admisión).
    limpio.setenv(config.ENV_PIPELINE_EN_VUELO_MAX, "0")
    assert config.pipeline_en_vuelo_max() == 1
    limpio.setenv(config.ENV_PIPELINE_MAX, "-3")
    assert config.pipeline_max() == 1


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
    limpio.delenv(config.ENV_INDICE, raising=False)
    assert config.override_ruta(config.ENV_INDICE) is None


def test_override_ruta_expande_tilde(limpio, tmp_path):
    """El override de ruta expande `~` (consistente con todos los recursos)."""
    limpio.setenv(config.ENV_INDICE, "~/sub/indice.sqlite")
    resuelto = config.override_ruta(config.ENV_INDICE)
    assert resuelto is not None
    assert "~" not in str(resuelto)
    assert resuelto.name == "indice.sqlite"

    # Una ruta absoluta se respeta tal cual.
    abs_ruta = tmp_path / "x" / "indice.sqlite"
    limpio.setenv(config.ENV_INDICE, str(abs_ruta))
    assert config.override_ruta(config.ENV_INDICE) == abs_ruta


# --------------------------------------------------------------------------- #
# Interruptor GENERAL de la maquina de contenido (kill-switch global)          #
# --------------------------------------------------------------------------- #


@pytest.fixture
def store_aislado(monkeypatch, tmp_path):
    """Aisla el store de ajustes en tmp (vacio) para que `_crudo` lea solo de env/defecto."""
    from keni_consola import ajustes

    ruta = tmp_path / "ajustes.toml"
    monkeypatch.setenv(config.ENV_AJUSTES, str(ruta))
    ajustes._CACHE_RUTA = None
    ajustes._CACHE_MTIME = -1.0
    ajustes._CACHE_DATOS = {}
    return monkeypatch


def test_maquina_activa_default_off(limpio, store_aislado):
    """Sin `KENI_MAQUINA` (ni en store ni en env), la maquina esta APAGADA por defecto."""
    assert config.maquina_activa() is False


@pytest.mark.parametrize("valor", ["1", "true", "on", "si", "sí", "yes"])
def test_maquina_activa_afirmativo(limpio, store_aislado, valor):
    store_aislado.setenv(config.ENV_MAQUINA, valor)
    assert config.maquina_activa() is True


@pytest.mark.parametrize("valor", ["0", "false", "off", "no", ""])
def test_maquina_activa_negativo(limpio, store_aislado, valor):
    store_aislado.setenv(config.ENV_MAQUINA, valor)
    assert config.maquina_activa() is False


def test_gate_maquina_off_anula_el_toggle_interno(limpio, store_aislado):
    """Con la maquina APAGADA, el gate devuelve False aunque el accesor interno sea True."""
    gateado = config.gate_maquina(lambda: True)
    assert gateado() is False


def test_gate_maquina_on_respeta_el_toggle_interno(limpio, store_aislado):
    """Con la maquina ENCENDIDA, el gate devuelve EXACTAMENTE el valor del accesor interno."""
    store_aislado.setenv(config.ENV_MAQUINA, "1")
    assert config.gate_maquina(lambda: True)() is True
    assert config.gate_maquina(lambda: False)() is False


def test_gate_maquina_no_cambia_la_semantica_del_accesor(limpio, store_aislado):
    """El accesor interno (p.ej. `ingesta_activa`) conserva su semantica; solo el gate ANDea.

    Con su propio flag ON pero la maquina apagada (default), el accesor sigue True pero el
    gate efectivo es False: nada corre hasta encender el interruptor general.
    """
    store_aislado.setenv(config.ENV_PIPELINE_SELECCION, "1")
    assert config.ingesta_activa() is True  # semantica intacta
    assert config.gate_maquina(config.ingesta_activa)() is False  # maquina off -> no corre
    store_aislado.setenv(config.ENV_MAQUINA, "1")
    assert config.gate_maquina(config.ingesta_activa)() is True  # maquina on -> sigue su toggle


# --------------------------------------------------------------------------- #
# Etapa QA (toggle propio `KENI_PIPELINE_VALIDACION`) + barrido por "cualquier etapa activa"     #
# --------------------------------------------------------------------------- #


def test_qa_activo_default_off(limpio, store_aislado):
    """Sin `KENI_PIPELINE_VALIDACION`, la etapa de QA está APAGADA por defecto (kill-switch, como las demás)."""
    assert config.qa_activo() is False


@pytest.mark.parametrize("valor", ["1", "true", "on", "si", "yes"])
def test_qa_activo_afirmativo(limpio, store_aislado, valor):
    store_aislado.setenv(config.ENV_PIPELINE_VALIDACION, valor)
    assert config.qa_activo() is True


def test_alguna_etapa_pipeline_activa_or_de_las_cuatro(limpio, store_aislado):
    """El barrido del daemon corre si CUALQUIER etapa (Noticias/QA/Copy/Arte) está activa."""
    assert config.alguna_etapa_pipeline_activa() is False  # todas off por defecto
    for env in (
        config.ENV_PIPELINE_SELECCION, config.ENV_PIPELINE_VALIDACION,
        config.ENV_PIPELINE_COPY, config.ENV_PIPELINE_ARTE,
    ):
        store_aislado.setenv(env, "1")
        assert config.alguna_etapa_pipeline_activa() is True
        store_aislado.delenv(env, raising=False)
    assert config.alguna_etapa_pipeline_activa() is False  # de nuevo todas off


# --------------------------------------------------------------------------- #
# Secretos basados en FICHERO (`*_FILE`, convencion Docker secrets).            #
# El valor vive en /run/secrets/... (un fichero), NO en la env del contenedor, #
# asi no aparece en `docker inspect`. La env directa, si esta, MANDA (aditivo). #
# --------------------------------------------------------------------------- #


class TestSecretosFichero:
    def test_database_url_lee_password_de_fichero(self, limpio, store_aislado, tmp_path):
        """Sin POSTGRES_PASSWORD en env, la password se lee de POSTGRES_PASSWORD_FILE."""
        p = tmp_path / "pg_pass"
        p.write_text("secreta-de-fichero", encoding="utf-8")
        store_aislado.setenv("POSTGRES_PASSWORD_FILE", str(p))
        store_aislado.setenv("POSTGRES_USER", "keni")
        store_aislado.setenv("POSTGRES_DB", "keni_social")
        dsn = config.database_url()
        assert dsn == "postgresql://keni:secreta-de-fichero@db:5432/keni_social"

    def test_env_gana_al_fichero(self, limpio, store_aislado, tmp_path):
        """Con ambos presentes, el valor de la env directa gana al del fichero."""
        p = tmp_path / "pg_pass"
        p.write_text("la-del-fichero", encoding="utf-8")
        store_aislado.setenv("POSTGRES_PASSWORD_FILE", str(p))
        store_aislado.setenv("POSTGRES_PASSWORD", "la-de-la-env")
        store_aislado.setenv("POSTGRES_USER", "keni")
        store_aislado.setenv("POSTGRES_DB", "keni_social")
        dsn = config.database_url()
        assert dsn == "postgresql://keni:la-de-la-env@db:5432/keni_social"

    def test_s3_secret_key_de_fichero_preserva_espacio_final(
        self, limpio, store_aislado, tmp_path
    ):
        """SIN strip de espacios significativos; solo se quita el salto de linea final."""
        p = tmp_path / "s3_secret"
        p.write_text("clave-con-espacio \n", encoding="utf-8")
        store_aislado.setenv("S3_SECRET_KEY_FILE", str(p))
        assert config.s3_secret_key() == "clave-con-espacio "

    def test_admin_pass_de_fichero_preserva_espacio_final(
        self, limpio, store_aislado, tmp_path
    ):
        """admin_pass tampoco recorta espacios; solo el `\\n` artefacto del fichero."""
        p = tmp_path / "admin_pass"
        p.write_text("contrasena con espacio \n", encoding="utf-8")
        store_aislado.setenv("KENI_CONSOLA_ADMIN_PASS_FILE", str(p))
        assert config.admin_pass() == "contrasena con espacio "

    def test_admin_pass_env_gana_al_fichero(self, limpio, store_aislado, tmp_path):
        p = tmp_path / "admin_pass"
        p.write_text("la-del-fichero", encoding="utf-8")
        store_aislado.setenv("KENI_CONSOLA_ADMIN_PASS_FILE", str(p))
        store_aislado.setenv("KENI_CONSOLA_ADMIN_PASS", "la-de-la-env")
        assert config.admin_pass() == "la-de-la-env"

    def test_fichero_inexistente_es_como_ausente(self, limpio, store_aislado, tmp_path):
        """Un `_FILE` que apunta a un fichero que no existe se ignora (cae al defecto)."""
        store_aislado.setenv("S3_SECRET_KEY_FILE", str(tmp_path / "no-existe"))
        assert config.s3_secret_key() is None

    def test_fichero_vacio_es_como_ausente(self, limpio, store_aislado, tmp_path):
        """Un fichero vacio (o solo `\\n`) se trata como ausente (None / "")."""
        p = tmp_path / "vacio"
        p.write_text("\n", encoding="utf-8")
        store_aislado.setenv("S3_SECRET_KEY_FILE", str(p))
        store_aislado.setenv("KENI_CONSOLA_ADMIN_PASS_FILE", str(p))
        assert config.s3_secret_key() is None
        assert config.admin_pass() == ""
