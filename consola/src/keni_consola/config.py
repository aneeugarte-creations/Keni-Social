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
    - KENI_CONSOLA_TOKEN          token interino OPCIONAL (gate extra) def (modo local genera uno)
    - KENI_CONSOLA_ORIGENES       hosts externos permitidos (CSRF tras proxy) def (solo el Host)
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
    - KENI_METRICAS_REFRESCO_HORAS       refresco cache metricas (h) def 4   (min 1)

  Imagen / secretos (`secretos`, `media`): la precedencia fichero>env vive en
  `secretos.py`; aqui se declaran solo los nombres (no hay accesor central porque el
  fichero de secretos participa en la decision):
    - KENI_IMAGEN_API_KEY, KENI_IMAGEN_PROVEEDOR  (+ OPENROUTER_API_KEY/OPENAI_API_KEY)

  Persistencia (#130 / ADR 0004): la operacional (tareas/comercial/rota/usuarios/sesiones/
  jobs) va SIEMPRE a Postgres -> `DATABASE_URL` es OBLIGATORIA (local o hosted). La media va
  a object storage S3/Garage si se cablean las `S3_*`; si no, sigue en disco. Los NOMBRES
  son los que ya estan en `deploy/docker-compose.yml`/`.env.example` (no se renombran):
    - DATABASE_URL                URL Postgres del back            OBLIGATORIA (ADR 0004)
    - S3_ENDPOINT                 endpoint S3/Garage               (cablea S3 si presente)
    - S3_REGION                   region S3                        def garage
    - S3_BUCKET                   bucket de media                  def keni-media
    - S3_ACCESS_KEY / S3_SECRET_KEY  credenciales S3               (vacias = disco)

  Rutas de estado (override especifico de cada recurso; la composicion del fallback
  vive en `rutas.py`). Nombre centralizado aqui, valor leido via `override_ruta`:
    - KENI_DATA_DIR               raiz unica de estado (contenedor)  -> lo usa `rutas`
    - KENI_CONSOLA_RAIZ           contenido editorial por marca
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
from urllib.parse import quote

# --------------------------------------------------------------------------- #
# Nombres de variable (fuente UNICA: el resto del codigo referencia estas      #
# constantes, no literales sueltos).                                           #
# --------------------------------------------------------------------------- #

# Arranque / red.
ENV_HOST = "KENI_CONSOLA_HOST"
ENV_PORT = "KENI_CONSOLA_PORT"

# Auth / sesion / CSRF.
ENV_TOKEN = "KENI_CONSOLA_TOKEN"
# Origenes/hosts externos permitidos para la verificacion CSRF de mutaciones detras de
# un reverse-proxy (Traefik). Lista separada por comas; cada item puede ser un origen
# completo (`https://social.kenitech.io`) o solo el host[:puerto] (`social.kenitech.io`).
ENV_ORIGENES = "KENI_CONSOLA_ORIGENES"
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
ENV_METRICAS_REFRESCO_HORAS = "KENI_METRICAS_REFRESCO_HORAS"

# Publicacion real via Metricool (gate de seguridad; def OFF = dry-run).
# `KENI_PUBLICAR_REAL=1` activa el posteo real al scheduler de Metricool en el
# barrido del programador. Sin este flag (o con valor falso) el barrido SOLO
# estampa `preparado_en` (dry-run): ningun post se envia a Metricool.
# `KENI_CONSOLA_URL_PUBLICA` es la URL base publica de la consola (p.ej.
# `https://social.kenitech.io`) necesaria para construir URLs absolutas de media
# que Metricool pueda ingerir. Sin ella las media URLs NO se incluyen en el post.
ENV_PUBLICAR_REAL = "KENI_PUBLICAR_REAL"
ENV_CONSOLA_URL_PUBLICA = "KENI_CONSOLA_URL_PUBLICA"

# Imagen / secretos (precedencia con el fichero vive en `secretos.py`).
ENV_IMAGEN_API_KEY = "KENI_IMAGEN_API_KEY"
ENV_IMAGEN_PROVEEDOR = "KENI_IMAGEN_PROVEEDOR"

# Eventos internos del tablero (pieza aprobada / contenido vencido). El barrido que
# detecta vencimientos y dispara los webhooks salientes corre como hilo demonio en el
# servidor real (igual que el programador). El reparto a la red es OPT-IN: sin webhooks
# activos no hay ninguna peticion de salida.
ENV_EVENTOS_INTERVALO_SEGUNDOS = "KENI_EVENTOS_INTERVALO_SEGUNDOS"
# Apaga del todo el barrido de vencimientos (la emision por transiciones sigue activa,
# solo deja de escanear el reloj). `0`/`false` => no arranca el hilo.
ENV_EVENTOS_VENCIMIENTOS = "KENI_EVENTOS_VENCIMIENTOS"

# Persistencia (#130 / ADR 0004): Postgres OBLIGATORIO para la operacional + object storage
# S3/Garage opcional para la media. NOMBRES EXACTOS de `deploy/docker-compose.yml`/
# `.env.example` (NO se renombran). `DATABASE_URL` (o sus componentes `POSTGRES_*`) es
# requerida; sin S3 cableado la media sigue en disco.
ENV_DATABASE_URL = "DATABASE_URL"
# Componentes de la conexion Postgres (mismos nombres que `deploy/.env.example` y la
# imagen oficial de Postgres). Sirven para DERIVAR `DATABASE_URL` cuando esta no se fija
# explicitamente, evitando que la URL "derive" de la password (incidente de prod: la
# password en `DATABASE_URL` no coincidia con `POSTGRES_PASSWORD`).
ENV_PG_USER = "POSTGRES_USER"
ENV_PG_PASSWORD = "POSTGRES_PASSWORD"
ENV_PG_DB = "POSTGRES_DB"
ENV_PG_HOST = "POSTGRES_HOST"
ENV_PG_PORT = "POSTGRES_PORT"
ENV_S3_ENDPOINT = "S3_ENDPOINT"
ENV_S3_REGION = "S3_REGION"
ENV_S3_BUCKET = "S3_BUCKET"
ENV_S3_ACCESS_KEY = "S3_ACCESS_KEY"
ENV_S3_SECRET_KEY = "S3_SECRET_KEY"

# Rutas de estado (override especifico de cada recurso; fallback en `rutas.py`).
ENV_DATA_DIR = "KENI_DATA_DIR"
ENV_RAIZ = "KENI_CONSOLA_RAIZ"
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
# Cadencia del barrido de refresco de la cache de metricas (horas). "1 vez al dia importa";
# 4h da margen sin golpear las APIs externas en cada apertura.
METRICAS_REFRESCO_HORAS_DEF = 4

# Cadencia del barrido de eventos internos (vencimientos del tablero). 5 min basta: el
# vencimiento es por DIA (`fecha_entrega`), no hace falta granularidad fina.
EVENTOS_INTERVALO_SEGUNDOS_DEF = 300.0

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
    """Token interino OPCIONAL fijado por `KENI_CONSOLA_TOKEN` (None si no esta; vacio = no fijado).

    Tras la auth multiusuario (#130) este token es un gate EXTRA, no la barrera principal:
    la Consola queda protegida por sesion + CSRF aunque no se fije. Si esta presente, sigue
    valiendo como credencial adicional (cabecera/cookie) para clientes de mantenimiento.
    """
    return _crudo(ENV_TOKEN) or None


def origenes_permitidos() -> frozenset[str]:
    """Hosts externos permitidos para la verificacion CSRF (`KENI_CONSOLA_ORIGENES`).

    Lista separada por comas. Cada item se NORMALIZA a `host[:puerto]` en minusculas: se
    acepta tanto un origen completo (`https://social.kenitech.io`) como solo el host
    (`social.kenitech.io`). Vacio (def) => conjunto vacio: el chequeo CSRF compara contra
    el `Host` de la peticion, como en local (127.0.0.1). Detras de un proxy (Traefik) se
    fija al host publico para que las mutaciones del SPA legitimo (cuyo `Origin` es el host
    externo) pasen, sin depender de que el `Host` reenviado coincida byte a byte.
    """
    crudo = _crudo(ENV_ORIGENES)
    if not crudo:
        return frozenset()
    hosts: set[str] = set()
    for parte in crudo.split(","):
        item = parte.strip()
        if not item:
            continue
        host = _host_de_origen(item)
        if host:
            hosts.add(host)
    return frozenset(hosts)


def _host_de_origen(valor: str) -> str | None:
    """Normaliza un item de `KENI_CONSOLA_ORIGENES` a `host[:puerto]` en minusculas.

    Acepta un origen con esquema (`https://host:puerto`) o solo el host (`host:puerto`).
    Devuelve None si no se puede extraer un host (entrada vacia/invalida).
    """
    from urllib.parse import urlsplit

    item = valor.strip().lower()
    if not item:
        return None
    # Con esquema: parsea el netloc. Sin esquema, `urlsplit` no separa el host, asi que
    # lo tratamos como host[:puerto] directo (quitando una posible barra/ruta final).
    if "://" in item:
        try:
            netloc = urlsplit(item).netloc
        except ValueError:
            return None
        netloc = netloc.rsplit("@", 1)[-1]
        return netloc or None
    return item.split("/", 1)[0] or None


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


def metricas_refresco_horas() -> int:
    """Cada cuantas horas refresca la cache de metricas el daemon (`KENI_METRICAS_REFRESCO_HORAS`, def 4, min 1)."""
    return _entero(ENV_METRICAS_REFRESCO_HORAS, METRICAS_REFRESCO_HORAS_DEF, minimo=1)


def eventos_intervalo_segundos() -> float:
    """Intervalo del barrido de vencimientos del tablero en s (`KENI_EVENTOS_INTERVALO_SEGUNDOS`, min 1.0, def 300)."""
    crudo = os.environ.get(ENV_EVENTOS_INTERVALO_SEGUNDOS)
    if not crudo:
        return EVENTOS_INTERVALO_SEGUNDOS_DEF
    try:
        return max(1.0, float(crudo))
    except ValueError:
        return EVENTOS_INTERVALO_SEGUNDOS_DEF


def eventos_vencimientos_activos() -> bool:
    """True (def) si el barrido de vencimientos debe arrancar. `KENI_EVENTOS_VENCIMIENTOS=0` lo apaga.

    Solo controla el HILO que escanea el reloj; la emision de eventos por transicion
    (pieza aprobada/publicada) NO depende de esto.
    """
    crudo = _crudo(ENV_EVENTOS_VENCIMIENTOS)
    if not crudo:
        return True
    return crudo.lower() in _VERDADEROS


def publicar_real() -> bool:
    """True si `KENI_PUBLICAR_REAL` esta a un valor afirmativo (gate de publicacion real).

    Por defecto OFF (False): el programador opera en DRY-RUN. Pon `KENI_PUBLICAR_REAL=1`
    (o `true`/`yes`/`on`) para activar el posteo real al scheduler de Metricool.
    El humano sigue aprobando; esta flag solo autoriza al sistema a enviar lo ya
    programado a Metricool cuando vence la fecha.
    """
    return _crudo(ENV_PUBLICAR_REAL).lower() in _VERDADEROS


def consola_url_publica() -> str | None:
    """URL base publica de la consola (`KENI_CONSOLA_URL_PUBLICA`), sin barra final.

    Necesaria para construir URLs absolutas de media que Metricool pueda ingerir.
    Ejemplo: `https://social.kenitech.io`. None si no esta configurada (en ese caso
    el programador omite las URLs de media en el borrador enviado a Metricool y lo
    registra en el log).
    """
    crudo = _crudo(ENV_CONSOLA_URL_PUBLICA)
    return crudo.rstrip("/") if crudo else None


# --------------------------------------------------------------------------- #
# Accesores: persistencia hosted (Postgres + object storage S3/Garage, #130)   #
# --------------------------------------------------------------------------- #
#
# La media (S3) sigue siendo opcional: sin endpoint+credenciales S3 -> disco. La DB
# operacional, en cambio, es Postgres OBLIGATORIO (ADR 0004): `database_url()` puede
# devolver None, pero `motor_db.conectar_cruda()` exige la URL y falla con un mensaje claro.


def database_url() -> str | None:
    """URL de Postgres del back; None si no esta fijada (ni la URL ni los componentes).

    La operacional (tareas/comercial/rota/usuarios/sesiones/jobs) va SIEMPRE a Postgres
    (ADR 0004): esta funcion resuelve la URL, y `motor_db.conectar_cruda()` la EXIGE (un
    None alli es un error de arranque con mensaje accionable, no un fallback a SQLite).

    PRECEDENCIA (anti-drift):
      1. `DATABASE_URL` explicita -> se devuelve TAL CUAL (override; p. ej. un Postgres
         externo o un DSN con parametros especiales).
      2. Si no hay `DATABASE_URL` pero estan `POSTGRES_USER`+`POSTGRES_PASSWORD`+
         `POSTGRES_DB`, se DERIVA la URL de esos componentes. Asi la URL NO puede
         desincronizarse de la password (incidente de prod: la password embebida en
         `DATABASE_URL` dejo de coincidir con `POSTGRES_PASSWORD`). `host` default `db`
         (nombre del servicio en compose), `port` default `5432`. Usuario y password se
         %-codifican (`quote(..., safe="")`) porque una password base64 puede llevar
         `+`/`/`/`=`, que romperian el parseo de la URL.
      3. Si no hay ni URL ni componentes -> None (sin Postgres configurado: `conectar_cruda`
         lanzara el error obligatorio).
    """
    explicita = _crudo(ENV_DATABASE_URL)
    if explicita:
        return explicita
    usuario = _crudo(ENV_PG_USER)
    password = _crudo(ENV_PG_PASSWORD)
    db = _crudo(ENV_PG_DB)
    if usuario and password and db:
        host = _crudo(ENV_PG_HOST) or "db"
        port = _crudo(ENV_PG_PORT) or "5432"
        return (
            f"postgresql://{quote(usuario, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{db}"
        )
    return None


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

    `nombre` es una de las constantes `ENV_*` de ruta de este modulo (p.ej. `ENV_INDICE`).
    """
    crudo = os.environ.get(nombre)
    if crudo:
        return Path(crudo).expanduser()
    return None
