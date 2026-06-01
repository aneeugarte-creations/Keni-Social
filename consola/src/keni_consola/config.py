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

  Biblioteca de prompts + linea editorial (`biblioteca`, `dominio.biblioteca_lanzar`):
    - KENI_BIBLIOTECA_DIR         almacen de documentos markdown     def <dir_config>/biblioteca

  Programadores en segundo plano (`comercial`, `programador`):
    - KENI_COMERCIAL_INTERVALO_SEGUNDOS  intervalo captura (s)       prioridad sobre horas
    - KENI_COMERCIAL_INTERVALO_HORAS     intervalo captura (h)       def INTERVALO_HORAS_DEF
    - KENI_PROGRAMADOR_INTERVALO_SEGUNDOS  intervalo barrido (s)     def INTERVALO_SEGUNDOS_DEF
    - KENI_METRICAS_REFRESCO_HORAS       refresco cache metricas (h) def 4   (min 1)
    - KENI_METRICAS_PIEZAS_REFRESCO_HORAS refresco cache POR PIEZA (h) def 4 (min 1)
    - KENI_ALERTAS_RENDIMIENTO_HORAS     barrido alertas rendim. (h) def 6   (min 1)
    - KENI_ALERTAS_RENDIMIENTO           apaga el barrido de alertas def ON
    - KENI_ALERTAS_UMBRAL_ENGAGEMENT     umbral bajo rendim. (%)     def 1.0

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

# Biblioteca de prompts + linea editorial (almacen unico de documentos markdown).
ENV_BIBLIOTECA_DIR = "KENI_BIBLIOTECA_DIR"

# Programadores en segundo plano.
ENV_COMERCIAL_INTERVALO_SEGUNDOS = "KENI_COMERCIAL_INTERVALO_SEGUNDOS"
ENV_COMERCIAL_INTERVALO_HORAS = "KENI_COMERCIAL_INTERVALO_HORAS"
ENV_PROGRAMADOR_INTERVALO_SEGUNDOS = "KENI_PROGRAMADOR_INTERVALO_SEGUNDOS"
ENV_METRICAS_REFRESCO_HORAS = "KENI_METRICAS_REFRESCO_HORAS"
# Refresco PROACTIVO de la cache de metricas POR PIEZA (tablero) — Fase 3 auto-operativa.
ENV_METRICAS_PIEZAS_REFRESCO_HORAS = "KENI_METRICAS_PIEZAS_REFRESCO_HORAS"
# Barrido de ALERTAS de rendimiento / reciclaje proactivo (emite eventos internos).
ENV_ALERTAS_INTERVALO_HORAS = "KENI_ALERTAS_RENDIMIENTO_HORAS"
ENV_ALERTAS_ACTIVAS = "KENI_ALERTAS_RENDIMIENTO"
# Umbral (% engagement) por debajo del cual una pieza publicada se considera "bajo
# rendimiento" y dispara una alerta. Def 1.0 (muy por debajo del ~2-3% tipico del piloto).
ENV_ALERTAS_UMBRAL_ENGAGEMENT = "KENI_ALERTAS_UMBRAL_ENGAGEMENT"

# Publicacion real via Metricool (gate de seguridad; def OFF = dry-run).
# `KENI_PUBLICAR_REAL=1` activa el posteo real al scheduler de Metricool en el
# barrido del programador. Sin este flag (o con valor falso) el barrido SOLO
# estampa `preparado_en` (dry-run): ningun post se envia a Metricool.
# `KENI_CONSOLA_URL_PUBLICA` es la URL base publica de la consola (p.ej.
# `https://social.kenitech.io`) necesaria para construir URLs absolutas de media
# que Metricool pueda ingerir. Sin ella las media URLs NO se incluyen en el post.
ENV_PUBLICAR_REAL = "KENI_PUBLICAR_REAL"
ENV_CONSOLA_URL_PUBLICA = "KENI_CONSOLA_URL_PUBLICA"

# Pre-aprobacion de piezas de BAJO RIESGO (fase3 auto-planificacion). Flag admin,
# CONSERVADOR por defecto (OFF): cuando se activa, al crear la cadena de aprobacion de una
# pieza de bajo riesgo (evergreen reutilizado sin cambios, o solo canal web/no-social) se
# auto-aprueban los niveles INFERIORES de la cadena, dejando SIEMPRE el ultimo nivel a un
# humano. Trazable: el decisor auto se sella como "auto". `KENI_AUTO_PREAPROBACION=1` lo
# enciende; sin el (o falsy), la cadena nace toda `pendiente` como hasta ahora.
ENV_AUTO_PREAPROBACION = "KENI_AUTO_PREAPROBACION"

# Auto-promocion del Radar de tendencias a "lo importante del dia" (fase3 auto-planificacion).
# `KENI_RADAR_AUTO=1` arranca el daemon que, cada N horas, promueve los temas que superan el
# umbral de señal a contenido `flujo='importante'` (origen 'radar-auto'). CONSERVADOR por
# defecto (OFF) y con umbral ALTO: nada llega al tablero sin superar la señal minima, y el
# equipo siempre puede revisar/borrar. El endpoint `/api/radar/auto/*` permite revisar la
# bandeja y ejecutar el batch a demanda independientemente del daemon.
ENV_RADAR_AUTO = "KENI_RADAR_AUTO"
ENV_RADAR_AUTO_UMBRAL = "KENI_RADAR_AUTO_UMBRAL"
ENV_RADAR_AUTO_GEO = "KENI_RADAR_AUTO_GEO"
ENV_RADAR_AUTO_INTERVALO_HORAS = "KENI_RADAR_AUTO_INTERVALO_HORAS"
ENV_RADAR_AUTO_MAX = "KENI_RADAR_AUTO_MAX"
ENV_RADAR_AUTO_MARCA = "KENI_RADAR_AUTO_MARCA"

# Auto-generacion de COPY al entrar un tema al tablero (fase3 auto-produccion, H2). Un hilo
# demonio barre el tablero y, para los temas alimentados por fuentes (import-calendario,
# radar-auto, radar, rss) que aun no tienen copy generado y SI tienen marca, ENCOLA una
# generacion de copy (mismo pipeline que el boton manual). El borrador resultante cae en la
# cola de revision. CONSERVADOR por defecto (OFF): sin `KENI_AUTOGEN` el equipo genera a mano.
ENV_AUTOGEN = "KENI_AUTOGEN"
ENV_AUTOGEN_INTERVALO_HORAS = "KENI_AUTOGEN_INTERVALO_HORAS"
ENV_AUTOGEN_MAX = "KENI_AUTOGEN_MAX"

# Auto-generacion de ARTE (imagen) para temas con copy pero sin imagen (fase3 auto-produccion,
# H2-b). Un hilo demonio barre el tablero y, para los temas con borrador/copy en alguna
# plataforma a la que le FALTA imagen, genera UN arte por IA (mismo proveedor que
# `/api/media/generar`) y lo adjunta. CONSERVADOR por defecto (OFF): sin `KENI_AUTOGEN_ARTE`
# el equipo hace el arte a mano. Sin proveedor de imagen configurado, no hace nada.
ENV_AUTOGEN_ARTE = "KENI_AUTOGEN_ARTE"
ENV_AUTOGEN_ARTE_INTERVALO_HORAS = "KENI_AUTOGEN_ARTE_INTERVALO_HORAS"
ENV_AUTOGEN_ARTE_MAX = "KENI_AUTOGEN_ARTE_MAX"

# Reaper de generaciones zombi: una generacion `ejecutando` cuyo proceso murio (reinicio/
# OOM/cuelgue) queda colgada para siempre. El reaper la cierra como `error` pasada una
# antigüedad MUY superior al wall-timeout (asi nunca mata una viva). Siempre activo.
ENV_GENERACIONES_TTL_HORAS = "KENI_GENERACIONES_TTL_HORAS"
ENV_REAPER_INTERVALO_MIN = "KENI_REAPER_INTERVALO_MIN"

# Recoleccion de basura (GC) de MEDIA HUERFANA (Estudio de imagen, diseno §5). El Estudio
# genera N variantes; las NO elegidas quedan como objetos sueltos en el almacen de media que
# nadie borra. Un hilo demonio barre periodicamente el almacen y borra SOLO los objetos
# HUERFANOS: ni referenciados por una publicacion (`imagen`) ni catalogados en biblioteca-media
# y mas VIEJOS que un umbral (def 24h, para no tocar variantes recien generadas que el usuario
# aun revisa). CONSERVADOR por defecto (OFF): sin `KENI_MEDIA_GC` no se borra nada.
ENV_MEDIA_GC = "KENI_MEDIA_GC"
ENV_MEDIA_GC_INTERVALO_HORAS = "KENI_MEDIA_GC_INTERVALO_HORAS"
ENV_MEDIA_GC_ANTIGUEDAD_HORAS = "KENI_MEDIA_GC_ANTIGUEDAD_HORAS"

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
# Store EDITABLE de ajustes de funcionalidad (flags + tuning) gestionado por la API admin
# (`keni_consola.ajustes`). Su VALOR participa en la PRECEDENCIA de `_crudo` (store > env);
# este nombre solo sobreescribe la RUTA del fichero (override de maxima prioridad).
ENV_AJUSTES = "KENI_CONSOLA_AJUSTES"
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
# Cadencia del refresco proactivo de la cache POR PIEZA (tablero). Casa con el TTL de
# `metricas_pieza` (4h): un post no cambia minuto a minuto.
METRICAS_PIEZAS_REFRESCO_HORAS_DEF = 4
# Cadencia del barrido de alertas de rendimiento / reciclaje proactivo (horas).
ALERTAS_INTERVALO_HORAS_DEF = 6
# Umbral de engagement (%) por debajo del cual una pieza dispara alerta de bajo rendimiento.
ALERTAS_UMBRAL_ENGAGEMENT_DEF = 1.0

# Cadencia del barrido de eventos internos (vencimientos del tablero). 5 min basta: el
# vencimiento es por DIA (`fecha_entrega`), no hace falta granularidad fina.
EVENTOS_INTERVALO_SEGUNDOS_DEF = 300.0

# Defaults de la auto-promocion del Radar (fase3). Umbral ALTO (solo lo muy viral entra
# solo), intervalo holgado (no golpear Google Trends), pocos temas por barrido (no inundar).
RADAR_AUTO_UMBRAL_DEF = 50_000
RADAR_AUTO_GEO_DEF = "MX"
RADAR_AUTO_INTERVALO_HORAS_DEF = 6
RADAR_AUTO_MAX_DEF = 3

# Auto-generacion de copy (H2): barre seguido (def 1h) y con cap bajo por barrido (def 3),
# porque cada item lanza un `claude -p` (coste). El cap del worker (`KENI_MAX_JOBS`) sigue
# aplicando aguas abajo.
AUTOGEN_INTERVALO_HORAS_DEF = 1
AUTOGEN_MAX_DEF = 3

# Auto-generacion de ARTE (H2-b): mismos defaults conservadores que el auto-copy (barre
# seguido, cap bajo por barrido), porque cada item llama al proveedor de imagen (coste).
AUTOGEN_ARTE_INTERVALO_HORAS_DEF = 1
AUTOGEN_ARTE_MAX_DEF = 3

# Reaper de generaciones: TTL 1h (>> wall-timeout de ~10 min, asi no toca jobs vivos) y
# barrido cada 10 min. El barrido tambien corre al arrancar (limpia los huerfanos del crash
# anterior de inmediato).
GENERACIONES_TTL_HORAS_DEF = 1
REAPER_INTERVALO_MIN_DEF = 10

# Recoleccion de basura de media huerfana (Estudio §5). Barre 1 vez al dia (no urge: el
# almacen crece lento) y solo borra objetos mas viejos que ANTIGUEDAD (def 24h), para NO
# tocar las variantes recien generadas que el usuario aun esta revisando en el Estudio.
MEDIA_GC_INTERVALO_HORAS_DEF = 24
MEDIA_GC_ANTIGUEDAD_HORAS_DEF = 24

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
    """Valor crudo (str) de un ajuste, sin espacios; "" si no esta.

    PRECEDENCIA (STORE > ENV > DEFECTO): primero el store EDITABLE de ajustes
    (`keni_consola.ajustes`, gestionado por la API admin); si el store no tiene la clave,
    cae a `os.environ`. Asi un flag/tuning cambiado desde la UI gana al entorno, y una clave
    no editada (ausente del store) se comporta EXACTAMENTE como hoy (lee la env / cae al
    defecto del accesor). Como todos los accesores (`_entero` y los de float, que tambien
    leen `_crudo`) pasan por aqui, la precedencia aplica de forma uniforme.

    El import de `ajustes` es PEREZOSO (dentro de la funcion) para evitar el ciclo de import
    a nivel de modulo: `ajustes` usa `rutas`, y `rutas` importa `config`.
    """
    from . import ajustes  # perezoso: evita el ciclo config <- rutas <- ... y ajustes->rutas

    desde_store = ajustes.obtener(nombre)
    if desde_store is not None:
        return desde_store.strip()
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
# Accesores: biblioteca de prompts + linea editorial                           #
# --------------------------------------------------------------------------- #


def biblioteca_dir() -> Path | None:
    """Override del dir del almacen de la Biblioteca (`KENI_BIBLIOTECA_DIR`); None si no esta.

    Sin override, `biblioteca.raiz()` cae a `rutas.dir_config()/biblioteca` (bajo el volumen
    `KENI_DATA_DIR` en contenedor; `~/.config/keni-social/biblioteca` en local). Los tests lo
    apuntan a un `tmp_path` para no tocar el estado real.
    """
    crudo = os.environ.get(ENV_BIBLIOTECA_DIR)
    return Path(crudo).expanduser() if crudo else None


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


def metricas_piezas_refresco_horas() -> int:
    """Cada cuantas horas refresca el daemon la cache POR PIEZA del tablero.

    `KENI_METRICAS_PIEZAS_REFRESCO_HORAS`, def 4, min 1. Fase 3 auto-operativa: refresca
    proactivamente el rendimiento de las piezas publicadas recientes (con `id_post_metricool`)
    para que el tablero y el reciclaje vean datos frescos sin lazy-fill en la apertura.
    """
    return _entero(
        ENV_METRICAS_PIEZAS_REFRESCO_HORAS, METRICAS_PIEZAS_REFRESCO_HORAS_DEF, minimo=1
    )


def alertas_rendimiento_horas() -> int:
    """Cada cuantas horas corre el barrido de alertas de rendimiento/reciclaje.

    `KENI_ALERTAS_RENDIMIENTO_HORAS`, def 6, min 1.
    """
    return _entero(ENV_ALERTAS_INTERVALO_HORAS, ALERTAS_INTERVALO_HORAS_DEF, minimo=1)


def alertas_rendimiento_activas() -> bool:
    """True (def) si el barrido de alertas debe arrancar. `KENI_ALERTAS_RENDIMIENTO=0` lo apaga.

    Solo controla el HILO; la emision de eventos por transicion del tablero no depende de esto.
    """
    crudo = _crudo(ENV_ALERTAS_ACTIVAS)
    if not crudo:
        return True
    return crudo.lower() in _VERDADEROS


def alertas_umbral_engagement() -> float:
    """Umbral de engagement (%) para la alerta de bajo rendimiento.

    `KENI_ALERTAS_UMBRAL_ENGAGEMENT`, def 1.0. Una pieza publicada con engagement REAL
    (Metricool) por debajo de este valor dispara `pieza.bajo_rendimiento`. Valor invalido
    o <=0 -> def (no tiene sentido un umbral nulo).
    """
    crudo = _crudo(ENV_ALERTAS_UMBRAL_ENGAGEMENT)
    if not crudo:
        return ALERTAS_UMBRAL_ENGAGEMENT_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return ALERTAS_UMBRAL_ENGAGEMENT_DEF
    return valor if valor > 0 else ALERTAS_UMBRAL_ENGAGEMENT_DEF


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


def auto_preaprobacion() -> bool:
    """True si la pre-aprobacion de piezas de bajo riesgo esta activa (`KENI_AUTO_PREAPROBACION`).

    Def OFF (False, conservador): la cadena de aprobacion nace toda `pendiente`. Con el flag
    a un valor afirmativo, al crear la cadena de una pieza de bajo riesgo se auto-aprueban
    los niveles inferiores (nunca el ultimo, que queda a un humano). Trazable como "auto".
    """
    return _crudo(ENV_AUTO_PREAPROBACION).lower() in _VERDADEROS


def radar_auto_activo() -> bool:
    """True si el daemon de auto-promocion del Radar debe arrancar (`KENI_RADAR_AUTO`).

    Def OFF (conservador): el Radar solo propone (la promocion la decide el equipo). Con el
    flag a un valor afirmativo, un hilo demonio promueve periodicamente los temas que superan
    el umbral de señal a `flujo='importante'` (origen 'radar-auto'), revisable en el tablero.
    """
    return _crudo(ENV_RADAR_AUTO).lower() in _VERDADEROS


def radar_auto_umbral() -> int:
    """Umbral MINIMO de señal (`senal` del tema) para auto-promover (`KENI_RADAR_AUTO_UMBRAL`).

    Def ALTO (50000) a proposito: solo lo MUY viral entra solo. Min 1 (un umbral <=0 no tiene
    sentido: promoveria cualquier cosa). La `senal` es el trafico aproximado de Google Trends
    (ver `radar.traduce_trafico`): 50K+ es una tendencia fuerte de verdad.
    """
    return _entero(ENV_RADAR_AUTO_UMBRAL, RADAR_AUTO_UMBRAL_DEF, minimo=1)


def radar_auto_geo() -> str:
    """Geo del Radar para la auto-promocion (`KENI_RADAR_AUTO_GEO`, def MX, mayusculas)."""
    return _crudo(ENV_RADAR_AUTO_GEO).upper() or RADAR_AUTO_GEO_DEF


def radar_auto_intervalo_horas() -> int:
    """Cada cuantas horas barre el daemon del Radar (`KENI_RADAR_AUTO_INTERVALO_HORAS`, def 6, min 1)."""
    return _entero(ENV_RADAR_AUTO_INTERVALO_HORAS, RADAR_AUTO_INTERVALO_HORAS_DEF, minimo=1)


def radar_auto_max() -> int:
    """Maximo de temas a auto-promover por barrido (`KENI_RADAR_AUTO_MAX`, def 3, min 1).

    Cota de seguridad: aunque muchos temas superen el umbral, no inundamos el tablero; se
    promueven los N de MAYOR señal por barrido.
    """
    return _entero(ENV_RADAR_AUTO_MAX, RADAR_AUTO_MAX_DEF, minimo=1)


def radar_auto_marca() -> str:
    """Marca (id canonico) a asignar a las piezas auto-promovidas (`KENI_RADAR_AUTO_MARCA`).

    "" (def) = sin marca (el equipo la asigna luego). Si se fija una marca invalida, el
    llamante la ignora (cae a sin marca): no se confia ciegamente del entorno.
    """
    return _crudo(ENV_RADAR_AUTO_MARCA)


def autogen_activo() -> bool:
    """True si el daemon de auto-generacion de copy debe arrancar (`KENI_AUTOGEN`).

    Def OFF (conservador): los temas entran al tablero sin copy y el equipo lo genera a mano.
    Con el flag, un hilo demonio encola copy para los temas alimentados por fuentes que aun
    no lo tienen (revisable en la cola de revision). Nada se publica solo (sigue gated).
    """
    return _crudo(ENV_AUTOGEN).lower() in _VERDADEROS


def autogen_intervalo_horas() -> int:
    """Cada cuantas horas barre el daemon de auto-generacion (`KENI_AUTOGEN_INTERVALO_HORAS`, def 1, min 1)."""
    return _entero(ENV_AUTOGEN_INTERVALO_HORAS, AUTOGEN_INTERVALO_HORAS_DEF, minimo=1)


def autogen_max() -> int:
    """Maximo de temas a auto-generar por barrido (`KENI_AUTOGEN_MAX`, def 3, min 1).

    Cada item lanza un `claude -p`: el cap evita una avalancha de jobs por barrido.
    """
    return _entero(ENV_AUTOGEN_MAX, AUTOGEN_MAX_DEF, minimo=1)


def autogen_arte_activo() -> bool:
    """True si el daemon de auto-generacion de arte debe arrancar (`KENI_AUTOGEN_ARTE`).

    Def OFF (conservador): el equipo hace el arte a mano. Con el flag, un hilo demonio
    genera imagen por IA para los temas con copy pero sin imagen y la adjunta. Sin
    proveedor de imagen configurado, el daemon arranca pero no hace nada (degrada).
    """
    return _crudo(ENV_AUTOGEN_ARTE).lower() in _VERDADEROS


def autogen_arte_intervalo_horas() -> int:
    """Cada cuantas horas barre el daemon de auto-arte (`KENI_AUTOGEN_ARTE_INTERVALO_HORAS`, def 1, min 1)."""
    return _entero(
        ENV_AUTOGEN_ARTE_INTERVALO_HORAS, AUTOGEN_ARTE_INTERVALO_HORAS_DEF, minimo=1
    )


def media_gc_activo() -> bool:
    """True si el daemon de GC de media huerfana debe BARRER (`KENI_MEDIA_GC`).

    Def OFF (conservador): sin el flag NO se borra ningun objeto del almacen. Con el flag,
    un hilo demonio barre cada N horas y borra los objetos HUERFANOS (no referenciados por
    ninguna publicacion ni catalogados en biblioteca-media) y mas viejos que el umbral. El
    hilo arranca SIEMPRE pero, gateado, solo actua cuando el flag esta activo.
    """
    return _crudo(ENV_MEDIA_GC).lower() in _VERDADEROS


def media_gc_intervalo_horas() -> int:
    """Cada cuantas horas barre el daemon de GC de media (`KENI_MEDIA_GC_INTERVALO_HORAS`, def 24, min 1)."""
    return _entero(
        ENV_MEDIA_GC_INTERVALO_HORAS, MEDIA_GC_INTERVALO_HORAS_DEF, minimo=1
    )


def media_gc_antiguedad_horas() -> int:
    """Antiguedad MINIMA (horas) de un objeto para considerarlo borrable (`KENI_MEDIA_GC_ANTIGUEDAD_HORAS`).

    Def 24h, min 1: un objeto mas NUEVO que esto NUNCA se borra, aunque parezca huerfano,
    para no eliminar las variantes recien generadas por el Estudio que el usuario aun revisa.
    """
    return _entero(
        ENV_MEDIA_GC_ANTIGUEDAD_HORAS, MEDIA_GC_ANTIGUEDAD_HORAS_DEF, minimo=1
    )


def autogen_arte_max() -> int:
    """Maximo de temas a auto-ilustrar por barrido (`KENI_AUTOGEN_ARTE_MAX`, def 3, min 1).

    Cada item llama al proveedor de imagen (coste): el cap evita avalanchas por barrido.
    """
    return _entero(ENV_AUTOGEN_ARTE_MAX, AUTOGEN_ARTE_MAX_DEF, minimo=1)


def generaciones_ttl_seg() -> int:
    """Antigüedad (s) tras la cual una generacion `ejecutando` se considera zombi.

    `KENI_GENERACIONES_TTL_HORAS` (def 1 h, min 1). MUY por encima del wall-timeout (~10 min):
    asi el reaper nunca cierra una generacion que de verdad sigue viva.
    """
    return _entero(ENV_GENERACIONES_TTL_HORAS, GENERACIONES_TTL_HORAS_DEF, minimo=1) * 3600


def reaper_intervalo_seg() -> int:
    """Cada cuanto barre el reaper de generaciones (`KENI_REAPER_INTERVALO_MIN`, def 10, min 1)."""
    return _entero(ENV_REAPER_INTERVALO_MIN, REAPER_INTERVALO_MIN_DEF, minimo=1) * 60


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
