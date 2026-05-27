"""Configuracion CENTRAL de la Consola Keni: fuente UNICA de las env vars `KENI_*`.

Antes cada modulo leia sus `os.environ.get("KENI_...")` por su cuenta (~30 lecturas
dispersas), repitiendo el nombre de la var, su default y el parseo. Este modulo las
CENTRALIZA: declara cada nombre de variable UNA vez (constantes `ENV_*`) y expone un
accesor por variable que encapsula su default, su tipo y su precedencia. Los modulos
llaman al accesor en vez de tocar `os.environ` directamente.

POR QUE ACCESORES (y no constantes leidas al importar): la configuracion se lee SIEMPRE
en tiempo de LLAMADA, nunca al importar el modulo. Los tests aislan cada recurso con
`monkeypatch.setenv(...)` ANTES de invocar el codigo; si el valor se capturara al
importar, ese aislamiento no funcionaria. Por eso cada accesor hace su `os.environ.get`
al ser llamado.

QUE NO HACE (a proposito, para no cambiar comportamiento):
  - NO renombra ninguna `KENI_*` ni cambia defaults/precedencia: es centralizacion, no
    rename. Un deploy que ya fija las vars actuales sigue funcionando igual.
  - NO resuelve las RUTAS de estado: la PRECEDENCIA de rutas (var especifica del recurso
    > `KENI_DATA_DIR` > `${XDG_CONFIG_HOME:-~/.config}`) vive en `rutas.py`, que es el
    sitio historico de esa logica. Aqui solo se centraliza el NOMBRE de cada var de ruta
    (constante `ENV_*`) y el accesor del OVERRIDE especifico (`override_ruta`), que cada
    modulo de ruta usa como su override de maxima prioridad. `rutas.data_dir()` sigue
    siendo quien compone el fallback.

CATALOGO de variables (todas opcionales salvo que se diga). Agrupadas por area:

  Arranque / red (`__main__`):
    - KENI_CONSOLA_HOST            host de bind                       def 127.0.0.1
    - KENI_CONSOLA_PORT            puerto                             def 8765

  Auth / sesion / CSRF (`seguridad`, `auth`):
    - KENI_CONSOLA_TOKEN          token de sesion fijo               def (genera uno)
    - KENI_CONSOLA_COOKIE_SECURE  cookies Secure (flag)              def derivado de HTTPS
    - KENI_CONSOLA_HTTPS          vamos tras TLS (flag)              def off
    - KENI_CONSOLA_SESION_HORAS   duracion de sesion (horas)         def 12
    - KENI_CONSOLA_ADMIN_USER     usuario del admin de bootstrap     def "admin"
    - KENI_CONSOLA_ADMIN_PASS     contrasena del admin de bootstrap  def (genera una)

  Observabilidad (`observabilidad`):
    - KENI_CONSOLA_LOG_LEVEL      nivel de log                       def INFO

  Concurrencia de jobs (`dominio.runner`):
    - KENI_MAX_JOBS               jobs `claude` simultaneos          def 4   (min 1)
    - KENI_MAX_COLA               jobs esperando un slot             def 16  (min 0)

  Cola + worker de generacion (#130 Fase 2 / ADR 0002 Fase B; `cola`, `worker`):
    - KENI_WORKER_EXTERNO         hay un servicio `worker` aparte    def OFF (worker in-proceso)
    - KENI_WORKER_SONDEO_SEGUNDOS intervalo de sondeo de la cola (s) def 0.5  (min 0.05)

  Generacion `claude -p` (`generaciones`, `dominio.stream`):
    - KENI_CLAUDE_TIMEOUT         wall-timeout de un job (s)         def 600
    - KENI_CLAUDE_MAX_USD         tope de coste (--max-budget-usd)   def sin tope
    - KENI_CLAUDE_MAX_TURNS       tope de turnos (--max-turns)       def sin tope
    - KENI_CLAUDE_SKIP_PERMISSIONS  saltar permisos (--dangerously-skip-permissions)  def ON

  Skills (`dominio.skills`, `skills_catalogo`, `api.skills_generacion_api`):
    - KENI_SKILLS_CWD             raiz de DESCUBRIMIENTO de skills   def repo/plugin/cwd
    - KENI_SKILLS_EJECUCION_CWD   cwd de EJECUCION de `claude`       def derivado de cwd_skills
    - KENI_SKILLS_DIR             carpeta directa del catalogo       def <cwd>/skills-copy/...
    - KENI_SKILLS_MAX_SUBIDA_MB   limite de subida por skill (MB)    def por tipo

  Programadores en segundo plano (`comercial`, `programador`):
    - KENI_COMERCIAL_INTERVALO_SEGUNDOS  intervalo captura (s)       prioridad sobre horas
    - KENI_COMERCIAL_INTERVALO_HORAS     intervalo captura (h)       def INTERVALO_HORAS_DEF
    - KENI_PROGRAMADOR_INTERVALO_SEGUNDOS  intervalo barrido (s)     def INTERVALO_SEGUNDOS_DEF

  Imagen / secretos (`secretos`, `media`): la precedencia fichero>env vive en
  `secretos.py`; aqui se declaran solo los nombres (no hay accesor central porque el
  fichero de secretos participa en la decision):
    - KENI_IMAGEN_API_KEY, KENI_IMAGEN_PROVEEDOR  (+ OPENROUTER_API_KEY/OPENAI_API_KEY)

  Persistencia hosted (#130): Postgres y object storage S3/Garage. Si NO se fijan, el
  perfil LOCAL/privado sigue en SQLite + disco (ADR 0001/0002); si se fijan (el stack
  hosted las cablea en `deploy/`), `db.py`/`media.py` consumen Postgres/S3. Los NOMBRES
  son los que ya estan en `deploy/docker-compose.yml`/`.env.example` (no se renombran):
    - DATABASE_URL                URL Postgres del back            def (vacio = SQLite)
    - S3_ENDPOINT                 endpoint S3/Garage               (cablea S3 si presente)
    - S3_REGION                   region S3                        def garage
    - S3_BUCKET                   bucket de media                  def keni-media
    - S3_ACCESS_KEY / S3_SECRET_KEY  credenciales S3               (vacias = disco)

  Rutas de estado (override especifico de cada recurso; la composicion del fallback
  vive en `rutas.py`). Nombre centralizado aqui, valor leido via `override_ruta`:
    - KENI_DATA_DIR               raiz unica de estado (contenedor)  -> lo usa `rutas`
    - KENI_CONSOLA_RAIZ           contenido editorial por marca
    - KENI_CONSOLA_DB             consola.db (SQLite)
    - KENI_CONSOLA_TAREAS         tareas.json (migracion)
    - KENI_CONSOLA_INDICE         indice.sqlite (regenerable)
    - KENI_CONSOLA_MEDIA          dir de media (imagenes)
    - KENI_CONSOLA_SECRETOS       secretos.toml
    - KENI_CONSOLA_PREFERENCIAS   preferencias.toml
    - KENI_CONSOLA_SUGERENCIAS    sugerencias.json
    - KENI_CONSOLA_TERMOMETRO     termometro.json
    - KENI_CONSOLA_CONFIG         consola.toml (allowlist de proyectos)
    - KENI_CONSOLA_GENERACIONES   dir de registros de generacion
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Nombres de variable (fuente UNICA: el resto del codigo referencia estas      #
# constantes, no literales sueltos).                                           #
# --------------------------------------------------------------------------- #

# Arranque / red.
ENV_HOST = "KENI_CONSOLA_HOST"
ENV_PORT = "KENI_CONSOLA_PORT"

# Auth / sesion / CSRF.
ENV_TOKEN = "KENI_CONSOLA_TOKEN"
ENV_COOKIE_SECURE = "KENI_CONSOLA_COOKIE_SECURE"
ENV_HTTPS = "KENI_CONSOLA_HTTPS"
ENV_SESION_HORAS = "KENI_CONSOLA_SESION_HORAS"
ENV_ADMIN_USER = "KENI_CONSOLA_ADMIN_USER"
ENV_ADMIN_PASS = "KENI_CONSOLA_ADMIN_PASS"

# Observabilidad.
ENV_LOG_LEVEL = "KENI_CONSOLA_LOG_LEVEL"

# Concurrencia de jobs.
ENV_MAX_JOBS = "KENI_MAX_JOBS"
ENV_MAX_COLA = "KENI_MAX_COLA"

# Cola + worker de generacion (#130 Fase 2 / ADR 0002 Fase B).
ENV_WORKER_EXTERNO = "KENI_WORKER_EXTERNO"
ENV_WORKER_SONDEO_SEGUNDOS = "KENI_WORKER_SONDEO_SEGUNDOS"

# Generacion `claude -p`.
ENV_CLAUDE_TIMEOUT = "KENI_CLAUDE_TIMEOUT"
ENV_CLAUDE_MAX_USD = "KENI_CLAUDE_MAX_USD"
ENV_CLAUDE_MAX_TURNS = "KENI_CLAUDE_MAX_TURNS"
ENV_CLAUDE_SKIP_PERMISSIONS = "KENI_CLAUDE_SKIP_PERMISSIONS"

# Skills.
ENV_SKILLS_CWD = "KENI_SKILLS_CWD"
ENV_SKILLS_EJECUCION_CWD = "KENI_SKILLS_EJECUCION_CWD"
ENV_SKILLS_DIR = "KENI_SKILLS_DIR"
ENV_SKILLS_MAX_SUBIDA_MB = "KENI_SKILLS_MAX_SUBIDA_MB"

# Programadores en segundo plano.
ENV_COMERCIAL_INTERVALO_SEGUNDOS = "KENI_COMERCIAL_INTERVALO_SEGUNDOS"
ENV_COMERCIAL_INTERVALO_HORAS = "KENI_COMERCIAL_INTERVALO_HORAS"
ENV_PROGRAMADOR_INTERVALO_SEGUNDOS = "KENI_PROGRAMADOR_INTERVALO_SEGUNDOS"

# Imagen / secretos (precedencia con el fichero vive en `secretos.py`).
ENV_IMAGEN_API_KEY = "KENI_IMAGEN_API_KEY"
ENV_IMAGEN_PROVEEDOR = "KENI_IMAGEN_PROVEEDOR"

# Persistencia hosted (#130): Postgres + object storage S3/Garage. NOMBRES EXACTOS de
# `deploy/docker-compose.yml`/`.env.example` (NO se renombran). Sin fijar => perfil
# local/privado (SQLite + disco). Fijados => `db.py`/`media.py` consumen Postgres/S3.
ENV_DATABASE_URL = "DATABASE_URL"
ENV_S3_ENDPOINT = "S3_ENDPOINT"
ENV_S3_REGION = "S3_REGION"
ENV_S3_BUCKET = "S3_BUCKET"
ENV_S3_ACCESS_KEY = "S3_ACCESS_KEY"
ENV_S3_SECRET_KEY = "S3_SECRET_KEY"

# Rutas de estado (override especifico de cada recurso; fallback en `rutas.py`).
ENV_DATA_DIR = "KENI_DATA_DIR"
ENV_RAIZ = "KENI_CONSOLA_RAIZ"
ENV_DB = "KENI_CONSOLA_DB"
ENV_TAREAS = "KENI_CONSOLA_TAREAS"
ENV_INDICE = "KENI_CONSOLA_INDICE"
ENV_MEDIA = "KENI_CONSOLA_MEDIA"
ENV_SECRETOS = "KENI_CONSOLA_SECRETOS"
ENV_PREFERENCIAS = "KENI_CONSOLA_PREFERENCIAS"
ENV_SUGERENCIAS = "KENI_CONSOLA_SUGERENCIAS"
ENV_TERMOMETRO = "KENI_CONSOLA_TERMOMETRO"
ENV_CONFIG = "KENI_CONSOLA_CONFIG"
ENV_GENERACIONES = "KENI_CONSOLA_GENERACIONES"

# --------------------------------------------------------------------------- #
# Defaults (constantes; ANTES vivian dispersos en cada modulo).                #
# --------------------------------------------------------------------------- #

HOST_DEF = "127.0.0.1"
PORT_DEF = 8765
SESION_HORAS_DEF = 12
ADMIN_USER_DEF = "admin"
LOG_LEVEL_DEF = "INFO"
MAX_JOBS_DEF = 4
MAX_COLA_DEF = 16
CLAUDE_TIMEOUT_DEF = 600
# Cadencia de sondeo de la cola por el worker (s). Bajo para que el job arranque casi
# al instante tras encolarse (la UX de "Generar" no debe notar el desacoplo).
WORKER_SONDEO_SEGUNDOS_DEF = 0.5

# Defaults de object storage (coinciden con `deploy/.env.example`). El endpoint y las
# credenciales NO tienen default: su PRESENCIA es lo que decide usar S3 (vs disco).
S3_REGION_DEF = "garage"
S3_BUCKET_DEF = "keni-media"

# Conjuntos de verdad/falsedad para flags (mismos que usaban los modulos de origen).
_VERDADEROS = frozenset({"1", "true", "yes", "si", "sí", "on"})
_FALSOS = frozenset({"0", "false", "no", "off", ""})


# --------------------------------------------------------------------------- #
# Helpers de lectura/parseo (tolerantes, como en los modulos de origen).       #
# --------------------------------------------------------------------------- #


def _crudo(nombre: str) -> str:
    """Valor crudo (str) de una env var, sin espacios; "" si no esta."""
    return (os.environ.get(nombre) or "").strip()


def _entero(nombre: str, defecto: int, *, minimo: int | None = None) -> int:
    """Entero de una env var; `defecto` si falta o no parsea. Aplica `minimo` si se da."""
    crudo = _crudo(nombre)
    if not crudo:
        return defecto
    try:
        valor = int(crudo)
    except ValueError:
        return defecto
    if minimo is not None:
        return max(minimo, valor)
    return valor


# --------------------------------------------------------------------------- #
# Accesores: arranque / red                                                    #
# --------------------------------------------------------------------------- #


def host() -> str:
    """Host de bind del servidor (`KENI_CONSOLA_HOST`, def 127.0.0.1)."""
    return os.environ.get(ENV_HOST, HOST_DEF)


def port() -> int:
    """Puerto del servidor (`KENI_CONSOLA_PORT`, def 8765); valor invalido -> def."""
    crudo = os.environ.get(ENV_PORT, str(PORT_DEF))
    try:
        return int(crudo)
    except ValueError:
        return PORT_DEF


# --------------------------------------------------------------------------- #
# Accesores: auth / sesion / CSRF                                              #
# --------------------------------------------------------------------------- #


def token() -> str | None:
    """Token de sesion fijado por `KENI_CONSOLA_TOKEN` (None si no esta; vacio = no fijado)."""
    return _crudo(ENV_TOKEN) or None


def flag_https() -> bool:
    """True si `KENI_CONSOLA_HTTPS` esta a un valor afirmativo (estamos tras TLS)."""
    return _crudo(ENV_HTTPS).lower() in _VERDADEROS


def cookie_secure() -> bool:
    """¿Cookies `Secure`? `KENI_CONSOLA_COOKIE_SECURE` manda; si no se fija, deriva de HTTPS."""
    crudo = _crudo(ENV_COOKIE_SECURE)
    if crudo:
        return crudo.lower() in _VERDADEROS
    return flag_https()


def sesion_horas() -> int:
    """Duracion de la sesion en horas (`KENI_CONSOLA_SESION_HORAS`, def 12; >0)."""
    horas = _entero(ENV_SESION_HORAS, SESION_HORAS_DEF)
    return horas if horas > 0 else SESION_HORAS_DEF


def admin_user() -> str:
    """Usuario del admin de bootstrap (`KENI_CONSOLA_ADMIN_USER`, def "admin")."""
    return _crudo(ENV_ADMIN_USER) or ADMIN_USER_DEF


def admin_pass() -> str:
    """Contrasena del admin de bootstrap (`KENI_CONSOLA_ADMIN_PASS`, "" si no esta)."""
    # SIN strip: una contrasena puede llevar espacios significativos a proposito.
    return os.environ.get(ENV_ADMIN_PASS, "")


# --------------------------------------------------------------------------- #
# Accesores: observabilidad                                                    #
# --------------------------------------------------------------------------- #


def log_level() -> str:
    """Nivel de log crudo en mayusculas (`KENI_CONSOLA_LOG_LEVEL`, def INFO).

    Devuelve el NOMBRE (DEBUG/INFO/...); el modulo de observabilidad lo mapea a un int y
    cae a INFO si no es valido (no se valida aqui para no acoplar a `logging`).
    """
    return os.environ.get(ENV_LOG_LEVEL, LOG_LEVEL_DEF).strip().upper()


# --------------------------------------------------------------------------- #
# Accesores: concurrencia de jobs                                              #
# --------------------------------------------------------------------------- #


def max_jobs() -> int:
    """Maximo de jobs `claude` simultaneos (`KENI_MAX_JOBS`, def 4, minimo 1)."""
    return _entero(ENV_MAX_JOBS, MAX_JOBS_DEF, minimo=1)


def max_cola() -> int:
    """Maximo de jobs ESPERANDO un slot (`KENI_MAX_COLA`, def 16, minimo 0)."""
    return _entero(ENV_MAX_COLA, MAX_COLA_DEF, minimo=0)


# --------------------------------------------------------------------------- #
# Accesores: cola + worker de generacion (#130 Fase 2 / ADR 0002 Fase B)       #
# --------------------------------------------------------------------------- #
#
# DOS modos de ejecucion del worker que consume la cola de generacion:
#   - LOCAL / un solo proceso (def): el back arranca el worker EN PROCESO (hilo de
#     fondo). La UX de una sola maquina no cambia: no hace falta un servicio aparte y
#     `claude` esta en el mismo entorno.
#   - HOSTED: un servicio `worker` SEPARADO consume la misma cola. Se activa con
#     `KENI_WORKER_EXTERNO` afirmativo en el back (asi NO arranca su worker in-proceso) y
#     el contenedor `worker` corre `python -m keni_consola.worker` (que SI tiene `claude`).


def worker_externo() -> bool:
    """True si hay un servicio `worker` SEPARADO (hosted) que consume la cola.

    `KENI_WORKER_EXTERNO` afirmativo => el back NO arranca su worker in-proceso (lo hace
    el contenedor `worker`). Def OFF: el back arranca el worker in-proceso (perfil local /
    un solo proceso), preservando la UX de una sola maquina sin servicio aparte.
    """
    return _crudo(ENV_WORKER_EXTERNO).lower() in _VERDADEROS


def worker_sondeo_segundos() -> float:
    """Intervalo de sondeo de la cola por el worker (`KENI_WORKER_SONDEO_SEGUNDOS`, def 0.5, min 0.05)."""
    crudo = _crudo(ENV_WORKER_SONDEO_SEGUNDOS)
    if not crudo:
        return WORKER_SONDEO_SEGUNDOS_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return WORKER_SONDEO_SEGUNDOS_DEF
    return max(0.05, valor)


# --------------------------------------------------------------------------- #
# Accesores: generacion `claude -p`                                            #
# --------------------------------------------------------------------------- #


def claude_timeout() -> int:
    """Wall-timeout (s) de un job de claude (`KENI_CLAUDE_TIMEOUT`, def 600; >0)."""
    crudo = _crudo(ENV_CLAUDE_TIMEOUT)
    if crudo:
        try:
            valor = int(crudo)
        except ValueError:
            return CLAUDE_TIMEOUT_DEF
        if valor > 0:
            return valor
    return CLAUDE_TIMEOUT_DEF


def claude_max_usd() -> float | None:
    """Tope de coste en USD (`KENI_CLAUDE_MAX_USD`); None si ausente/invalido/<=0 (sin tope)."""
    crudo = _crudo(ENV_CLAUDE_MAX_USD)
    if not crudo:
        return None
    try:
        valor = float(crudo)
    except ValueError:
        return None
    return valor if valor > 0 else None


def claude_max_turns() -> int | None:
    """Tope de turnos (`KENI_CLAUDE_MAX_TURNS`); None si ausente/invalido/<=0 (sin tope)."""
    crudo = _crudo(ENV_CLAUDE_MAX_TURNS)
    if not crudo:
        return None
    try:
        valor = int(crudo)
    except ValueError:
        return None
    return valor if valor > 0 else None


def claude_skip_permisos() -> bool:
    """¿Pasar `--dangerously-skip-permissions`? (def ON; `KENI_CLAUDE_SKIP_PERMISSIONS` falsy lo apaga)."""
    crudo = os.environ.get(ENV_CLAUDE_SKIP_PERMISSIONS, "1").strip().lower()
    return crudo not in _FALSOS


# --------------------------------------------------------------------------- #
# Accesores: skills                                                            #
# --------------------------------------------------------------------------- #


def skills_cwd() -> str | None:
    """Override de la raiz de DESCUBRIMIENTO de skills (`KENI_SKILLS_CWD`); None si no esta."""
    return os.environ.get(ENV_SKILLS_CWD) or None


def skills_ejecucion_cwd() -> str | None:
    """Override del cwd de EJECUCION de `claude` (`KENI_SKILLS_EJECUCION_CWD`); None si no esta."""
    return os.environ.get(ENV_SKILLS_EJECUCION_CWD) or None


def skills_dir() -> str | None:
    """Override de la carpeta directa del catalogo de skills (`KENI_SKILLS_DIR`); None si no esta."""
    return os.environ.get(ENV_SKILLS_DIR) or None


def skills_max_subida_mb() -> int | None:
    """Limite de subida por skill en MB (`KENI_SKILLS_MAX_SUBIDA_MB`); None si ausente/invalido/<=0."""
    crudo = os.environ.get(ENV_SKILLS_MAX_SUBIDA_MB)
    if not crudo:
        return None
    try:
        mb = int(crudo)
    except ValueError:
        return None
    return mb if mb > 0 else None


# --------------------------------------------------------------------------- #
# Accesores: programadores en segundo plano                                    #
# --------------------------------------------------------------------------- #


def comercial_intervalo_segundos() -> float | None:
    """Intervalo de la captura comercial en s (`KENI_COMERCIAL_INTERVALO_SEGUNDOS`, min 1.0).

    None si ausente/invalido (el llamante cae a horas/def). Tiene PRIORIDAD sobre horas.
    """
    crudo = os.environ.get(ENV_COMERCIAL_INTERVALO_SEGUNDOS)
    if not crudo:
        return None
    try:
        return max(1.0, float(crudo))
    except ValueError:
        return None


def comercial_intervalo_horas() -> float | None:
    """Intervalo de la captura comercial en HORAS (`KENI_COMERCIAL_INTERVALO_HORAS`).

    Devuelve las horas crudas (float, >0); None si ausente/invalido. El minimo de 60 s lo
    aplica el llamante al convertir a segundos (comportamiento historico).
    """
    crudo = os.environ.get(ENV_COMERCIAL_INTERVALO_HORAS)
    if not crudo:
        return None
    try:
        return float(crudo)
    except ValueError:
        return None


def programador_intervalo_segundos() -> float | None:
    """Intervalo del barrido del programador en s (`KENI_PROGRAMADOR_INTERVALO_SEGUNDOS`, min 1.0).

    None si ausente/invalido (el llamante cae al default del modulo).
    """
    crudo = os.environ.get(ENV_PROGRAMADOR_INTERVALO_SEGUNDOS)
    if not crudo:
        return None
    try:
        return max(1.0, float(crudo))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Accesores: persistencia hosted (Postgres + object storage S3/Garage, #130)   #
# --------------------------------------------------------------------------- #
#
# La PRESENCIA de la variable es el conmutador de backend (perfil local/privado vs
# hosted): sin `DATABASE_URL` -> SQLite; sin endpoint+credenciales S3 -> disco. No se
# rompe el modo local (ADR 0001/0002) porque el default de cada accesor es "ausente".


def database_url() -> str | None:
    """URL de Postgres del back (`DATABASE_URL`); None si no esta (=> SQLite local).

    Es el CONMUTADOR de backend de `db.py`: si hay URL, la persistencia operacional
    (tareas/comercial/rota/usuarios/sesiones) va a Postgres; si no, sigue en SQLite.
    """
    return _crudo(ENV_DATABASE_URL) or None


def s3_endpoint() -> str | None:
    """Endpoint S3/Garage (`S3_ENDPOINT`); None si no esta."""
    return _crudo(ENV_S3_ENDPOINT) or None


def s3_region() -> str:
    """Region S3 (`S3_REGION`, def `garage`)."""
    return _crudo(ENV_S3_REGION) or S3_REGION_DEF


def s3_bucket() -> str:
    """Bucket de media S3 (`S3_BUCKET`, def `keni-media`)."""
    return _crudo(ENV_S3_BUCKET) or S3_BUCKET_DEF


def s3_access_key() -> str | None:
    """Access key S3 (`S3_ACCESS_KEY`); None si no esta."""
    return _crudo(ENV_S3_ACCESS_KEY) or None


def s3_secret_key() -> str | None:
    """Secret key S3 (`S3_SECRET_KEY`); None si no esta. SIN strip: puede ser sensible.

    A diferencia del resto, NO recortamos: una clave S3 puede (en teoria) llevar
    espacios significativos. Devuelve None solo si la var no esta o esta vacia.
    """
    valor = os.environ.get(ENV_S3_SECRET_KEY)
    return valor if valor else None


def s3_configurado() -> bool:
    """True si HAY object storage S3 cableado (endpoint + ambas credenciales).

    Es el conmutador de `media.py`: con S3 cableado, la media va al bucket; si no
    (perfil local/privado), sigue en disco. Exige endpoint y AMBAS credenciales para
    no intentar hablar S3 a medio configurar.
    """
    return bool(s3_endpoint() and s3_access_key() and s3_secret_key())


# --------------------------------------------------------------------------- #
# Accesor: override de RUTA especifica de un recurso                           #
# --------------------------------------------------------------------------- #


def override_ruta(nombre: str) -> Path | None:
    """Override de ruta especifico de un recurso (`KENI_CONSOLA_*` de estado).

    Es el override de MAXIMA prioridad de cada modulo de ruta (db, indice, media, ...):
    si la var esta puesta, se usa tal cual (expandiendo `~`). Si no, el modulo cae a
    `rutas.dir_config()`/`rutas.raiz_proyectos()`, que componen el fallback
    `KENI_DATA_DIR` > `${XDG_CONFIG_HOME:-~/.config}`.

    `nombre` es una de las constantes `ENV_*` de ruta de este modulo (p.ej. `ENV_DB`).
    """
    crudo = os.environ.get(nombre)
    if crudo:
        return Path(crudo).expanduser()
    return None
