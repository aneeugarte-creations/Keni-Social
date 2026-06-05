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

# MFA PASSKEYS / WebAuthn (segundo factor), GATEADO OFF por defecto. `KENI_CONSOLA_MFA`
# afirmativo activa la elevacion de login (un usuario con >=1 passkey debe completar una
# ceremonia WebAuthn tras la contrasena) y la seccion de "Llaves de acceso" en "Mi cuenta".
# Con el flag OFF el login se comporta EXACTAMENTE como hoy (nunca se pide segundo factor).
# `KENI_CONSOLA_MFA_KEY` es una clave Fernet (base64 url-safe de 32 bytes) que ahora FIRMA y
# fecha la cookie del CHALLENGE/pre-auth de vida corta (ya no cifra un secreto TOTP: en
# passkeys el secreto vive en el dispositivo del usuario). Si el flag esta ON pero la clave
# falta/es invalida, las ceremonias REHUSAN (fail-safe, 503), nunca se media-autentica.
ENV_MFA = "KENI_CONSOLA_MFA"
ENV_MFA_KEY = "KENI_CONSOLA_MFA_KEY"
# WebAuthn Relying Party: identidad del servidor frente al autenticador.
#   - RP_ID: dominio efectivo (sin esquema ni puerto). Dev: `localhost`. Prod: `social.kenitech.io`.
#   - RP_ORIGIN: origen(es) esperado(s) de la ceremonia (con esquema y puerto). Dev:
#     `http://localhost:8765`. Prod: `https://social.kenitech.io`. Admite lista separada por comas.
#   - RP_NOMBRE: nombre legible que el SO muestra al crear/usar la passkey ("Keni Social").
ENV_RP_ID = "KENI_CONSOLA_RP_ID"
ENV_RP_ORIGIN = "KENI_CONSOLA_RP_ORIGIN"
ENV_RP_NOMBRE = "KENI_CONSOLA_RP_NOMBRE"

# MCP operativo (servidor MCP montado en `/mcp`): bearer que exige el endpoint a los
# clientes (este Claude Code) e identidad (usuario) con la que el MCP opera la API
# interna. Si `KENI_MCP_BEARER` no esta, el endpoint `/mcp` NO se monta (apagado por
# defecto: el despliegue actual no cambia hasta que el operador fije el bearer).
ENV_MCP_BEARER = "KENI_MCP_BEARER"
# Usuario al que se ATRIBUYEN las acciones del MCP (autor en el historial). Si no se
# fija, cae al admin de bootstrap (`KENI_CONSOLA_ADMIN_USER`): el dueño de la consola.
ENV_MCP_USUARIO = "KENI_MCP_USUARIO"

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
# Herramientas VETADAS en la generacion (`--disallowed-tools`). Defensa contra
# prompt-injection: la generacion de copy no necesita ejecutar comandos ni navegar.
ENV_CLAUDE_DISALLOWED_TOOLS = "KENI_CLAUDE_DISALLOWED_TOOLS"

# Biblioteca de prompts + linea editorial (almacen unico de documentos markdown).
ENV_BIBLIOTECA_DIR = "KENI_BIBLIOTECA_DIR"

# Programadores en segundo plano.
ENV_COMERCIAL_INTERVALO_SEGUNDOS = "KENI_COMERCIAL_INTERVALO_SEGUNDOS"
ENV_COMERCIAL_INTERVALO_HORAS = "KENI_COMERCIAL_INTERVALO_HORAS"
ENV_PROGRAMADOR_INTERVALO_SEGUNDOS = "KENI_PROGRAMADOR_INTERVALO_SEGUNDOS"
ENV_METRICAS_REFRESCO_HORAS = "KENI_METRICAS_REFRESCO_HORAS"
# Refresco PROACTIVO de la cache de metricas POR PIEZA (tablero) — Fase 3 auto-operativa.
ENV_METRICAS_PIEZAS_REFRESCO_HORAS = "KENI_METRICAS_PIEZAS_REFRESCO_HORAS"
# Retencion (dias) del HISTORICO de metricas por pieza (`metricas_pieza_snapshots`, ADR 0007).
ENV_METRICAS_HISTORICO_RETENCION_DIAS = "KENI_METRICAS_HISTORICO_RETENCION_DIAS"
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

# Gate de gobernanza "minimo N aprobaciones" (item A QA/aprobaciones). Antes de PROGRAMAR una
# pieza se exige que su cadena de aprobacion acumule al menos N niveles aprobados (defecto 2:
# "cuatro ojos" reales). `KENI_MIN_APROBACIONES=0` desactiva el gate; valor invalido -> def.
ENV_MIN_APROBACIONES = "KENI_MIN_APROBACIONES"

# QA Editorial como APROBADOR AUTOMATICO (item D). Flag admin, CONSERVADOR por defecto (OFF):
# cuando se activa, la cadena de aprobacion nace con un PRIMER nivel automatico "QA Editorial"
# que aprueba/pendiente/rechaza segun el veredicto 🟢/🟡/🔴 de la skill de QA. El ULTIMO nivel
# sigue siendo humano. `KENI_AUTO_QA_EDITORIAL=1` lo enciende.
ENV_AUTO_QA_EDITORIAL = "KENI_AUTO_QA_EDITORIAL"

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

# Investigador (Fase 1): daemon que MATERIALIZA por marca un snapshot del Radar (temas
# consolidados + score/razon/estado) en Postgres, para que la Parrilla y el Radar lean del
# snapshot (rapido, sin re-descargar fuentes) en vez de golpear Trends/feeds en cada request.
# CONSERVADOR por defecto (OFF): sin el flag, el snapshot NUNCA se lee (los endpoints siguen
# en vivo, comportamiento de Fase 0 intacto) y el daemon arranca pero no materializa nada.
ENV_INVESTIGADOR = "KENI_INVESTIGADOR"
ENV_INVESTIGADOR_INTERVALO_HORAS = "KENI_INVESTIGADOR_INTERVALO_HORAS"

# `KENI_PIPELINE_LINEAS=1` activa el auto-etiquetado de la ingesta: cada pieza nueva se
# clasifica en su LÍNEA (etiqueta clase 'vertical') y su ORIGEN (clase 'origen') por
# palabras clave. CONSERVADOR por defecto (OFF): sin el flag, la ingesta no etiqueta nada
# (comportamiento previo intacto). Una pieza sin línea NO se descarta: queda marcada con
# un aviso para que el equipo la clasifique o la deseche a mano.
ENV_PIPELINE_LINEAS = "KENI_PIPELINE_LINEAS"

# Loop de aprendizaje (Fase 5): el score de priorizacion tiene en cuenta lo que
# HISTORICAMENTE rinde por marca (engagement de la fachada de metricas). Gateado OFF por
# defecto (conservador): sin el flag, la lista del dia ordena EXACTAMENTE como hoy. Con el
# flag, las piezas de marcas que rinden mas reciben un pequeño bonus de score. Es ADITIVO y
# DEGRADABLE: si las metricas no estan disponibles, se omite sin romper (vuelve al score base).
ENV_PRIORIZA_METRICAS = "KENI_PRIORIZA_METRICAS"
ENV_PRIORIZA_METRICAS_RANGO = "KENI_PRIORIZA_METRICAS_RANGO"

# Auto-refresco de Algoritmos (inteligencia de plataforma): ingiere periodicamente los
# feeds de blogs oficiales/agregadores. Gateado OFF por defecto (la pagina Algoritmos tiene
# un boton "Refrescar" manual); con el flag ON, un daemon ingiere cada N horas.
ENV_ALGORITMOS_AUTO = "KENI_ALGORITMOS_AUTO"
ENV_ALGORITMOS_INTERVALO_HORAS = "KENI_ALGORITMOS_INTERVALO_HORAS"
# Digest DIARIO de sugerencias editoriales a partir de las noticias importantes (encola un
# claude -p por plataforma afectada). Gateado OFF por defecto.
ENV_SUGERENCIAS_EDITORIALES = "KENI_SUGERENCIAS_EDITORIALES"
ENV_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS = "KENI_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS"
ENV_SUGERENCIAS_EDITORIALES_MAX = "KENI_SUGERENCIAS_EDITORIALES_MAX"

# Carril Rápido de Breaking (Claro Sports): un hilo demonio barre el snapshot del Investigador
# cada N minutos y, para los temas breaking de Claro Sports sin borrador aún, crea un DRAFT y
# encola la generación de copy (mismo camino que /api/breaking/preparar). SÓLO BORRADORES; nunca
# publica. CONSERVADOR por defecto (OFF): sin `KENI_BREAKING` el equipo lo hace a mano con el tap.
ENV_BREAKING = "KENI_BREAKING"
ENV_BREAKING_INTERVALO_MIN = "KENI_BREAKING_INTERVALO_MIN"
ENV_BREAKING_MAX = "KENI_BREAKING_MAX"

# Auto-generacion de COPY al entrar un tema al tablero (fase3 auto-produccion, H2). Un hilo
# demonio barre el tablero y, para los temas alimentados por fuentes (import-calendario,
# radar-auto, radar, rss) que aun no tienen copy generado y SI tienen marca, ENCOLA una
# generacion de copy (mismo pipeline que el boton manual). El borrador resultante cae en la
# cola de revision. CONSERVADOR por defecto (OFF): sin `KENI_AUTOGEN` el equipo genera a mano.
ENV_AUTOGEN = "KENI_AUTOGEN"
ENV_AUTOGEN_INTERVALO_HORAS = "KENI_AUTOGEN_INTERVALO_HORAS"
ENV_AUTOGEN_MAX = "KENI_AUTOGEN_MAX"

# Pipeline de contenido CI→CD→QA por marca (fase3 auto-produccion, Flujo "tubería"). Un hilo
# demonio que, cada N horas y por marca con feeds RSS activos, ingiere temas frescos (CI),
# lanza la generacion de copy+arte de marca (CD, mismo camino que el boton manual) y valida
# automaticamente los borradores recientes (QA), registrando CADA etapa en "Actividad IA" como
# un pipeline de CI/CD. Deja BORRADORES en la cola de revision para la aprobacion humana; NUNCA
# publica. CONSERVADOR por defecto (OFF): sin `KENI_PIPELINE` el comportamiento no cambia.
ENV_PIPELINE = "KENI_PIPELINE"
ENV_PIPELINE_INTERVALO_HORAS = "KENI_PIPELINE_INTERVALO_HORAS"
ENV_PIPELINE_MAX = "KENI_PIPELINE_MAX"

# Auto-generacion de ARTE (imagen) para temas con copy pero sin imagen (fase3 auto-produccion,
# H2-b). Un hilo demonio barre el tablero y, para los temas con borrador/copy en alguna
# plataforma a la que le FALTA imagen, genera UN arte por IA (mismo proveedor que
# `/api/media/generar`) y lo adjunta. CONSERVADOR por defecto (OFF): sin `KENI_AUTOGEN_ARTE`
# el equipo hace el arte a mano. Sin proveedor de imagen configurado, no hace nada.
ENV_AUTOGEN_ARTE = "KENI_AUTOGEN_ARTE"
ENV_AUTOGEN_ARTE_INTERVALO_HORAS = "KENI_AUTOGEN_ARTE_INTERVALO_HORAS"
ENV_AUTOGEN_ARTE_MAX = "KENI_AUTOGEN_ARTE_MAX"

# Auto-avance "dale el OK" (Flujo D): un hilo demonio lleva SOLO a `en_revision` (abre los OK
# del equipo) las piezas en borrador que ya tienen copy out, copy in (o exención), imagen con
# formato correcto y QA pasado (🟢/🟡). De paso, lanza la QA editorial por pieza de las que aún
# no la tienen, para que el veredicto exista. CONSERVADOR por defecto (OFF): sin el flag, mandar
# a revisión sigue siendo manual. `KENI_AUTO_AVANCE_MAX` acota los lanzamientos de QA por barrido.
ENV_AUTO_AVANCE = "KENI_AUTO_AVANCE"
ENV_AUTO_AVANCE_INTERVALO_HORAS = "KENI_AUTO_AVANCE_INTERVALO_HORAS"
ENV_AUTO_AVANCE_MAX = "KENI_AUTO_AVANCE_MAX"

# Auto-programación: una pieza APROBADA (cerrada toda su cadena humana) pasa SOLA a `programado`
# en su próximo hueco de franja. A diferencia del resto de etapas de auto-producción (que gastan
# `claude -p` o podrían postear), programar es bookkeeping interno, reversible y NO publica (el
# posteo sigue gated por KENI_PUBLICAR_REAL), así que su default es ON: el OK humano es el gate;
# aprobado => programado es el flujo deseado. `KENI_AUTO_PROGRAMAR=0` lo apaga (kill switch).
ENV_AUTO_PROGRAMAR = "KENI_AUTO_PROGRAMAR"

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

# Insumos del día (cajones): modelo de parseo que usa `claude -p` para extraer los ítems
# del material diario (portal/corresponsales/reporteros/eventos_claro). Por defecto "haiku"
# (más rápido/económico para extracción estructurada). Si se deja vacío (""), no se pasa
# `--model` y `claude` usa su propio default. Ver `dominio/insumos_parse.py`.
ENV_INSUMOS_MODELO = "KENI_INSUMOS_MODELO"

# Agentes de investigacion (Ola 6): briefs reutilizables que proponen candidatos fechados.
# GATEADO OFF por defecto: sin el flag, el daemon no barre. El endpoint /api/investigacion/correr
# funciona a demanda independientemente del flag del daemon.
ENV_INVESTIGACION = "KENI_INVESTIGACION_AUTO"
ENV_INVESTIGACION_INTERVALO_HORAS = "KENI_INVESTIGACION_INTERVALO_HORAS"
ENV_INVESTIGACION_MAX = "KENI_INVESTIGACION_MAX"

# Traducción + tropicalización MX de temas extranjeros en el Radar (Ola 4).
# `KENI_TRADUCCION=0` apaga la traducción (def ON: ahorra pedir explicitamente activarla).
# `KENI_TRADUCCION_MAX` acota cuántos temas extranjeros del top se traducen por request
# (def 15). Se usa el mismo modelo de `KENI_INSUMOS_MODELO` (Haiku). Ver
# `dominio/traduccion.py` y la integración en `api/radar.py`.
ENV_TRADUCCION = "KENI_TRADUCCION"
ENV_TRADUCCION_MAX = "KENI_TRADUCCION_MAX"

# Imagen / secretos (precedencia con el fichero vive en `secretos.py`).
ENV_IMAGEN_API_KEY = "KENI_IMAGEN_API_KEY"
ENV_IMAGEN_PROVEEDOR = "KENI_IMAGEN_PROVEEDOR"

# Agencias de noticias (item F): adaptadores de fuente que descargan y normalizan notas a la
# MISMA forma que los items RSS ({titulo, resumen, enlace, fecha, fuente}). GATEADOS por
# credencial: sin clave, la fuente aparece como "pendiente/no configurada" y NO rompe el
# pipeline (degradacion honesta, igual criterio que las fuentes pendientes del Radar).
#   - Reuters Connect: una API key (Bearer). `KENI_REUTERS_BASE_URL` permite apuntar a un
#     endpoint/version concreto sin recompilar (def el publico de Reuters Connect).
#   - AFP: OAuth2 client_credentials (client_id + client_secret). `KENI_AFP_BASE_URL` igual.
ENV_REUTERS_API_KEY = "KENI_REUTERS_API_KEY"
ENV_REUTERS_BASE_URL = "KENI_REUTERS_BASE_URL"
ENV_AFP_CLIENT_ID = "KENI_AFP_CLIENT_ID"
ENV_AFP_CLIENT_SECRET = "KENI_AFP_CLIENT_SECRET"
ENV_AFP_BASE_URL = "KENI_AFP_BASE_URL"

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
# Pool de conexiones Postgres (psycopg_pool). `KENI_DB_POOL` ON/OFF (def ON) elige entre el
# pool reutilizable y el camino historico de "una conexion por operacion" (fallback de
# un-solo-flag por si el pool se porta mal en prod). `KENI_DB_POOL_MIN`/`_MAX` dimensionan el
# pool: MAX debe SUPERAR el numero de conexiones de larga duracion concurrentes (cada
# `lock_barrido` retiene una conexion entera durante su barrido) + las leases por request +
# los daemons, o el resto se quedaria esperando una conexion libre (timeout).
ENV_DB_POOL = "KENI_DB_POOL"
ENV_DB_POOL_MIN = "KENI_DB_POOL_MIN"
ENV_DB_POOL_MAX = "KENI_DB_POOL_MAX"
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
# Gate de gobernanza: minimo de aprobaciones acumuladas para PROGRAMAR (item A). Def 2
# ("cuatro ojos" reales: dos personas distintas firman antes de que entre al calendario).
MIN_APROBACIONES_DEF = 2
SESION_HORAS_DEF = 12
ADMIN_USER_DEF = "admin"
LOG_LEVEL_DEF = "INFO"
MAX_JOBS_DEF = 4
MAX_COLA_DEF = 16
# Pool Postgres: arranca pequeño (la mayoria de ops son cortas) y crece hasta el MAX. El MAX
# (12) cubre con holgura los ~4 `lock_barrido` simultaneos (cada uno retiene una conexion
# entera) + las leases por request del threadpool del back + los daemons. Subir si Postgres
# tiene `max_connections` alto y se ve `PoolTimeout` bajo carga.
DB_POOL_MIN_DEF = 2
DB_POOL_MAX_DEF = 12
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
# Retencion del historico por pieza (`metricas_pieza_snapshots`): a 4h de cadencia, 90 dias
# son ~540 puntos por pieza; la poda mantiene la tabla acotada (ADR 0007).
METRICAS_HISTORICO_RETENCION_DIAS_DEF = 90
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

# Cadencia del barrido del Investigador (Fase 1): materializa el snapshot del Radar por marca
# cada N horas. Intervalo holgado (def 6h, igual que radar-auto): el snapshot vive con un TTL
# de ~2 intervalos, asi que con 6h las lecturas sirven datos de a lo sumo medio dia.
INVESTIGADOR_INTERVALO_HORAS_DEF = 6

# Agentes de investigacion (Ola 6): cadencia holgada (def 6h, cada barrido lanza claude -p
# por brief activo). Cap bajo por barrido (def 5) para no disparar costes.
INVESTIGACION_INTERVALO_HORAS_DEF = 6
INVESTIGACION_MAX_DEF = 5

# Auto-refresco de Algoritmos: intervalo holgado (def 6h); los blogs de plataforma no
# cambian a cada minuto y no conviene martillear los feeds.
ALGORITMOS_INTERVALO_HORAS_DEF = 6

# Digest de sugerencias editoriales: 1 vez al dia, pocas plataformas por barrido (cada una
# cuesta un claude -p). Conservador a proposito.
SUGERENCIAS_EDITORIALES_INTERVALO_HORAS_DEF = 24
SUGERENCIAS_EDITORIALES_MAX_DEF = 3

# Carril Rápido de Breaking: barre cada 5 min (def) y cap 3 borradores por barrido.
BREAKING_INTERVALO_MIN_DEF = 5
BREAKING_MAX_DEF = 3

# Auto-generacion de copy (H2): barre seguido (def 1h) y con cap bajo por barrido (def 3),
# porque cada item lanza un `claude -p` (coste). El cap del worker (`KENI_MAX_JOBS`) sigue
# aplicando aguas abajo.
AUTOGEN_INTERVALO_HORAS_DEF = 1
AUTOGEN_MAX_DEF = 3

# Auto-generacion de ARTE (H2-b): mismos defaults conservadores que el auto-copy (barre
# seguido, cap bajo por barrido), porque cada item llama al proveedor de imagen (coste).
AUTOGEN_ARTE_INTERVALO_HORAS_DEF = 1
AUTOGEN_ARTE_MAX_DEF = 3

# Auto-avance "dale el OK": barre seguido (def 1h) y acota cuántas QA editoriales lanza por
# barrido (def 4), porque cada una es un `claude -p` (coste). Avanzar a en_revisión no tiene
# coste de IA; el cap solo limita los lanzamientos de QA pendiente.
AUTO_AVANCE_INTERVALO_HORAS_DEF = 1
AUTO_AVANCE_MAX_DEF = 4

# Pipeline de contenido CI→CD→QA: barrido HORARIO (def 1h) por marca y cap bajo por barrido
# (def 3), porque cada item ingerido lanza un `claude -p` (coste). El cap del worker
# (`KENI_MAX_JOBS`) sigue aplicando aguas abajo.
PIPELINE_INTERVALO_HORAS_DEF = 1
PIPELINE_MAX_DEF = 3

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


def mcp_bearer() -> str | None:
    """Bearer que protege el endpoint `/mcp` (`KENI_MCP_BEARER`; None si no esta).

    None/vacio => el servidor MCP NO se monta (apagado por defecto). Cuando esta, el
    middleware del MCP exige `Authorization: Bearer <este valor>` en cada peticion a
    `/mcp` (comparacion en tiempo constante). Es la barrera del MCP frente al exterior;
    por dentro el MCP opera la API con una sesion del usuario `mcp_usuario()`.
    """
    return _crudo(ENV_MCP_BEARER) or None


def mcp_usuario() -> str | None:
    """Usuario al que se atribuyen las acciones del MCP (`KENI_MCP_USUARIO`).

    Si no se fija, cae al admin de bootstrap (`KENI_CONSOLA_ADMIN_USER`): el dueño. None
    solo si tampoco hay admin configurado (el MCP resolvera entonces el primer admin).
    """
    return _crudo(ENV_MCP_USUARIO) or _crudo(ENV_ADMIN_USER) or None


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


def mfa_habilitado() -> bool:
    """True si el segundo factor (passkeys/WebAuthn) esta ACTIVO (`KENI_CONSOLA_MFA` afirmativo).

    Default OFF (mismo espiritu CONSERVADOR que el resto de gates): con el flag apagado, el
    login NO pide nunca un segundo factor y se comporta EXACTAMENTE como hoy. Encenderlo solo
    afecta a usuarios que YA tengan >=1 passkey (`mfa_activo`); el resto sigue entrando con
    usuario+contrasena hasta que enrolen una.
    """
    return _crudo(ENV_MFA).lower() in _VERDADEROS


def mfa_key() -> str | None:
    """Clave Fernet que firma/fecha la cookie de challenge + pre-auth WebAuthn (`KENI_CONSOLA_MFA_KEY`).

    None si no esta (vacio cuenta como no fijada). NO se valida aqui que sea una clave Fernet
    bien formada: eso lo comprueba `auth.mfa` al construir el cifrador, para REHUSAR (fail-safe)
    la ceremonia si la clave falta o es invalida, en vez de media-autenticar. SIN normalizar mas
    alla del strip: una clave Fernet es base64 url-safe sin espacios.
    """
    return _crudo(ENV_MFA_KEY) or None


def rp_id() -> str:
    """WebAuthn Relying Party ID (`KENI_CONSOLA_RP_ID`, def `localhost`).

    Es el dominio efectivo SIN esquema ni puerto. En prod debe ser `social.kenitech.io`. El
    defecto `localhost` cubre el desarrollo (`python -m keni_consola` en 127.0.0.1:8765).
    """
    return _crudo(ENV_RP_ID) or "localhost"


def rp_origenes() -> list[str]:
    """Origen(es) esperado(s) de la ceremonia WebAuthn (`KENI_CONSOLA_RP_ORIGIN`, def dev).

    Con esquema y puerto. Admite una lista separada por comas (varios origenes permitidos). El
    defecto `http://localhost:8765` cubre el desarrollo; en prod: `https://social.kenitech.io`.
    """
    crudo = _crudo(ENV_RP_ORIGIN) or "http://localhost:8765"
    return [o.strip() for o in crudo.split(",") if o.strip()]


def rp_nombre() -> str:
    """Nombre legible de la Relying Party (`KENI_CONSOLA_RP_NOMBRE`, def "Keni Social").

    Es lo que el sistema operativo muestra al crear/usar una passkey.
    """
    return _crudo(ENV_RP_NOMBRE) or "Keni Social"


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


# Herramientas VETADAS por defecto en la generacion (`--disallowed-tools`). Defensa en
# profundidad frente a prompt-injection (el contenido de usuario/RSS viaja en el prompt):
# corremos con skip-permissions para cargar skills/leer ficheros del cwd, PERO vetamos:
#   - `Bash` —el vector de MAYOR impacto: ejecucion de comandos arbitrarios, lectura/
#     exfiltracion de secretos de `/data` y del entorno—.
#   - `Write` y `Edit` —escritura/edicion de ficheros en disco—. NINGUN flujo de generacion
#     (copy-desde-nota, QA, hashtags, termometro, green, sugerencias, NI los prompts de
#     investigacion `brief-tendencias`/`termometro-mundial`) escribe ficheros: su salida es
#     SIEMPRE texto que parsea el post-procesado. Vetarlas cierra un vector de persistencia/
#     manipulacion del cwd sin afectar a ningun flujo legitimo (defensa en profundidad).
# NINGUN flujo de generacion necesita Bash/Write/Edit. Web (`WebFetch`/`WebSearch`) NO se
# veta por defecto a proposito: los prompts curados `brief-tendencias`/`termometro-mundial`
# los usan para confirmar frescura, y comparten este mismo constructor de argv. El riesgo
# residual de Web en el flujo copy-desde-nota lo cubre el delimitador con NONCE
# `<contenido_usuario_…>` (ver `dominio.generar.envolver_contenido_usuario`). Vetar Web SOLO
# en los flujos de copy/RSS/autogen/QA (que no la necesitan) exige `endurecer` por-callsite en
# cada lanzador (`api/hashtags`, `api/qa_editorial`, `api/termometro`, `dominio/green`,
# `autogen_copy`, `pipeline_contenido`, `dominio/biblioteca_lanzar`...): queda PENDIENTE de
# revision humana, porque esos lanzadores son de otros modulos (no de este endurecimiento).
# Configurable con `KENI_CLAUDE_DISALLOWED_TOOLS` (lista coma/espacio): un operador puede
# endurecer mas (p.ej. "Bash Write Edit WebFetch WebSearch") si lo desea.
CLAUDE_DISALLOWED_TOOLS_DEF = "Bash Write Edit"


def claude_disallowed_tools() -> list[str]:
    """Herramientas vetadas en la generacion (`--disallowed-tools`); lista, posiblemente vacia.

    Por defecto veta `Bash Write Edit` (`CLAUDE_DISALLOWED_TOOLS_DEF`); Web queda disponible
    para los prompts de investigacion. `KENI_CLAUDE_DISALLOWED_TOOLS` lo sobreescribe
    (separadores coma o espacio); vacio explicito ("" / solo separadores) => sin veto (lista
    vacia, para depurar). Tolerante: duplicados y espacios sobrantes se limpian conservando el
    orden.
    """
    crudo = os.environ.get(ENV_CLAUDE_DISALLOWED_TOOLS)
    if crudo is None:
        crudo = CLAUDE_DISALLOWED_TOOLS_DEF
    piezas = [p.strip() for p in crudo.replace(",", " ").split()]
    vistos: list[str] = []
    for p in piezas:
        if p and p not in vistos:
            vistos.append(p)
    return vistos


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


def metricas_historico_retencion_dias() -> int:
    """Días de retención del HISTÓRICO de métricas por pieza (`metricas_pieza_snapshots`).

    `KENI_METRICAS_HISTORICO_RETENCION_DIAS`, def 90, min 1. El daemon de refresco poda los
    snapshots más antiguos que esta ventana para acotar el crecimiento de la tabla (ADR 0007).
    """
    return _entero(
        ENV_METRICAS_HISTORICO_RETENCION_DIAS, METRICAS_HISTORICO_RETENCION_DIAS_DEF, minimo=1
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


def publicar_real_para(marca: str) -> bool:
    """True si las piezas de `marca` deben publicarse DE VERDAD.

    Mismo patrón maestro+excepción que las etapas de auto-producción: el MAESTRO global
    `KENI_PUBLICAR_REAL` debe estar ON y la marca NO debe estar EXCLUIDA (override falsy por
    marca, `KENI_PUBLICAR_REAL::marca`). Con el maestro OFF, todas van a dry-run; con el maestro
    ON, una marca excluida sigue en dry-run mientras el resto publica. `marca` vacía sigue al
    maestro (sin override no está excluida).
    """
    return publicar_real() and not marca_apagada(ENV_PUBLICAR_REAL, marca)


def auto_preaprobacion() -> bool:
    """True si la pre-aprobacion de piezas de bajo riesgo esta activa (`KENI_AUTO_PREAPROBACION`).

    Def OFF (False, conservador): la cadena de aprobacion nace toda `pendiente`. Con el flag
    a un valor afirmativo, al crear la cadena de una pieza de bajo riesgo se auto-aprueban
    los niveles inferiores (nunca el ultimo, que queda a un humano). Trazable como "auto".
    """
    return _crudo(ENV_AUTO_PREAPROBACION).lower() in _VERDADEROS


def min_aprobaciones() -> int:
    """Minimo de aprobaciones acumuladas para PROGRAMAR una pieza (`KENI_MIN_APROBACIONES`).

    Def 2 (item A: "cuatro ojos" reales). `0` (o negativo) DESACTIVA el gate (cualquier pieza
    aprobada se puede programar, comportamiento legado). Valor no entero -> def. Min 0.
    """
    return _entero(ENV_MIN_APROBACIONES, MIN_APROBACIONES_DEF, minimo=0)


def auto_qa_editorial() -> bool:
    """True si el QA editorial actua como aprobador AUTOMATICO de la cadena (`KENI_AUTO_QA_EDITORIAL`).

    Def OFF (conservador): la cadena nace toda humana. Con el flag, al crear la cadena se
    antepone un nivel automatico "QA Editorial" cuyo veredicto (🟢/🟡/🔴) aprueba/deja
    pendiente/rechaza ese primer nivel. El ultimo nivel sigue siendo humano.
    """
    return _crudo(ENV_AUTO_QA_EDITORIAL).lower() in _VERDADEROS


def radar_auto_activo() -> bool:
    """True si el daemon de auto-promocion del Radar debe arrancar (`KENI_RADAR_AUTO`).

    Def OFF (conservador): el Radar solo propone (la promocion la decide el equipo). Con el
    flag a un valor afirmativo, un hilo demonio promueve periodicamente los temas que superan
    el umbral de señal a `flujo='importante'` (origen 'radar-auto'), revisable en el tablero.
    """
    return _crudo(ENV_RADAR_AUTO).lower() in _VERDADEROS


def pipeline_lineas_activo() -> bool:
    """True si la ingesta debe auto-etiquetar línea (vertical) y origen (`KENI_PIPELINE_LINEAS`).

    Def OFF (conservador): sin el flag, la ingesta no toca etiquetas (comportamiento previo).
    Con el flag, cada pieza nueva se clasifica por palabras clave; sin línea queda con aviso.
    """
    return _crudo(ENV_PIPELINE_LINEAS).lower() in _VERDADEROS


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


def investigador_activo() -> bool:
    """True si el Investigador (snapshot del Radar por marca) debe materializar (`KENI_INVESTIGADOR`).

    Def OFF (conservador): sin el flag, el daemon arranca pero NO materializa, y los endpoints
    (Radar/Parrilla) NUNCA leen del snapshot (siguen en vivo, comportamiento de Fase 0 intacto).
    Con el flag a un valor afirmativo, el daemon escribe el snapshot por marca y los endpoints
    lo sirven (rapido, sin re-descargar fuentes) mientras este fresco.
    """
    return _crudo(ENV_INVESTIGADOR).lower() in _VERDADEROS


def investigador_intervalo_horas() -> int:
    """Cada cuantas horas barre el Investigador (`KENI_INVESTIGADOR_INTERVALO_HORAS`, def 6, min 1)."""
    return _entero(ENV_INVESTIGADOR_INTERVALO_HORAS, INVESTIGADOR_INTERVALO_HORAS_DEF, minimo=1)


def prioriza_metricas_activo() -> bool:
    """True si el score de priorizacion debe usar las metricas historicas (`KENI_PRIORIZA_METRICAS`).

    Def OFF (conservador): la lista del dia ordena EXACTAMENTE como hoy. Con el flag a un valor
    afirmativo, las piezas de marcas que historicamente RINDEN mas reciben un pequeño bonus de
    score. Aditivo y DEGRADABLE: si la fachada de metricas no esta disponible, se omite sin romper.
    """
    return _crudo(ENV_PRIORIZA_METRICAS).lower() in _VERDADEROS


def prioriza_metricas_rango() -> str:
    """Rango de metricas para el bonus de priorizacion (`KENI_PRIORIZA_METRICAS_RANGO`, def "mes").

    Es uno de los rangos que entiende la fachada de metricas ("semana"/"mes"/...). Si el valor
    es invalido, el llamante lo trata best-effort (degrada a sin bonus); no se valida aqui.
    """
    return _crudo(ENV_PRIORIZA_METRICAS_RANGO) or "mes"


def algoritmos_auto_activo() -> bool:
    """True si el daemon de auto-refresco de Algoritmos debe ingerir (`KENI_ALGORITMOS_AUTO`).

    Def OFF (conservador): la pagina Algoritmos tiene un boton "Refrescar" manual. Con el flag
    a un valor afirmativo, un hilo demonio ingiere los feeds cada N horas (solo LEE feeds RSS
    publicos y persiste noticias clasificadas; no publica ni genera nada).
    """
    return _crudo(ENV_ALGORITMOS_AUTO).lower() in _VERDADEROS


def algoritmos_intervalo_horas() -> int:
    """Cada cuantas horas ingiere el daemon de Algoritmos (`KENI_ALGORITMOS_INTERVALO_HORAS`, def 6, min 1)."""
    return _entero(ENV_ALGORITMOS_INTERVALO_HORAS, ALGORITMOS_INTERVALO_HORAS_DEF, minimo=1)


def sugerencias_editoriales_activo() -> bool:
    """True si el digest diario de sugerencias editoriales debe correr (`KENI_SUGERENCIAS_EDITORIALES`).

    Def OFF (conservador): cada barrido encola uno o varios `claude -p` (coste). Con el flag a
    un valor afirmativo, un hilo demonio propone 1 vez/dia cambios a las fichas/limites a partir
    de las noticias importantes. Las propuestas son REVISABLES; nunca se aplican solas.
    """
    return _crudo(ENV_SUGERENCIAS_EDITORIALES).lower() in _VERDADEROS


def sugerencias_editoriales_intervalo_horas() -> int:
    """Cada cuantas horas corre el digest (`KENI_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS`, def 24, min 1)."""
    return _entero(
        ENV_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS,
        SUGERENCIAS_EDITORIALES_INTERVALO_HORAS_DEF,
        minimo=1,
    )


def sugerencias_editoriales_max() -> int:
    """Maximo de plataformas a procesar por barrido (`KENI_SUGERENCIAS_EDITORIALES_MAX`, def 3, min 1).

    Cada plataforma cuesta un `claude -p`: el tope acota el gasto por dia.
    """
    return _entero(ENV_SUGERENCIAS_EDITORIALES_MAX, SUGERENCIAS_EDITORIALES_MAX_DEF, minimo=1)


def breaking_auto_activo() -> bool:
    """True si el daemon del Carril Rápido de Breaking debe barrer (`KENI_BREAKING`).

    Def OFF (conservador): el equipo prepara borradores de breaking a mano (tap en la UI).
    Con el flag a un valor afirmativo, un hilo demonio barre el snapshot del Investigador
    cada N min y pre-genera borradores para los temas breaking de Claro Sports sin draft.
    SÓLO BORRADORES: nunca publica; el aprobador humano sigue siendo obligatorio.
    """
    return _crudo(ENV_BREAKING).lower() in _VERDADEROS


def breaking_intervalo_min() -> int:
    """Cada cuantos minutos barre el daemon de breaking (`KENI_BREAKING_INTERVALO_MIN`, def 5, min 1)."""
    return _entero(ENV_BREAKING_INTERVALO_MIN, BREAKING_INTERVALO_MIN_DEF, minimo=1)


def breaking_max() -> int:
    """Maximo de borradores breaking a preparar por barrido (`KENI_BREAKING_MAX`, def 3, min 1).

    Cada item lanza un `claude -p`: el cap evita una avalancha de jobs por barrido.
    """
    return _entero(ENV_BREAKING_MAX, BREAKING_MAX_DEF, minimo=1)


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


def pipeline_activo() -> bool:
    """True si el daemon del pipeline de contenido debe BARRER (`KENI_PIPELINE`).

    Def OFF (conservador): sin el flag el comportamiento existente NO cambia (nada se ingiere/
    genera por el pipeline). Con el flag a un valor afirmativo, un hilo demonio ejecuta cada N
    horas el flujo CI→CD→QA por marca y deja borradores en la cola de revision. Nada se publica
    solo (sigue gated). El hilo arranca SIEMPRE pero, gateado, solo actua con el flag activo.
    """
    return _crudo(ENV_PIPELINE).lower() in _VERDADEROS


def pipeline_intervalo_horas() -> int:
    """Cada cuantas horas barre el pipeline de contenido (`KENI_PIPELINE_INTERVALO_HORAS`, def 1, min 1)."""
    return _entero(ENV_PIPELINE_INTERVALO_HORAS, PIPELINE_INTERVALO_HORAS_DEF, minimo=1)


def pipeline_max() -> int:
    """Maximo de temas a ingerir+generar por barrido y por marca (`KENI_PIPELINE_MAX`, def 3, min 1).

    Cada item lanza un `claude -p`: el cap evita una avalancha de jobs por barrido.
    """
    return _entero(ENV_PIPELINE_MAX, PIPELINE_MAX_DEF, minimo=1)


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


def auto_programar_activo() -> bool:
    """True si una pieza APROBADA debe encolarse SOLA a su próximo hueco (`KENI_AUTO_PROGRAMAR`).

    Def ON (a diferencia de las demás etapas auto, que son OFF): programar no gasta recursos ni
    publica —solo asigna un hueco, reversible—, y "aprobado => programado" es el flujo deseado.
    Respeta precedencia store>env>defecto; `KENI_AUTO_PROGRAMAR=0`/`no`/`off` lo apaga.
    """
    crudo = _crudo(ENV_AUTO_PROGRAMAR).lower()
    if not crudo:
        return True
    return crudo not in _FALSOS


def auto_avance_activo() -> bool:
    """True si el daemon de auto-avance "dale el OK" debe arrancar (`KENI_AUTO_AVANCE`).

    Def OFF (conservador): mandar una pieza a revisión sigue siendo manual. Con el flag, un
    hilo demonio lleva a `en_revision` las piezas listas (copy out + copy in/exención + imagen
    con formato correcto + QA 🟢/🟡) y lanza la QA editorial de las que aún no la tienen.
    """
    return _crudo(ENV_AUTO_AVANCE).lower() in _VERDADEROS


# --------------------------------------------------------------------------- #
# Exclusiones POR MARCA de las etapas de auto-producción                       #
# --------------------------------------------------------------------------- #
#
# Cada etapa (pipeline/ingesta, auto-copy, auto-arte, auto-avance) sigue gateada GLOBALMENTE por
# su flag (el daemon solo barre con el global ON). Encima de eso, una marca se puede APAGAR de
# forma explícita: un override en el store con clave `f"{ENV}::{marca}"` y valor falsy ("0"/"no")
# EXCLUYE esa marca de esa etapa. Caso de uso: el global ON produce todas las marcas; apagas
# nacion-gamer y deja de producirse, claro-sports sigue. El override SOLO excluye: no consulta el
# global (por eso las funciones de selección/barrido siguen siendo testeables con el global OFF),
# y solo tiene efecto cuando la etapa global está encendida (sin global, el daemon ni barre).

# Separador de la clave por-marca. No aparece en los ids de marca (`claro-sports`, etc.).
SEP_MARCA = "::"


def clave_por_marca(env_flag: str, marca: str) -> str:
    """Clave de store del override por-marca de una etapa: `KENI_AUTOGEN::claro-sports`."""
    return f"{env_flag}{SEP_MARCA}{marca}"


def marca_apagada(env_flag: str, marca: str) -> bool:
    """True si `marca` está EXPLÍCITAMENTE apagada para la etapa `env_flag` (override falsy).

    Solo mira el override por-marca del store; NO consulta el flag global (eso lo hace el daemon
    al decidir si barre). Sin override -> False (no excluida): la etapa corre para esa marca como
    siempre. Es la guarda que los barridos consultan para SALTAR las marcas apagadas a mano.
    """
    from . import ajustes  # perezoso: evita el ciclo config <- ajustes

    crudo = ajustes.obtener(clave_por_marca(env_flag, marca))
    if crudo is None or not crudo.strip():
        return False  # sin override explícito: la marca NO está apagada
    return crudo.strip().lower() not in _VERDADEROS


def auto_avance_intervalo_horas() -> int:
    """Cada cuantas horas barre el daemon de auto-avance (`KENI_AUTO_AVANCE_INTERVALO_HORAS`, def 1, min 1)."""
    return _entero(
        ENV_AUTO_AVANCE_INTERVALO_HORAS, AUTO_AVANCE_INTERVALO_HORAS_DEF, minimo=1
    )


def auto_avance_max() -> int:
    """Máximo de QA editoriales a lanzar por barrido de auto-avance (`KENI_AUTO_AVANCE_MAX`, def 4, min 1)."""
    return _entero(ENV_AUTO_AVANCE_MAX, AUTO_AVANCE_MAX_DEF, minimo=1)


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
# Accesores: agencias de noticias (item F) — gateadas por credencial            #
# --------------------------------------------------------------------------- #


# URLs por defecto de las agencias (override con su `*_BASE_URL`). Son los endpoints
# documentados; se centralizan aqui para no esparcir literales por el adaptador.
REUTERS_BASE_URL_DEF = "https://api.reutersconnect.com"
AFP_BASE_URL_DEF = "https://afp-apicore-prod.afp.com"


def reuters_api_key() -> str | None:
    """API key de Reuters Connect (`KENI_REUTERS_API_KEY`); None si no esta (fuente apagada)."""
    return _crudo(ENV_REUTERS_API_KEY) or None


def reuters_base_url() -> str:
    """URL base de Reuters Connect (`KENI_REUTERS_BASE_URL`, def el publico), sin barra final."""
    return (_crudo(ENV_REUTERS_BASE_URL) or REUTERS_BASE_URL_DEF).rstrip("/")


def reuters_configurado() -> bool:
    """True si Reuters tiene credencial: la fuente puede descargar (si no, queda pendiente)."""
    return bool(reuters_api_key())


def afp_client_id() -> str | None:
    """Client ID de AFP (`KENI_AFP_CLIENT_ID`); None si no esta."""
    return _crudo(ENV_AFP_CLIENT_ID) or None


def afp_client_secret() -> str | None:
    """Client secret de AFP (`KENI_AFP_CLIENT_SECRET`); None si no esta. SIN strip (sensible)."""
    valor = os.environ.get(ENV_AFP_CLIENT_SECRET)
    return valor if valor else None


def afp_base_url() -> str:
    """URL base de AFP (`KENI_AFP_BASE_URL`, def el publico), sin barra final."""
    return (_crudo(ENV_AFP_BASE_URL) or AFP_BASE_URL_DEF).rstrip("/")


def afp_configurado() -> bool:
    """True si AFP tiene AMBAS credenciales OAuth2 (si no, la fuente queda pendiente)."""
    return bool(afp_client_id() and afp_client_secret())


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


def db_pool_activado() -> bool:
    """¿Usar el pool de conexiones Postgres? (`KENI_DB_POOL`, def ON).

    Flag de revert de UN SOLO interruptor: con `KENI_DB_POOL=0` (o `false`/`no`/`off`) el
    factory vuelve al camino historico de "una conexion psycopg por operacion". Por defecto
    ON: el pool reutiliza conexiones y evita el handshake TCP+auth en el camino caliente.
    """
    crudo = _crudo(ENV_DB_POOL)
    if not crudo:
        return True  # def ON
    return crudo.lower() in _VERDADEROS


def db_pool_min() -> int:
    """Conexiones minimas que el pool mantiene abiertas (`KENI_DB_POOL_MIN`, def 2, min 0)."""
    return _entero(ENV_DB_POOL_MIN, DB_POOL_MIN_DEF, minimo=0)


def db_pool_max() -> int:
    """Conexiones maximas del pool (`KENI_DB_POOL_MAX`, def 12).

    DEBE superar las conexiones de larga duracion concurrentes (cada `lock_barrido` retiene
    una conexion entera durante su barrido) + las leases por request + los daemons, o el
    resto se quedaria esperando una conexion libre. Se fuerza `>= min` para que el pool sea
    coherente aunque alguien fije un MAX por debajo del MIN.
    """
    return max(db_pool_min(), _entero(ENV_DB_POOL_MAX, DB_POOL_MAX_DEF, minimo=1))


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


# --------------------------------------------------------------------------- #
# Accesor: insumos del día                                                     #
# --------------------------------------------------------------------------- #


def insumos_modelo() -> str:
    """Modelo de claude para parsear insumos del día (`KENI_INSUMOS_MODELO`, def "haiku").

    Si la var esta explicitamente vacia (""), devuelve "" -> el llamante NO pasa `--model`
    y claude usa su propio default. Si no esta fijada, devuelve "haiku". Si esta fijada a
    un valor no vacio, devuelve ese valor como nombre de modelo.
    """
    # _crudo() hace strip: si la var es "" o solo espacios, devuelve "".
    # Si la var no esta en el entorno, os.environ.get devuelve None -> _crudo da "".
    # Por eso chequeamos la var cruda del entorno para distinguir "no fijada" de "vacia".
    raw = os.environ.get(ENV_INSUMOS_MODELO)
    if raw is None:
        return "haiku"  # no fijada: default haiku
    return raw.strip()  # fijada: respeta el valor (puede ser "" para desactivar --model)


# --------------------------------------------------------------------------- #
# Accesores: traducción + tropicalización MX (Ola 4)                           #
# --------------------------------------------------------------------------- #


def traduccion_activa() -> bool:
    """¿Traducir temas extranjeros en el Radar? (`KENI_TRADUCCION`, def ON).

    Por defecto ACTIVO: `KENI_TRADUCCION=0` o falsy lo apaga. La traduccion usa Haiku
    (mismo modelo que insumos), es best-effort (si falla, el Radar no se rompe) y se
    acota a `traduccion_max()` temas del top.
    """
    crudo = _crudo(ENV_TRADUCCION)
    if not crudo:
        return True  # no fijada => ON por defecto
    return crudo.lower() not in _FALSOS


def traduccion_max() -> int:
    """Cap de temas extranjeros a traducir por request del Radar (`KENI_TRADUCCION_MAX`, def 15, min 1)."""
    return _entero(ENV_TRADUCCION_MAX, 15, minimo=1)


# --------------------------------------------------------------------------- #
# Accesores: agentes de investigacion (Ola 6)                                  #
# --------------------------------------------------------------------------- #


def investigacion_auto_activa() -> bool:
    """True si el daemon de investigacion debe barrer briefs activos (`KENI_INVESTIGACION_AUTO`).

    Def OFF (conservador): el daemon arranca pero no barre. Con el flag ON corre cada
    N horas y deposita candidatos para revision humana; NUNCA crea tablero solo.
    """
    return _crudo(ENV_INVESTIGACION).lower() in _VERDADEROS


def investigacion_intervalo_horas() -> int:
    """Cada cuantas horas barre el daemon de investigacion (`KENI_INVESTIGACION_INTERVALO_HORAS`, def 6, min 1)."""
    return _entero(ENV_INVESTIGACION_INTERVALO_HORAS, INVESTIGACION_INTERVALO_HORAS_DEF, minimo=1)


def investigacion_max() -> int:
    """Cap de candidatos a depositar por barrido (`KENI_INVESTIGACION_MAX`, def 5, min 1)."""
    return _entero(ENV_INVESTIGACION_MAX, INVESTIGACION_MAX_DEF, minimo=1)
