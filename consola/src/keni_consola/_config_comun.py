"""Núcleo de config: imports, constantes ENV_*, defaults, kill-switch y helpers de
lectura/parseo. Lo comparten los `config_<dominio>`; `config.py` es el barrel."""
from __future__ import annotations

import os
from collections.abc import Callable
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
# Tope ABSOLUTO de vida de una sesion (horas): la expiracion deslizante (`SESION_HORAS`) se
# renueva en cada uso, asi que una sesion activa (o robada-pero-usada) nunca caduca. Este cap,
# medido contra `creada`, la mata pasado el tope AUNQUE se siga usando. Default GENEROSO (30 d)
# para no molestar el uso normal del piloto: solo acota sesiones renovadas indefinidamente.
ENV_SESION_MAX_HORAS = "KENI_CONSOLA_SESION_MAX_HORAS"
# Longitud MINIMA de contrasena (politica global, editable desde Usuarios → Configuracion
# global). Suelo duro de 12 (NIST 800-63B); subirla endurece la politica para contrasenas
# nuevas/reseteadas. Se lee store-aware via `_crudo`/`_entero` (STORE > ENV > defecto).
ENV_PASSWORD_MIN = "KENI_CONSOLA_PASSWORD_MIN"
ENV_ADMIN_USER = "KENI_CONSOLA_ADMIN_USER"
ENV_ADMIN_PASS = "KENI_CONSOLA_ADMIN_PASS"

# MFA PASSKEYS / WebAuthn (segundo factor), GATEADO OFF por defecto. `KENI_CONSOLA_MFA`
# afirmativo activa la elevacion de login (un usuario con >=1 passkey debe completar una
# ceremonia WebAuthn tras la contrasena) y la seccion de "Llaves de acceso" en "Mi cuenta".
# Con el flag OFF el login se comporta EXACTAMENTE como hoy (nunca se pide segundo factor).
# `KENI_CONSOLA_MFA_KEY` es una clave Fernet (base64 url-safe de 32 bytes) que FIRMA y
# fecha la cookie del CHALLENGE/pre-auth de vida corta (no cifra ningun secreto: en
# passkeys el secreto vive en el dispositivo del usuario). Si el flag esta ON pero la clave
# falta/es invalida, las ceremonias REHUSAN (fail-safe, 503), nunca se media-autentica.
ENV_MFA = "KENI_CONSOLA_MFA"
ENV_MFA_KEY = "KENI_CONSOLA_MFA_KEY"
# MFA OBLIGATORIO PARA ADMINS, default ON. Un admin publica en canales de marca: un
# password robado sin segundo factor es account-takeover. Por eso, INDEPENDIENTEMENTE del
# flag global `KENI_CONSOLA_MFA`, los admins quedan sujetos al segundo factor SIEMPRE que la
# maquinaria pueda operar (hay `KENI_CONSOLA_MFA_KEY`): si ya tienen passkey, el login la
# EXIGE; si aun no, se les marca para INSCRIBIRLA (flujo de gracia, sin bloquear). Sin clave
# de firma NO se fuerza nada (no hay lockout). Se puede apagar (`KENI_CONSOLA_MFA_ADMIN=0`)
# como valvula de escape operativa. NO afecta a editores (siguen gobernados por el flag global).
ENV_MFA_ADMIN = "KENI_CONSOLA_MFA_ADMIN"
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

# Listener de CONTROL del proceso `daemons` (gestion de la cuenta de Claude: estado/uso/
# login/logout, ver `cuenta_claude` + `control`). Solo el `daemons` (imagen del worker, con
# `claude`) lo levanta; el `back` lo alcanza por la red interna y lo protege con el bearer.
# ACTIVO por defecto: el bearer back<->daemons se AUTO-PERSISTE en /data
# (`cuenta_claude.bearer_efectivo`). `KENI_CONTROL_BEARER` es un OVERRIDE opcional (avanzado).
ENV_CONTROL_BEARER = "KENI_CONTROL_BEARER"
# Puerto del listener de control (interno, nunca por Traefik). Def 8770.
ENV_CONTROL_PORT = "KENI_CONTROL_PORT"
# URL base con que el `back` alcanza el control del `daemons` (red interna docker). Def
# `http://daemons:8770`.
ENV_CONTROL_URL = "KENI_CONTROL_URL"

# Agentes Ralph (sesiones `claude` PERSISTENTES multi-turno en el servicio worker-ralph).
# Solo worker-ralph (imagen del worker, con `claude`) levanta el listener; el `back` lo
# alcanza por la red interna con el bearer compartido y lo proxea (admin-gated).
#   - KENI_RALPH_URL: URL base con que el `back` alcanza el listener (def `http://worker-ralph:8771`).
#   - KENI_RALPH_PORT: puerto del listener (interno, nunca por Traefik). Def 8771.
#   - KENI_MAX_RALPH: tope de Ralphs vivos a la vez (pool de nombres). Def 8.
#   - KENI_DEV_REPO: clon git del repo sobre el que cada Ralph crea su worktree+rama. Def `/repo`.
ENV_RALPH_URL = "KENI_RALPH_URL"
ENV_RALPH_PORT = "KENI_RALPH_PORT"
ENV_MAX_RALPH = "KENI_MAX_RALPH"
ENV_DEV_REPO = "KENI_DEV_REPO"

# Listener del carril DEV (worker-dev): promocion REAL a `main` de la rama de una sugerencia.
# Solo worker-dev (imagen del worker, con git+gh) lo levanta; el `back` lo alcanza por la red
# interna con el bearer compartido y lo proxea (admin-gated), igual que el control de `daemons`.
#   - KENI_DEV_URL: URL base con que el `back` alcanza el listener (def `http://worker-dev:8772`).
#   - KENI_DEV_PORT: puerto del listener (interno, nunca por Traefik). Def 8772.
ENV_DEV_URL = "KENI_DEV_URL"
ENV_DEV_PORT = "KENI_DEV_PORT"

# Observabilidad.
ENV_LOG_LEVEL = "KENI_CONSOLA_LOG_LEVEL"

# Concurrencia de jobs (la cola NO tiene tope: el exceso ESPERA, ver R-NO-LIMIT).
ENV_MAX_JOBS = "KENI_MAX_JOBS"

# Cola + worker de generacion (ADR 0002).
ENV_WORKER_EXTERNO = "KENI_WORKER_EXTERNO"
ENV_WORKER_SONDEO_SEGUNDOS = "KENI_WORKER_SONDEO_SEGUNDOS"
# CARRILES de cola que ESTE worker reclama (lista separada por comas). Reparte el trabajo de
# las DOS cuentas de Claude: el worker A monta `cuenta-a` ademas de inferencia/proceso y el
# worker B solo `cuenta-b`. Vacio/ausente = TODOS los carriles de contenido (inferencia, proceso,
# cuenta-a, cuenta-b): el perfil de UNA sola maquina/cuenta no orfana ningun job.
ENV_WORKER_CARRILES = "KENI_WORKER_CARRILES"

# Economia de tokens de la generacion (la suscripcion `claude` es COMPARTIDA con el equipo):
# corte DIARIO por COSTE en USD + kill switch humano (`presupuesto_ia.py`).
# Topes DIARIOS de tokens POR MOTOR (ADR 0011: investigacion vs produccion), separando ENTRADA y
# SALIDA. Cada motor corta de forma independiente con sus topes propios; el corte efectivo de un
# motor es el MAS restrictivo entre su tope IN, su tope OUT y el cap global de USD. 0 = SIN limite.
ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA = "KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA"
ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA = "KENI_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA"
ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA = "KENI_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA"
ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA = "KENI_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA"
ENV_PRESUPUESTO_USD_DIA = "KENI_PRESUPUESTO_USD_DIA"
ENV_PRESUPUESTO_MARGEN_MANUAL = "KENI_PRESUPUESTO_MARGEN_MANUAL"
ENV_GENERACION_PAUSADA = "KENI_GENERACION_PAUSADA"
# Tope de INTENTOS de ejecucion de un job de la cola (anti crash-loop del re-reclamo).
ENV_JOBS_MAX_INTENTOS = "KENI_JOBS_MAX_INTENTOS"
# Economia de CONTEXTO: tope duro y umbral de aviso del tamano del prompt por generacion.
ENV_PROMPT_MAX_CHARS = "KENI_PROMPT_MAX_CHARS"
ENV_PROMPT_AVISO_CHARS = "KENI_PROMPT_AVISO_CHARS"

# Generacion `claude -p`.
# Esfuerzo de razonamiento (`claude --effort`) de TODA la generacion. Vive en el catalogo
# de ajustes (select editable en caliente; precedencia STORE > ENV). El TOML local de
# preferencias queda solo como FALLBACK legado (ver `preferencias.obtener_esfuerzo`).
ENV_ESFUERZO = "KENI_ESFUERZO"
ENV_CLAUDE_TIMEOUT = "KENI_CLAUDE_TIMEOUT"
ENV_CLAUDE_MAX_USD = "KENI_CLAUDE_MAX_USD"
ENV_CLAUDE_MAX_TURNS = "KENI_CLAUDE_MAX_TURNS"
ENV_CLAUDE_SKIP_PERMISSIONS = "KENI_CLAUDE_SKIP_PERMISSIONS"
# Herramientas VETADAS en la generacion (`--disallowed-tools`). Defensa contra
# prompt-injection: la generacion de copy no necesita ejecutar comandos ni navegar.
ENV_CLAUDE_DISALLOWED_TOOLS = "KENI_CLAUDE_DISALLOWED_TOOLS"
# Excluir las secciones DINAMICAS del system prompt de Claude Code
# (`--exclude-dynamic-system-prompt-sections`). El copy no pasa `--system-prompt`: esas
# secciones (entorno/CWD/git) son ruido para la generacion. Def ON; falsy lo apaga.
ENV_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS = "KENI_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS"
# Persistencia de la sesion de Claude Code. El copy es one-shot: no necesita persistir la
# sesion en disco. Def "0" (NO persistir = SE añade `--no-session-persistence`); truthy la
# reactiva (NO se añade la flag). El `session_id` se sigue emitiendo en `system/init` y
# `result` aunque no se persista, asi que la captura de metricas no se ve afectada.
ENV_CLAUDE_SESSION_PERSISTENCE = "KENI_CLAUDE_SESSION_PERSISTENCE"
# Modelo(s) de FALLBACK (`--fallback-model`): si el modelo por defecto falla (sobrecarga),
# `claude` cae a estos en orden. CSV; vacio = sin fallback. El CLI acepta la lista en UN
# solo `--fallback-model <lista>`. Solo aplica cuando el run usa el modelo por defecto: si
# el job fija su propio `--model`, se respeta su eleccion (no se añade fallback).
ENV_CLAUDE_FALLBACK_MODEL = "KENI_CLAUDE_FALLBACK_MODEL"
# Etapa de COPY: enviar el contexto editorial ESTABLE de la marca (cuerpo base + linea
# editorial + indicaciones) como `--system-prompt` en vez de incrustarlo en el mensaje de
# usuario. El system queda byte-identico por marca/dia (se cachea de verdad) y el mensaje de
# usuario solo lleva lo dinamico (contrato JSON + CONTEXTO de la fuente). Def ON; falsy lo apaga
# (vuelve a un unico mensaje de usuario con todo dentro).
ENV_COPY_SYSTEM_PROMPT = "KENI_COPY_SYSTEM_PROMPT"
# Idle-timeout del stream (watchdog): un stream SILENCIOSO pero con stdout abierto dejaria el
# lector bloqueado para siempre (el wall-timeout global no se alcanza). Si pasan mas de N s sin
# una linea nueva, se mata el arbol del proceso (cierra stdout -> el lector termina). Def 90 s;
# 0 = desactivado.
ENV_CLAUDE_IDLE_TIMEOUT = "KENI_CLAUDE_IDLE_TIMEOUT"

# Almacen de prompts + linea editorial (almacen unico de documentos markdown).
ENV_PROMPTS_DIR = "KENI_PROMPTS_DIR"
# Nombre legacy de la env var (back-compat): se lee como fallback de `KENI_PROMPTS_DIR`.
ENV_PROMPTS_DIR_LEGACY = "KENI_TEXTO_DIR"

# Programadores en segundo plano.
ENV_METRICAS_REFRESCO_HORAS = "KENI_METRICAS_REFRESCO_HORAS"
# Refresco PROACTIVO de la cache de metricas POR PIEZA (tablero) — Fase 3 auto-operativa.
ENV_METRICAS_PIEZAS_REFRESCO_HORAS = "KENI_METRICAS_PIEZAS_REFRESCO_HORAS"
# Retencion (dias) del HISTORICO de metricas por pieza (`metricas_pieza_snapshots`, ADR 0007).
ENV_METRICAS_HISTORICO_RETENCION_DIAS = "KENI_METRICAS_HISTORICO_RETENCION_DIAS"
# Barrido de ALERTAS de rendimiento (emite eventos internos).
ENV_ALERTAS_INTERVALO_HORAS = "KENI_ALERTAS_RENDIMIENTO_HORAS"
ENV_ALERTAS_ACTIVAS = "KENI_ALERTAS_RENDIMIENTO"
# Umbral (% engagement) por debajo del cual una pieza publicada se considera "bajo
# rendimiento" y dispara una alerta. Def 1.0 (muy por debajo del ~2-3% tipico del piloto).
ENV_ALERTAS_UMBRAL_ENGAGEMENT = "KENI_ALERTAS_UMBRAL_ENGAGEMENT"

# Pieza real via Metricool (gate de seguridad; def OFF = dry-run).
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

# Gate de gobernanza "minimo N aprobaciones" (item A verificación/aprobaciones). Antes de PROGRAMAR una
# pieza se exige que su cadena de aprobacion acumule al menos N niveles aprobados (defecto 2:
# "cuatro ojos" reales). `KENI_MIN_APROBACIONES=0` desactiva el gate; valor invalido -> def.
ENV_MIN_APROBACIONES = "KENI_MIN_APROBACIONES"

# INTERRUPTOR GENERAL de la maquina de contenido (kill-switch GLOBAL). `KENI_MAQUINA`
# afirmativo ENCIENDE la maquina; ausente/falso la deja APAGADA (def OFF). Cuando esta OFF,
# NINGUN daemon de automatizacion de CONTENIDO corre, aunque su toggle individual este ON: es
# la condicion necesaria que se ANDea con cada toggle (ver `gate_maquina`). Cuando esta ON,
# cada subsistema sigue EXACTAMENTE su propio toggle, como hasta ahora. NO afecta a los daemons
# de mantenimiento (metricas, alertas, vencimientos, limpiador, GC de media) ni a la pieza.
ENV_MAQUINA = "KENI_MAQUINA"

# Auto-refresco de Algoritmos (inteligencia de plataforma): ingiere periodicamente los
# feeds de blogs oficiales/agregadores. Gateado OFF por defecto (la pagina Algoritmos tiene
# un boton "Refrescar" manual); con el flag ON, un daemon ingiere cada N horas.
ENV_ALGORITMOS_AUTO = "KENI_ALGORITMOS_AUTO"
ENV_ALGORITMOS_INTERVALO_HORAS = "KENI_ALGORITMOS_INTERVALO_HORAS"

# Re-derivación PERIÓDICA de los patrones editoriales por marca (Metricool -> perfil +
# doc 'patrones'). Gateado OFF por defecto; Voz/Reglas (criterio humano) jamás se tocan.
# En el catálogo de ajustes (UI) junto al resto de gates de daemons.
ENV_PATRONES_AUTO = "KENI_PATRONES_AUTO"

# Google Trends como fuente externa: el daemon ingiere las tendencias (con sus noticias) al
# pool. GATEADO OFF por defecto (KENI_TRENDS). `KENI_TRENDS_GEOS` = CSV de geos (def "MX").
ENV_TRENDS = "KENI_TRENDS"
ENV_TRENDS_INTERVALO_MIN = "KENI_TRENDS_INTERVALO_MIN"
ENV_TRENDS_GEOS = "KENI_TRENDS_GEOS"

# MOTOR DE INGESTA PERSISTENTE (Ola A): un hilo demonio sondea en background los feeds RSS
# VENCIDOS (cadencia por feed/categoría) y PERSISTE cada artículo en `noticias_items` (archivo
# a nivel de artículo). A diferencia del resto, SOLO LEE feeds públicos y persiste; no genera ni
# publica nada. Def OFF para CI/tests; se ACTIVA en producción (deploy: KENI_PIPELINE_RECOLECTAR=1). `BATCH`
# = feeds por barrido; `WORKERS` = descargas en paralelo; `MAX_ITEMS` = artículos por feed.
ENV_PIPELINE_RECOLECTAR = "KENI_PIPELINE_RECOLECTAR"
ENV_MARCAS_ACTIVAS = "KENI_MARCAS_ACTIVAS"
ENV_MARCA_NOTICIAS = "KENI_MARCA_NOTICIAS"
MARCA_NOTICIAS_DEF = "unotv"
ENV_INGESTA_BATCH = "KENI_INGESTA_BATCH"
ENV_INGESTA_WORKERS = "KENI_INGESTA_WORKERS"
ENV_INGESTA_MAX_ITEMS = "KENI_INGESTA_MAX_ITEMS"
# Cadencia por categoría (segundos). Prioritarias agresivas (~3 min), generales ~10 min, las
# de cambio lento ~30 min. Configurables por env; un feed puede sobrescribir con `intervalo_min`.
ENV_INGESTA_INTERVALO_BREAKING = "KENI_INGESTA_INTERVALO_BREAKING"
ENV_INGESTA_INTERVALO_DEPORTES = "KENI_INGESTA_INTERVALO_DEPORTES"
ENV_INGESTA_INTERVALO_MX = "KENI_INGESTA_INTERVALO_MX"
ENV_INGESTA_INTERVALO_INTERNACIONAL = "KENI_INGESTA_INTERVALO_INTERNACIONAL"
ENV_INGESTA_INTERVALO_GAMING = "KENI_INGESTA_INTERVALO_GAMING"
ENV_INGESTA_INTERVALO_EVERGREEN = "KENI_INGESTA_INTERVALO_EVERGREEN"
ENV_INGESTA_INTERVALO_DEFECTO = "KENI_INGESTA_INTERVALO_DEFECTO"

# Agrupar HISTORIAS (Ola B): ventana reciente de agrupación (dedup EXACTO: url canónica o hash de
# título) y heurística de "breaking" (N fuentes distintas en < M horas). Agrupación INCREMENTAL
# acotada por la ventana: nunca re-agrupa el archivo entero. Corre dentro del barrido de Recolectar.
ENV_CLUSTER_VENTANA_H = "KENI_CLUSTER_VENTANA_H"
# LEGADO: umbral breaking por CONTEO de fuentes. Sustituido por el umbral PONDERADO
# (`KENI_CLUSTER_BREAKING_PESO`); si el conteo está fijado y el peso no, se mapea (peso =
# conteo) para no romper despliegues configurados. Ver `config.cluster_breaking_peso()`.
ENV_CLUSTER_BREAKING_FUENTES = "KENI_CLUSTER_BREAKING_FUENTES"
ENV_CLUSTER_BREAKING_PESO = "KENI_CLUSTER_BREAKING_PESO"
# Tope EXTRA diario de breaking sobre el plan: una última hora corroborada sale al feed
# aunque su línea esté llena, hasta este máximo extra en 24 h (techo de seguridad).
ENV_BREAKING_EXTRA_DIA = "KENI_BREAKING_EXTRA_DIA"
ENV_CLUSTER_BREAKING_VENTANA_H = "KENI_CLUSTER_BREAKING_VENTANA_H"

# Pesos del ALGORITMO DE PONDERACIÓN del score de cluster (jerarquización de noticias). Editables
# por la consola para que el equipo afine la priorización sin tocar código (clamp [0,1]; default =
# los de `dominio.agrupar.PesosScore`). El daemon de Recolectar los inyecta en `agrupar.puntuar`.
ENV_SCORE_PESO_CORROBORACION = "KENI_SCORE_PESO_CORROBORACION"
ENV_SCORE_PESO_VELOCIDAD = "KENI_SCORE_PESO_VELOCIDAD"
ENV_SCORE_PESO_FRESCURA = "KENI_SCORE_PESO_FRESCURA"
ENV_SCORE_PESO_VIRALIDAD = "KENI_SCORE_PESO_VIRALIDAD"
ENV_SCORE_PESO_MARCA = "KENI_SCORE_PESO_MARCA"
ENV_SCORE_BONUS_BREAKING = "KENI_SCORE_BONUS_BREAKING"

# Monitor de COBERTURA + Traducir completo + auto-verificación (Ola D). Aditivo sobre A-C.
#   MAX_ERRORES: tras N errores seguidos el daemon AUTO-DESACTIVA el feed (deja de sondearlo).
#   FEED_SLA_MIN: un feed activo sin items nuevos en > N min cuenta como "stale" en /salud.
#   TRAD_MIN_SCORE: score mínimo de un cluster extranjero para entrar a Traducir.
#   TRAD_LOTE: clusters por barrido a Traducir (acotado; el resto se cogen en el siguiente).
#   FUENTES_BAJA_CONFIANZA: dominios/outlets agregadores/foros que marcan una historia 'dudosa'
#     si son su única fuente (lista CSV configurable).
ENV_INGESTA_MAX_ERRORES = "KENI_INGESTA_MAX_ERRORES"
ENV_FEED_SLA_MIN = "KENI_FEED_SLA_MIN"
ENV_TRAD_MIN_SCORE = "KENI_TRAD_MIN_SCORE"
ENV_TRAD_LOTE = "KENI_TRAD_LOTE"
ENV_FUENTES_BAJA_CONFIANZA = "KENI_FUENTES_BAJA_CONFIANZA"

# Pipeline de contenido Admitir→Redactar→Revisar por marca (fase3 auto-produccion). Un hilo
# demonio que, cada N horas y por marca con feeds RSS activos, admite temas frescos (Admitir),
# lanza la redaccion del copy+imagen de marca (Redactar, mismo camino que el boton manual) y revisa
# automaticamente los borradores recientes (Revisar), registrando CADA etapa en "Actividad IA" como
# un pipeline. Deja BORRADORES en la cola de revision para la aprobacion humana; NUNCA
# publica. CONSERVADOR por defecto (OFF): sin `KENI_PIPELINE_REDACTAR` el comportamiento no cambia.
ENV_PIPELINE_REDACTAR = "KENI_PIPELINE_REDACTAR"
ENV_PIPELINE_MAX = "KENI_PIPELINE_MAX"
# FLUJO CONTINUO: el pipeline no barre por tandas (sin intervalo configurable: tick corto
# constante en `pipeline_contenido._barrido`) ni tiene topes por etapa (Verificar/Redactar/Ilustrar/Revisar):
# el volumen lo regula Admitir (gate serial en proceso por marca) + el backpressure de la cola.
ENV_PIPELINE_EN_PROCESO_MAX = "KENI_PIPELINE_EN_PROCESO_MAX"  # gate serial: temas en proceso por marca
# Enriquecimiento de la NOTA de origen al Recolectar: antes de encolar el copy, el daemon descarga
# el CUERPO del/los artículo(s) (no solo el snippet RSS) y, en clusters, agrega el texto de CADA
# fuente —no solo sus URLs—. Así `claude -p` sintetiza sobre material real sin gastar turnos en
# WebFetch ni pedir permisos. CONSERVADOR por defecto (OFF): sin el flag la nota es título+resumen
# como hasta ahora. Best-effort: un fetch que falle cae a título+resumen (nunca rompe el barrido).
ENV_PIPELINE_FETCH_FUENTE = "KENI_PIPELINE_FETCH_FUENTE"  # ingerir el cuerpo del artículo en la nota
# Frescura del pipeline (ventana deslizante sobre la priorización): TTL en horas de un tema EN PROCESO.
# Lo que no se completó a tiempo CADUCA y libera su hueco; hoy entra lo de hoy, no el backlog.
ENV_PIPELINE_TEMA_TTL_HORAS = "KENI_PIPELINE_TEMA_TTL_HORAS"  # caducidad de temas en proceso

# Etapa de Verificar del pipeline: "Verificar" (`KENI_PIPELINE_VERIFICAR`, toggle de etapa por marca). Es la verificación
# de la FUENTE (pre-copy): un `claude -p` evalúa la nota de origen antes de redactar el copy. Toggle
# PROPIO (1 toggle = 1 etapa): apagarla por marca la deja como "Saltada" y el copy se genera
# igual (sin la verificación). CONSERVADOR por defecto (OFF), como el resto de etapas: sin `KENI_PIPELINE_VERIFICAR` no
# se verificación (la etapa aparece saltada). Encender desde el panel admin para activar la verificación.
ENV_PIPELINE_VERIFICAR = "KENI_PIPELINE_VERIFICAR"

# Etapa de Ilustrar del pipeline: "Ilustrar" (`KENI_PIPELINE_ILUSTRAR`, toggle de etapa). Tras la
# etapa de Redactar, el pipeline genera UNA imagen por IA (mismo proveedor que `/api/media/generar`)
# para los temas con copy pero sin imagen y la adjunta. CONSERVADOR por defecto (OFF): sin
# `KENI_PIPELINE_ILUSTRAR` no se ilustra. Sin proveedor de imagen configurado, no hace nada.
# `KENI_AUTOGEN_ARTE_MAX` acota cuántos temas se ilustran por barrido (cada uno cuesta).
ENV_PIPELINE_ILUSTRAR = "KENI_PIPELINE_ILUSTRAR"
ENV_AUTOGEN_ARTE_MAX = "KENI_AUTOGEN_ARTE_MAX"

# Etapa de Sugerir hashtags del pipeline (`KENI_PIPELINE_SUGERIR_HASHTAGS`, toggle de etapa). Tras
# Redactar, para un borrador SIN hashtags el pipeline propone (no inyecta) los hashtags más
# relevantes de la biblioteca de la marca, que el feed ofrece en gris para aceptar/rechazar. Def
# ON: la sugerencia es READ-ONLY y barata, y no toca el copy ni publica nada.
ENV_PIPELINE_SUGERIR_HASHTAGS = "KENI_PIPELINE_SUGERIR_HASHTAGS"

# Etapa de Decisor del pipeline (PREVIA a Redactar): un agente barato (Haiku) decide el CAMINO de
# cada tema —`foto` o `carrusel`— a partir de señales ligeras (nº de sub-historias, titulares,
# fuentes, evento, marca), ANTES de redactar. El camino elegido se guarda en `copy_pendiente` y
# Redactar usa el prompt del camino (foto o carrusel). CONSERVADOR por defecto (OFF): sin el flag,
# Redactar decide el formato dentro de su propio prompt (comportamiento de hoy).
ENV_PIPELINE_DECISOR = "KENI_PIPELINE_DECISOR"
# Etapa de Traducir (investigación): traduce a ES-MX los clusters extranjeros recientes. Toggle
# propio (`KENI_PIPELINE_TRADUCIR`, global + `::marca`), def ON.
ENV_PIPELINE_TRADUCIR = "KENI_PIPELINE_TRADUCIR"
# Etapa de Admitir (investigación→producción): promueve las historias verificadas del pool a temas
# en la mesa. Toggle propio (`KENI_PIPELINE_ADMITIR`, global + `::marca`), def ON; ADITIVO sobre
# Recolectar (admite solo si Recolectar Y Admitir están encendidas para la marca).
ENV_PIPELINE_ADMITIR = "KENI_PIPELINE_ADMITIR"

# Etapa de Revisar del COPY del pipeline: "Revisar" (`KENI_PIPELINE_REVISAR`, toggle de etapa).
# ANTES de que un borrador completo avance solo a la cola de revisión (etapa AVANCE), la IA "hacia
# adentro" revisa el copy generado: verificación de VOZ contra los patrones medidos de
# la marca (`patrones_marca`) + chequeo barato de COHERENCIA con la nota de origen. ADVISORY y
# SAFE-by-default (mismo patrón que `dominio.copy.verificar_voz`): NUNCA bloquea el avance ni
# descarta la pieza; si detecta algo, DEGRADA la revision (`listo`→`revisar`) y deja una nota para
# que el humano decida en la revisión. CONSERVADOR por defecto (OFF): sin el flag el avance no
# cambia. Existe la verificación de la FUENTE (Verificar, pre-copy); esto es la verificación del COPY ya redactado.
ENV_PIPELINE_REVISAR = "KENI_PIPELINE_REVISAR"

# La etapa de AVANCE (un borrador COMPLETO pasa SOLO a la cola de revisión con la misma cadena
# que el envío humano) ya NO es configurable: corre incondicionalmente bajo el maestro
# KENI_MAQUINA. «Borrador» dejó de ser un estado donde descanse una pieza completa, así que no
# hay toggle (`KENI_PIPELINE_AVANCE`) ni exclusión por marca que la apaguen.

# Crítica IA: un nivel automático "Crítica IA" se AÑADE AL FINAL de la cadena del feed (detrás
# de los dos OK humanos). Cuando los humanos cierran su parte, un `claude -p` con VISIÓN critica
# la pieza (arte sintético en marca periodística, coherencia imagen↔texto, sustancia, rigor,
# hashtags, voz) y vota ese nivel: aprueba → la pieza se programa sola; detecta un problema →
# DISLIKE de IA + comentario sin resolver, que frena la programación y deja la pieza en el feed
# para que un humano la corrija. CONSERVADOR por defecto (OFF): sin `KENI_CRITICA_IA` el flujo es
# el de hoy (dos OK humanos → programado). El humano siempre tiene la última palabra (al editar
# se reinicia la cadena; un coordinador puede `forzar`).
ENV_CRITICA_IA = "KENI_CRITICA_IA"

# Limpiador de generaciones atascadas: una generacion `ejecutando` cuyo proceso murio (reinicio/
# OOM/cuelgue) queda colgada para siempre. El limpiador la cierra como `error` pasada una
# antigüedad MUY superior al wall-timeout (asi nunca mata una viva). Siempre activo.
ENV_GENERACIONES_TTL_HORAS = "KENI_GENERACIONES_TTL_HORAS"
ENV_LIMPIADOR_INTERVALO_MIN = "KENI_LIMPIADOR_INTERVALO_MIN"

# Muestreo de fondo del USO de la cuenta de Claude: un daemon de mantenimiento sondea
# `claude -p /usage` cada N minutos y persiste el snapshot, para que el indicador de la barra
# lateral y el gate diario no dependan de que un admin abra el panel. SIEMPRE activo.
ENV_USO_MUESTREO_MIN = "KENI_USO_MUESTREO_MIN"

# Verificar la FUENTE (verificación pre-copy del pipeline): es un filtro PERMISIVO, no redaccion, asi
# que corre BARATO por defecto: modelo rapido (Haiku), esfuerzo bajo y timeout corto. Cada
# una es configurable; vacia ("") = se usa el global correspondiente.
ENV_VERIFICACION_FUENTE_MODELO = "KENI_VERIFICACION_FUENTE_MODELO"
ENV_VERIFICACION_FUENTE_ESFUERZO = "KENI_VERIFICACION_FUENTE_ESFUERZO"
ENV_VERIFICACION_FUENTE_TIMEOUT = "KENI_VERIFICACION_FUENTE_TIMEOUT"
# Corrector de temas atascados `verificacion_fuente='en_curso'`: si el lanzamiento/generacion de la verificación
# muere sin finalizador, el tema quedaba excluido para siempre de la re-verificación (y contando en
# el cupo en proceso). El limpiador resetea a "" los `en_curso` mas viejos que este TTL (minutos).
ENV_VERIFICACION_EN_CURSO_TTL_MIN = "KENI_VERIFICACION_EN_CURSO_TTL_MIN"

# Recoleccion de basura (GC) de MEDIA SUELTA (Estudio de imagen, diseno §5). El Estudio
# genera N variantes; las NO elegidas quedan como objetos sueltos en el almacen de media que
# nadie borra. Un hilo demonio barre periodicamente el almacen y borra SOLO los objetos
# SUELTOS: ni referenciados por una pieza (`imagen`) ni catalogados en catalogo-media
# y mas VIEJOS que un umbral (def 24h, para no tocar variantes recien generadas que el usuario
# aun revisa). CONSERVADOR por defecto (OFF): sin `KENI_MEDIA_GC` no se borra nada.
ENV_MEDIA_GC = "KENI_MEDIA_GC"
ENV_MEDIA_GC_INTERVALO_HORAS = "KENI_MEDIA_GC_INTERVALO_HORAS"
ENV_MEDIA_GC_ANTIGUEDAD_HORAS = "KENI_MEDIA_GC_ANTIGUEDAD_HORAS"

# GC del POOL DE NOTICIAS por RELEVANCIA (no por edad sola). Un hilo demonio barre y borra lo
# irrelevante: historias `nuevo` no llevadas al tablero, de UNA fuente, score bajo y sin actividad
# reciente, + items sueltos viejos. CONSERVA usados/ligados/corroborados/score alto/recientes.
# CONSERVADOR por defecto (OFF): sin `KENI_NOTICIAS_GC` no se borra nada.
ENV_NOTICIAS_GC = "KENI_NOTICIAS_GC"
ENV_NOTICIAS_GC_INTERVALO_HORAS = "KENI_NOTICIAS_GC_INTERVALO_HORAS"
ENV_NOTICIAS_GC_SCORE_UMBRAL = "KENI_NOTICIAS_GC_SCORE_UMBRAL"
ENV_NOTICIAS_GC_INACTIVIDAD_HORAS = "KENI_NOTICIAS_GC_INACTIVIDAD_HORAS"

# Perfil editorial por marca (Fase 2): un agente Haiku extrae las keywords/temas de la línea
# editorial (página texto) y la priorización las usa como relevancia de marca (reemplaza el diccionario
# hardcodeado). GATEADO por `KENI_PRIORIZAR_PERFIL_IA` (def OFF): sin el flag se usa el vocabulario
# base. El refresco (Haiku) corre acotado por marca + TTL en el daemon de Recolectar. (ADR 0011:
# es priorización por relevancia, no voz editorial.)
ENV_PRIORIZAR_PERFIL_IA = "KENI_PRIORIZAR_PERFIL_IA"
ENV_PERFIL_EDITORIAL_TTL_HORAS = "KENI_PERFIL_EDITORIAL_TTL_HORAS"

# Fusionar SEMÁNTICAMENTE historias del mismo evento (Fase 2b): un agente Haiku agrupa las historias
# recientes de una marca que cubren el mismo acontecimiento (titulares distintos) y el daemon las
# funde en una sola (n_fuentes real). GATEADO por `KENI_PIPELINE_FUSIONAR` (def ON: ES la vía de
# agrupación del mismo evento; la formación solo dedup-ea EXACTO). `_MAX` acota
# cuántas historias por marca se mandan a Haiku por barrido (coste/contexto).
ENV_PIPELINE_FUSIONAR = "KENI_PIPELINE_FUSIONAR"
ENV_FUSION_SEMANTICA_MAX = "KENI_FUSION_SEMANTICA_MAX"
ENV_FUSION_VENTANA_H = "KENI_FUSION_VENTANA_H"

# Señal de RENDIMIENTO en la priorización (Fase 2c): prioriza historias de las líneas editoriales que
# MEJOR funcionan en redes (Metricool). GATEADO por `KENI_RENDIMIENTO_RANKING` (def OFF). Anti-sesgo:
# una línea solo cuenta si tiene ≥ `_MIN_PIEZAS` medidas; se limita al `_TOP_N`. El peso de la señal
# en el score es `KENI_SCORE_PESO_RENDIMIENTO`.
ENV_RENDIMIENTO_RANKING = "KENI_RENDIMIENTO_RANKING"
ENV_SCORE_PESO_RENDIMIENTO = "KENI_SCORE_PESO_RENDIMIENTO"
ENV_RENDIMIENTO_TOP_N = "KENI_RENDIMIENTO_TOP_N"
ENV_RENDIMIENTO_MIN_PIEZAS = "KENI_RENDIMIENTO_MIN_PIEZAS"

# Insumos del día (cajones): modelo de parseo que usa `claude -p` para extraer los ítems
# del material diario (portal/corresponsales/reporteros/eventos_claro). Por defecto "haiku"
# (más rápido/económico para extracción estructurada). Si se deja vacío (""), no se pasa
# `--model` y `claude` usa su propio default. Ver `dominio/recibir_parse.py`.
ENV_INSUMOS_MODELO = "KENI_INSUMOS_MODELO"
# Modelo de Fusionar (fusión semántica) historias (decide qué se corrobora con qué; el juicio
# fino "mismo evento vs mismo tema" se le escapaba a haiku). Def "sonnet"; "" = sin --model.
ENV_FUSION_MODELO = "KENI_FUSION_MODELO"
# Modelo de Sugerir hashtags: elegir de una lista fija de candidatos de la marca es una tarea
# acotada, así que va con haiku por defecto (no necesita el modelo grande). Def "haiku"; "" = sin
# --model. Ver `dominio/sugerir_hashtags.py`.
ENV_HASHTAGS_MODELO = "KENI_HASHTAGS_MODELO"
# Modelo del Decisor de formato (foto vs carrusel): decisión binaria sobre señales ligeras, la
# tarea más acotada del pipeline, así que va con haiku por defecto. Def "haiku"; "" = sin --model.
# Ver `dominio/decisor.py`.
ENV_DECISOR_MODELO = "KENI_DECISOR_MODELO"
# Modelo de Redactar (copy): el copy producía con el modelo por defecto de la cuenta (Opus).
# Medido sobre generaciones reales, sonnet da copy de calidad equivalente o mejor a ~mitad de
# coste de salida. Def "sonnet"; "" = sin --model (default de la cuenta). Ver `dominio/generar.py`.
ENV_COPY_MODELO = "KENI_COPY_MODELO"

# Traducir + tropicalización MX de temas extranjeros en el Radar (Ola 4). Traducir es
# SIEMPRE ON (no tiene toggle propio: corre dentro de la etapa de Recolectar, gateada por
# KENI_PIPELINE_RECOLECTAR + KENI_MAQUINA). `KENI_TRADUCCION_MAX` acota cuántos temas extranjeros del top
# se traducen por request (def 15). Se usa el mismo modelo de `KENI_INSUMOS_MODELO` (Haiku).
ENV_TRADUCCION_MAX = "KENI_TRADUCCION_MAX"

# Imagen / secretos (precedencia con el fichero vive en `secretos.py`).
ENV_IMAGEN_API_KEY = "KENI_IMAGEN_API_KEY"
ENV_IMAGEN_PROVEEDOR = "KENI_IMAGEN_PROVEEDOR"

# Motor de VIDEO (Ola VIDEO). El render (ffmpeg) y la transcripcion (whisper.cpp `whisper-cli`,
# en `keni_consola.transcripcion`) son locales, gratuitos y BAJO DEMANDA (solo corren cuando un
# humano pulsa "Renderizar" / "Transcribir"; no hay daemon que los dispare ni consumen tokens),
# asi que NO tienen kill-switch ni estan gateados por la maquina. Aqui solo queda configuracion
# legitima del render (el modelo de whisper se resuelve en el motor compartido, KENI_WHISPER_MODEL):
#   - KENI_FFMPEG_BIN         (str, def "ffmpeg"): binario de ffmpeg (path o nombre en PATH).
#   - KENI_VIDEO_RENDER_TIMEOUT (int, def 1800 s): wall-timeout del render de un video.
ENV_FFMPEG_BIN = "KENI_FFMPEG_BIN"
ENV_VIDEO_RENDER_TIMEOUT = "KENI_VIDEO_RENDER_TIMEOUT"
FFMPEG_BIN_DEF = "ffmpeg"
VIDEO_RENDER_TIMEOUT_DEF = 1800

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

# Fotos de STOCK (ayuda visual, nunca publicable sin autorizar): APIs gratuitas para proponer
# fotos como alternativa a galería/subir/IA. Solo Pexels y Pixabay necesitan clave; Wikimedia,
# NASA y Openverse no. La etapa de arte que las busca va GATEADA por `KENI_PIPELINE_STOCK`
# (def OFF, como Ilustrar) y acota cuántos temas por barrido con `KENI_STOCK_MAX_BARRIDO`.
ENV_PEXELS_API_KEY = "KENI_PEXELS_API_KEY"
ENV_PIXABAY_API_KEY = "KENI_PIXABAY_API_KEY"
ENV_PIPELINE_STOCK = "KENI_PIPELINE_STOCK"
ENV_STOCK_MAX_BARRIDO = "KENI_STOCK_MAX_BARRIDO"
# Proveedores de stock HABILITADOS por marca: CSV de ids (`KENI_STOCK_FUENTES::<marca>`).
# Vacío = sin filtro (todas las fuentes disponibles). Lo gestiona la subpágina de Stock.
ENV_STOCK_FUENTES = "KENI_STOCK_FUENTES"

# Persistencia (ADR 0004): Postgres OBLIGATORIO para la operacional + object storage
# S3/Garage opcional para la media. NOMBRES EXACTOS de `deploy/docker-compose.yml`/
# `.env.example` (NO se renombran). `DATABASE_URL` (o sus componentes `POSTGRES_*`) es
# requerida; sin S3 cableado la media sigue en disco.
ENV_DATABASE_URL = "DATABASE_URL"
# Componentes de la conexion Postgres (mismos nombres que `deploy/.env.example` y la
# imagen oficial de Postgres). Sirven para DERIVAR `DATABASE_URL` cuando esta no se fija
# explicitamente, evitando que la password de `DATABASE_URL` se desincronice de
# `POSTGRES_PASSWORD`.
ENV_PG_USER = "POSTGRES_USER"
ENV_PG_PASSWORD = "POSTGRES_PASSWORD"
ENV_PG_DB = "POSTGRES_DB"
ENV_PG_HOST = "POSTGRES_HOST"
ENV_PG_PORT = "POSTGRES_PORT"
# Pool de conexiones Postgres (psycopg_pool). `KENI_DB_POOL` ON/OFF (def **ON**) elige entre
# el pool reutilizable (default; seguro en prod, validado contra PG real) y el camino historico
# "una conexion por operacion" (`=0`, revert de un flag). Ver `db_pool_activado()` para por que
# es seguro y por que esta OFF solo en la SUITE. `KENI_DB_POOL_MIN`/`_MAX` dimensionan el
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

# Limite de tamano (MB) de un VIDEO subido a una pieza de formato video. Def 300 MB
# (`KENI_VIDEO_MAX_MB`); el almacen lo aplica en `media.guardar_video_subida`.
ENV_VIDEO_MAX_MB = "KENI_VIDEO_MAX_MB"
VIDEO_MAX_MB_DEF = 300

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
ENV_GENERACIONES = "KENI_CONSOLA_GENERACIONES"

# --------------------------------------------------------------------------- #
# Defaults (constantes centralizadas aqui, no dispersas por modulo).           #
# --------------------------------------------------------------------------- #

HOST_DEF = "127.0.0.1"
PORT_DEF = 8765
# Gate de gobernanza: minimo de aprobaciones acumuladas para PROGRAMAR (item A). Def 2
# ("cuatro ojos" reales: dos personas distintas firman antes de que entre al calendario).
MIN_APROBACIONES_DEF = 2
SESION_HORAS_DEF = 12
# Tope absoluto de vida de sesion (horas). Def 720 = 30 dias: MUY por encima de la ventana
# deslizante (def 12h), asi nunca corta una sesion en uso normal del piloto; solo bota las que
# se renuevan indefinidamente (token vivo o robado-y-usado) pasados los 30 dias desde `creada`.
SESION_MAX_HORAS_DEF = 720
ADMIN_USER_DEF = "admin"
LOG_LEVEL_DEF = "INFO"
MAX_JOBS_DEF = 4
# Agentes Ralph: puerto del listener de worker-ralph, tope de Ralphs vivos y clon git base.
RALPH_PORT_DEF = 8771
MAX_RALPH_DEF = 8
DEV_REPO_DEF = "/repo"
# Puerto del listener de promocion del carril dev (worker-dev), interno (nunca por Traefik).
DEV_PORT_DEF = 8772
# Pool Postgres: arranca pequeño (la mayoria de ops son cortas) y crece hasta el MAX. El MAX
# (12) cubre con holgura los ~4 `lock_barrido` simultaneos (cada uno retiene una conexion
# entera) + las leases por request del threadpool del back + los daemons. Subir si Postgres
# tiene `max_connections` alto y se ve `PoolTimeout` bajo carga.
DB_POOL_MIN_DEF = 2
# 20: holgura para el threadpool del back (run_in_executor ~min(32,cpu+4)=16 en 12 vCPU) + los
# daemons + el headroom de `lock_barrido`. Las leases son CORTAS (una por operacion), asi que
# 20 sobra; por proceso, y son 3 (back/daemons/worker) -> 60 < max_connections=200 de Postgres.
DB_POOL_MAX_DEF = 20
CLAUDE_TIMEOUT_DEF = 600
# Idle-timeout (s) del watchdog del stream de `claude -p` (def 90; 0 = desactivado).
CLAUDE_IDLE_TIMEOUT_DEF = 90
# Verificar la fuente: timeout holgado (abre fuentes y busca en la web con modelo fuerte) y TTL del
# corrector de temas `en_curso` sueltos (minutos; muy superior al timeout de la verificación).
VERIFICACION_FUENTE_TIMEOUT_DEF = 600
VERIFICACION_EN_CURSO_TTL_MIN_DEF = 30
# Cadencia de sondeo de la cola por el worker (s). Bajo para que el job arranque casi
# al instante tras encolarse (la UX de "Generar" no debe notar el desacoplo).
WORKER_SONDEO_SEGUNDOS_DEF = 0.5
# Topes DIARIOS de tokens por motor, separando ENTRADA y SALIDA (dia UTC). 0 = SIN limite (defecto:
# no cambia el comportamiento; solo rige el cap global de USD hasta que se fije un valor > 0).
PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA_DEF = 0
PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA_DEF = 0
PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA_DEF = 0
PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA_DEF = 0
# Presupuesto DIARIO de coste en USD de la generacion (suma de `coste_usd` del dia UTC, ya
# calculado por job con tarifas correctas). Mejor proxy del gasto real que los tokens (un
# token de input cacheado pesa muchisimo menos que uno de salida). 0 = SIN limite (defecto:
# no cambia el comportamiento de un deploy existente; se enciende fijando un valor > 0).
PRESUPUESTO_USD_DIA_DEF = 0.0
# Margen EXTRA (%) sobre el presupuesto que se concede SOLO a los lanzamientos manuales del
# equipo cuando el fondo ya esta cortado. Al superarlo, corte TOTAL (tambien lo manual).
PRESUPUESTO_MARGEN_MANUAL_DEF = 20
# Intentos maximos de ejecucion de un job (el normal + re-reclamos de suelto). 3 da dos
# reintentos automaticos tras muertes del worker sin permitir un crash-loop infinito.
JOBS_MAX_INTENTOS_DEF = 3
# Tope DURO del prompt por generacion (chars; ~4 chars = 1 token). 200k chars ~ 50k tokens:
# muy por encima de cualquier prompt legitimo de copy; corta los patologicos (saturación de
# feeds concatenados). 0 = sin tope. El AVISO (warning + visible) salta mucho antes.
PROMPT_MAX_CHARS_DEF = 200_000
PROMPT_AVISO_CHARS_DEF = 80_000
# Cadencia del barrido de refresco de la cache de metricas (horas). "1 vez al dia importa";
# 4h da margen sin golpear las APIs externas en cada apertura.
METRICAS_REFRESCO_HORAS_DEF = 6
# Cadencia del refresco proactivo de la cache POR PIEZA (tablero). Casa con el TTL de
# `metricas_pieza` (4h): un post no cambia minuto a minuto.
METRICAS_PIEZAS_REFRESCO_HORAS_DEF = 4
# Retencion del historico por pieza (`metricas_pieza_snapshots`): a 4h de cadencia, 90 dias
# son ~540 puntos por pieza; la limpieza mantiene la tabla acotada (ADR 0007).
METRICAS_HISTORICO_RETENCION_DIAS_DEF = 90
# Cadencia del barrido de alertas de rendimiento (horas).
ALERTAS_INTERVALO_HORAS_DEF = 6
# Umbral de engagement (%) por debajo del cual una pieza dispara alerta de bajo rendimiento.
ALERTAS_UMBRAL_ENGAGEMENT_DEF = 1.0

# Auto-refresco de Algoritmos: intervalo holgado (def 6h); los blogs de plataforma no
# cambian a cada minuto y no conviene martillear los feeds.
ALGORITMOS_INTERVALO_HORAS_DEF = 6

# Google Trends: cadencia holgada (def 30 min; las tendencias no cambian al segundo).
TRENDS_INTERVALO_MIN_DEF = 30
TRENDS_GEOS_DEF = ("MX",)

# Motor de ingesta persistente (Ola A): tope de feeds por barrido, descargas en paralelo y
# artículos por feed. Defaults escalables (concurrencia ACOTADA para no abrir cientos de
# conexiones de golpe ante muchos feeds).
INGESTA_BATCH_DEF = 40
INGESTA_WORKERS_DEF = 12
INGESTA_MAX_ITEMS_DEF = 100
# Cadencia por categoría (segundos). El tablero/UI ven el archivo "vivo"; los feeds prioritarios
# se sondean agresivo y los de cambio lento con holgura.
INGESTA_INTERVALO_BREAKING_DEF = 180
INGESTA_INTERVALO_DEPORTES_DEF = 180
INGESTA_INTERVALO_MX_DEF = 600
INGESTA_INTERVALO_INTERNACIONAL_DEF = 600
INGESTA_INTERVALO_GAMING_DEF = 1800
# Cadencia EVERGREEN (ciencia y tecnología + temáticas de misión: salud, medio ambiente,
# cultura, educación, impacto social): temas de cambio lento, se sondean con holgura (~30 min).
INGESTA_INTERVALO_EVERGREEN_DEF = 1800
# Categoría desconocida / sin clasificar: cadencia general.
INGESTA_INTERVALO_DEFECTO_DEF = 600
# Tope del backoff exponencial (segundos): un feed que falla repetidamente no se pausa más de
# esto (1 hora), para que se reintente con regularidad cuando vuelva.
INGESTA_BACKOFF_TOPE_SEG = 3600

# Clustering de historias (Ola B): defaults. Ventana de 72h (una historia evoluciona varios
# días); la formación dedup-ea EXACTO (url canónica o hash de título), la agrupación del mismo
# evento con titulares distintos la hace la fusión semántica (Haiku, ON por defecto); breaking
# PONDERADO = masa de fuentes (Σ peso por outlet) >= 3.0 sumadas en la ventana ACTUAL de 6h: 3
# normales, 1 potente + 1 normal, o 2 potentes. Anclado en ahora: decae solo.
CLUSTER_VENTANA_H_DEF = 72
CLUSTER_BREAKING_FUENTES_DEF = 3  # LEGADO (conteo); ver CLUSTER_BREAKING_PESO_DEF
CLUSTER_BREAKING_PESO_DEF = 3.0
BREAKING_EXTRA_DIA_DEF = 4
CLUSTER_BREAKING_VENTANA_H_DEF = 6

# Pesos del algoritmo de ponderación del score (defaults; espejan `agrupar.PesosScore`).
# El bonus breaking es 0.0: breaking ya emerge del ranking (corroboración ponderada ×
# velocidad); el knob queda para rollback/ajuste sin tocar código.
SCORE_PESO_CORROBORACION_DEF = 0.30
SCORE_PESO_VELOCIDAD_DEF = 0.20
SCORE_PESO_FRESCURA_DEF = 0.20
SCORE_PESO_VIRALIDAD_DEF = 0.10
SCORE_PESO_MARCA_DEF = 0.20
SCORE_BONUS_BREAKING_DEF = 0.0

# Monitor de cobertura + traducción + verificación (Ola D): defaults.
#   8 errores seguidos ya es señal robusta de feed muerto (con backoff, son horas de fallos).
#   SLA de frescura por feed: 180 min (3h) sin items nuevos en un feed activo = "stale".
#   Umbral de score 0 = traducir TODO cluster extranjero reciente (sin filtro de relevancia);
#   subirlo limita Traducir a historias más relevantes. Lote de 40 por barrido para no
#   saturar Haiku (el backlog se procesa a lo largo de varios barridos, sin tope artificial).
INGESTA_MAX_ERRORES_DEF = 8
FEED_SLA_MIN_DEF = 180
TRAD_MIN_SCORE_DEF = 0.0
TRAD_LOTE_DEF = 40
# Outlets/agregadores de baja confianza: una historia cuya ÚNICA fuente es uno de estos se
# marca 'dudosa' (no corroborada por una fuente fiable). CSV configurable por env/ajustes; se
# compara contra el host del item y contra su `fuente_nombre`, normalizados a minúsculas.
FUENTES_BAJA_CONFIANZA_DEF: tuple[str, ...] = (
    "reddit.com",
    "t.me",
    "telegram",
    "4chan",
    "medium.com",
    "blogspot.com",
    "wordpress.com",
    "substack.com",
)

# Etapa de Ilustrar del pipeline: cap bajo por barrido (def 3), porque cada item llama al
# proveedor de imagen (coste).
AUTOGEN_ARTE_MAX_DEF = 3

# Pipeline de contenido (FLUJO CONTINUO): Admitir admite hasta este nº de historias por
# marca en cada pasada, acotada además por el gate serial en proceso. Cada admisión acaba en
# `claude -p` (coste); el cap del worker (`KENI_MAX_JOBS`) sigue aplicando más adelante en el flujo.
PIPELINE_MAX_DEF = 3
# WIP del gate serial: piezas EN PROCESO (sin terminar Verificar→Redactar) por marca. ES el regulador del
# flujo continuo: in=out (no se admite más hasta que algo sale por el otro lado).
PIPELINE_EN_PROCESO_MAX_DEF = 8
# TTL por defecto de un tema EN PROCESO (horas): un día. "Lo que no entró ayer no entra hoy":
# el pipeline prioriza siempre lo fresco de la priorización, nunca arrastra backlog.
PIPELINE_TEMA_TTL_HORAS_DEF = 24


# Limpiador de generaciones: TTL 1h (>> wall-timeout de ~10 min, asi no toca jobs vivos) y
# barrido cada 10 min. El barrido tambien corre al arrancar (limpia los sueltos del crash
# anterior de inmediato).
GENERACIONES_TTL_HORAS_DEF = 1
LIMPIADOR_INTERVALO_MIN_DEF = 10

# Cadencia del muestreo de uso de la cuenta (def 20 min): suficiente para alimentar el
# indicador y el gate sin aporrear `claude -p /usage` (cada lectura es un roundtrip a Anthropic).
USO_MUESTREO_MIN_DEF = 20

# Recoleccion de basura de media suelta (Estudio §5). Barre 1 vez al dia (no urge: el
# almacen crece lento) y solo borra objetos mas viejos que ANTIGUEDAD (def 24h), para NO
# tocar las variantes recien generadas que el usuario aun esta revisando en el Estudio.
MEDIA_GC_INTERVALO_HORAS_DEF = 24
MEDIA_GC_ANTIGUEDAD_HORAS_DEF = 24

# GC del pool de noticias: cada 6h; purga historias con score < 0.15 (basura) e inactivas > 48h.
NOTICIAS_GC_INTERVALO_HORAS_DEF = 6
NOTICIAS_GC_SCORE_UMBRAL_DEF = 0.15
NOTICIAS_GC_INACTIVIDAD_HORAS_DEF = 48

# Perfil editorial: se re-extrae con Haiku cada 24h (o si cambia la línea editorial).
PERFIL_EDITORIAL_TTL_HORAS_DEF = 24

# Fusionar (semántica): hasta 80 historias por marca y barrido se mandan a Haiku a agrupar. El
# lote toma las más recientes (`clusters_recientes` viene `ultimo_visto` desc): un evento muy
# cubierto se fragmenta en muchos clusters (la formación dedup-ea EXACTO, no fusiona titulares
# distintos) y todos son recientes a la vez; un cap holgado los funde en UNA pasada en vez de
# dejar la cola para la siguiente (donde cada fragmento compite por separado con corroboración ~0).
FUSION_SEMANTICA_MAX_DEF = 80
# Ventana de FRESCURA (horas) del lote de fusión/macro-evento: más corta que la de agrupación
# (72h). Un cluster sin actividad nueva en esta ventana ya se digirió y no se reenvía al LLM de
# fusión/macro en cada barrido; si recibe un item nuevo su `ultimo_visto` avanza y reentra.
FUSION_VENTANA_H_DEF = 48

# Rendimiento en la priorización (Fase 2c): peso de la señal (0.15), top-3 líneas, muestra mínima 5.
SCORE_PESO_RENDIMIENTO_DEF = 0.15
RENDIMIENTO_TOP_N_DEF = 3
RENDIMIENTO_MIN_PIEZAS_DEF = 5

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


def _leer_secreto_fichero(nombre: str) -> str | None:
    """Lee un secreto del fichero apuntado por la env `<nombre>_FILE` (convencion de
    Docker secrets: el valor vive en /run/secrets/... y NO en la env, asi no aparece en
    `docker inspect`). None si la env `_FILE` no esta, el fichero no existe o esta vacio.
    Quita solo el salto de linea final (artefacto del fichero); preserva espacios
    significativos para secretos que asi lo requieran (contrasenas, claves S3)."""
    ruta = os.environ.get(nombre + "_FILE")
    if not ruta:
        return None
    try:
        return Path(ruta).read_text(encoding="utf-8").rstrip("\n") or None
    except OSError:
        return None


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
    valor = os.environ.get(nombre)
    if not valor:
        valor = _leer_secreto_fichero(nombre)
    return (valor or "").strip()


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
# Interruptor GENERAL de la maquina de contenido (kill-switch global)          #
# --------------------------------------------------------------------------- #


def maquina_activa() -> bool:
    """True si la MAQUINA DE CONTENIDO esta encendida globalmente (`KENI_MAQUINA`).

    Def OFF (kill-switch CONSERVADOR): con el interruptor general APAGADO, NINGUN daemon de
    automatizacion de CONTENIDO corre, aunque su toggle individual este ON. Con el interruptor
    ENCENDIDO, cada subsistema sigue EXACTAMENTE su propio toggle (este flag deja de restar).
    Mismo idiom de parseo que el resto de flags (`_crudo(...).lower() in _VERDADEROS`).
    """
    return _crudo(ENV_MAQUINA).lower() in _VERDADEROS


def gate_maquina(accesor: Callable[[], bool]) -> Callable[[], bool]:
    """Envuelve el accesor de un daemon de contenido con el interruptor general (AND).

    Devuelve un nuevo accesor `lambda: maquina_activa() and accesor()`: el daemon corre solo si
    la maquina esta encendida Y su propio toggle esta ON. NO cambia la semantica del accesor
    interno (que se sigue exponiendo intacto para tests y para la UI de ajustes); solo el
    GATEADO del daemon (su `activo_fn`) pasa por aqui. Se evalua en cada ciclo (lectura en
    tiempo de llamada), igual que los accesores envueltos, asi el toggle responde en caliente.
    """
    return lambda: maquina_activa() and accesor()



__all__ = [
    'ADMIN_USER_DEF',
    'ALERTAS_INTERVALO_HORAS_DEF',
    'ALERTAS_UMBRAL_ENGAGEMENT_DEF',
    'ALGORITMOS_INTERVALO_HORAS_DEF',
    'AUTOGEN_ARTE_MAX_DEF',
    'CLAUDE_TIMEOUT_DEF',
    'CLAUDE_IDLE_TIMEOUT_DEF',
    'VERIFICACION_EN_CURSO_TTL_MIN_DEF',
    'VERIFICACION_FUENTE_TIMEOUT_DEF',
    'CLUSTER_BREAKING_FUENTES_DEF',
    'BREAKING_EXTRA_DIA_DEF',
    'CLUSTER_BREAKING_PESO_DEF',
    'CLUSTER_BREAKING_VENTANA_H_DEF',
    'CLUSTER_VENTANA_H_DEF',
    'Callable',
    'DB_POOL_MAX_DEF',
    'DB_POOL_MIN_DEF',
    'ENV_ADMIN_PASS',
    'ENV_ADMIN_USER',
    'ENV_AFP_BASE_URL',
    'ENV_AFP_CLIENT_ID',
    'ENV_AFP_CLIENT_SECRET',
    'ENV_AJUSTES',
    'ENV_ALERTAS_ACTIVAS',
    'ENV_ALERTAS_INTERVALO_HORAS',
    'ENV_ALERTAS_UMBRAL_ENGAGEMENT',
    'ENV_ALGORITMOS_AUTO',
    'ENV_ALGORITMOS_INTERVALO_HORAS',
    'ENV_PIPELINE_ILUSTRAR',
    'ENV_PIPELINE_STOCK',
    'ENV_STOCK_MAX_BARRIDO',
    'ENV_STOCK_FUENTES',
    'ENV_PEXELS_API_KEY',
    'ENV_PIXABAY_API_KEY',
    'ENV_PIPELINE_SUGERIR_HASHTAGS',
    'ENV_PIPELINE_DECISOR',
    'ENV_PIPELINE_TRADUCIR',
    'ENV_PIPELINE_ADMITIR',
    'ENV_AUTOGEN_ARTE_MAX',
    'ENV_AUTO_PREAPROBACION',
    'ENV_PROMPTS_DIR',
    'ENV_PROMPTS_DIR_LEGACY',
    'ENV_CLAUDE_DISALLOWED_TOOLS',
    'ENV_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS',
    'ENV_CLAUDE_FALLBACK_MODEL',
    'ENV_COPY_SYSTEM_PROMPT',
    'ENV_CLAUDE_IDLE_TIMEOUT',
    'ENV_CLAUDE_MAX_TURNS',
    'ENV_CLAUDE_MAX_USD',
    'ENV_CLAUDE_SESSION_PERSISTENCE',
    'ENV_CLAUDE_SKIP_PERMISSIONS',
    'ENV_CLAUDE_TIMEOUT',
    'ENV_CLUSTER_BREAKING_FUENTES',
    'ENV_BREAKING_EXTRA_DIA',
    'ENV_CLUSTER_BREAKING_PESO',
    'ENV_CLUSTER_BREAKING_VENTANA_H',
    'ENV_CLUSTER_VENTANA_H',
    'ENV_CONSOLA_URL_PUBLICA',
    'ENV_COOKIE_SECURE',
    'ENV_DATABASE_URL',
    'ENV_DATA_DIR',
    'ENV_DB_POOL',
    'ENV_DB_POOL_MAX',
    'ENV_DB_POOL_MIN',
    'ENV_ESFUERZO',
    'ENV_FEED_SLA_MIN',
    'ENV_PIPELINE_FUSIONAR',
    'ENV_FUSION_SEMANTICA_MAX',
    'ENV_FUSION_VENTANA_H',
    'ENV_FFMPEG_BIN',
    'ENV_FUENTES_BAJA_CONFIANZA',
    'ENV_GENERACIONES',
    'ENV_GENERACIONES_TTL_HORAS',
    'ENV_HOST',
    'ENV_HTTPS',
    'ENV_IMAGEN_API_KEY',
    'ENV_IMAGEN_PROVEEDOR',
    'ENV_INDICE',
    'ENV_PIPELINE_RECOLECTAR',
    'ENV_INGESTA_BATCH',
    'ENV_INGESTA_INTERVALO_BREAKING',
    'ENV_INGESTA_INTERVALO_DEFECTO',
    'ENV_INGESTA_INTERVALO_DEPORTES',
    'ENV_INGESTA_INTERVALO_GAMING',
    'ENV_INGESTA_INTERVALO_INTERNACIONAL',
    'ENV_INGESTA_INTERVALO_MX',
    'ENV_INGESTA_INTERVALO_EVERGREEN',
    'ENV_INGESTA_MAX_ERRORES',
    'ENV_INGESTA_MAX_ITEMS',
    'ENV_INGESTA_WORKERS',
    'ENV_FUSION_MODELO',
    'ENV_HASHTAGS_MODELO',
    'ENV_DECISOR_MODELO',
    'ENV_COPY_MODELO',
    'ENV_INSUMOS_MODELO',
    'ENV_LOG_LEVEL',
    'ENV_MAQUINA',
    'ENV_MAX_JOBS',
    'ENV_CONTROL_BEARER',
    'ENV_CONTROL_PORT',
    'ENV_CONTROL_URL',
    'ENV_MCP_BEARER',
    'ENV_MCP_USUARIO',
    'ENV_MEDIA',
    'ENV_MEDIA_GC',
    'ENV_MEDIA_GC_ANTIGUEDAD_HORAS',
    'ENV_MEDIA_GC_INTERVALO_HORAS',
    'ENV_METRICAS_HISTORICO_RETENCION_DIAS',
    'ENV_METRICAS_PIEZAS_REFRESCO_HORAS',
    'ENV_METRICAS_REFRESCO_HORAS',
    'ENV_MFA',
    'ENV_MFA_KEY',
    'ENV_MIN_APROBACIONES',
    'ENV_NOTICIAS_GC',
    'ENV_NOTICIAS_GC_INACTIVIDAD_HORAS',
    'ENV_NOTICIAS_GC_INTERVALO_HORAS',
    'ENV_NOTICIAS_GC_SCORE_UMBRAL',
    'ENV_ORIGENES',
    'ENV_PRIORIZAR_PERFIL_IA',
    'ENV_PATRONES_AUTO',
    'ENV_PERFIL_EDITORIAL_TTL_HORAS',
    'ENV_PG_DB',
    'ENV_PG_HOST',
    'ENV_PG_PASSWORD',
    'ENV_PG_PORT',
    'ENV_PG_USER',
    'ENV_PIPELINE_REDACTAR',
    'ENV_PIPELINE_MAX',
    'ENV_PIPELINE_EN_PROCESO_MAX',
    'ENV_PIPELINE_TEMA_TTL_HORAS',
    'ENV_PORT',
    'ENV_PREFERENCIAS',
    'ENV_PRESUPUESTO_MARGEN_MANUAL',
    'ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA',
    'ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA',
    'ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA',
    'ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA',
    'ENV_PRESUPUESTO_USD_DIA',
    'ENV_GENERACION_PAUSADA',
    'ENV_JOBS_MAX_INTENTOS',
    'ENV_PROMPT_MAX_CHARS',
    'ENV_PROMPT_AVISO_CHARS',
    'ENV_PUBLICAR_REAL',
    'ENV_PIPELINE_VERIFICAR',
    'ENV_VERIFICACION_EN_CURSO_TTL_MIN',
    'ENV_VERIFICACION_FUENTE_ESFUERZO',
    'ENV_VERIFICACION_FUENTE_MODELO',
    'ENV_VERIFICACION_FUENTE_TIMEOUT',
    'ENV_RAIZ',
    'ENV_LIMPIADOR_INTERVALO_MIN',
    'ENV_USO_MUESTREO_MIN',
    'ENV_RENDIMIENTO_MIN_PIEZAS',
    'ENV_RENDIMIENTO_RANKING',
    'ENV_RENDIMIENTO_TOP_N',
    'ENV_REUTERS_API_KEY',
    'ENV_REUTERS_BASE_URL',
    'ENV_RP_ID',
    'ENV_RP_NOMBRE',
    'ENV_RP_ORIGIN',
    'ENV_S3_ACCESS_KEY',
    'ENV_S3_BUCKET',
    'ENV_S3_ENDPOINT',
    'ENV_S3_REGION',
    'ENV_S3_SECRET_KEY',
    'ENV_SCORE_BONUS_BREAKING',
    'ENV_SCORE_PESO_RENDIMIENTO',
    'ENV_SCORE_PESO_CORROBORACION',
    'ENV_SCORE_PESO_FRESCURA',
    'ENV_SCORE_PESO_MARCA',
    'ENV_SCORE_PESO_VELOCIDAD',
    'ENV_SCORE_PESO_VIRALIDAD',
    'ENV_SECRETOS',
    'ENV_PASSWORD_MIN',
    'ENV_SESION_HORAS',
    'ENV_SESION_MAX_HORAS',
    'ENV_SUGERENCIAS',
    'ENV_TOKEN',
    'ENV_TRADUCCION_MAX',
    'ENV_TRAD_LOTE',
    'ENV_TRAD_MIN_SCORE',
    'ENV_TRENDS',
    'ENV_TRENDS_GEOS',
    'ENV_TRENDS_INTERVALO_MIN',
    'ENV_VIDEO_MAX_MB',
    'ENV_VIDEO_RENDER_TIMEOUT',
    'ENV_WORKER_CARRILES',
    'ENV_WORKER_EXTERNO',
    'ENV_WORKER_SONDEO_SEGUNDOS',
    'FEED_SLA_MIN_DEF',
    'FFMPEG_BIN_DEF',
    'FUENTES_BAJA_CONFIANZA_DEF',
    'FUSION_SEMANTICA_MAX_DEF',
    'FUSION_VENTANA_H_DEF',
    'GENERACIONES_TTL_HORAS_DEF',
    'HOST_DEF',
    'INGESTA_BACKOFF_TOPE_SEG',
    'INGESTA_BATCH_DEF',
    'INGESTA_INTERVALO_BREAKING_DEF',
    'INGESTA_INTERVALO_DEFECTO_DEF',
    'INGESTA_INTERVALO_DEPORTES_DEF',
    'INGESTA_INTERVALO_GAMING_DEF',
    'INGESTA_INTERVALO_INTERNACIONAL_DEF',
    'INGESTA_INTERVALO_MX_DEF',
    'INGESTA_INTERVALO_EVERGREEN_DEF',
    'INGESTA_MAX_ERRORES_DEF',
    'INGESTA_MAX_ITEMS_DEF',
    'INGESTA_WORKERS_DEF',
    'LOG_LEVEL_DEF',
    'JOBS_MAX_INTENTOS_DEF',
    'PROMPT_MAX_CHARS_DEF',
    'PROMPT_AVISO_CHARS_DEF',
    'MAX_JOBS_DEF',
    'PRESUPUESTO_MARGEN_MANUAL_DEF',
    'PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA_DEF',
    'PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA_DEF',
    'PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA_DEF',
    'PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA_DEF',
    'PRESUPUESTO_USD_DIA_DEF',
    'MEDIA_GC_ANTIGUEDAD_HORAS_DEF',
    'MEDIA_GC_INTERVALO_HORAS_DEF',
    'METRICAS_HISTORICO_RETENCION_DIAS_DEF',
    'METRICAS_PIEZAS_REFRESCO_HORAS_DEF',
    'METRICAS_REFRESCO_HORAS_DEF',
    'MIN_APROBACIONES_DEF',
    'NOTICIAS_GC_INACTIVIDAD_HORAS_DEF',
    'NOTICIAS_GC_INTERVALO_HORAS_DEF',
    'NOTICIAS_GC_SCORE_UMBRAL_DEF',
    'PERFIL_EDITORIAL_TTL_HORAS_DEF',
    'PIPELINE_MAX_DEF',
    'PIPELINE_EN_PROCESO_MAX_DEF',
    'PIPELINE_TEMA_TTL_HORAS_DEF',
    'PORT_DEF',
    'Path',
    'LIMPIADOR_INTERVALO_MIN_DEF',
    'USO_MUESTREO_MIN_DEF',
    'RENDIMIENTO_MIN_PIEZAS_DEF',
    'RENDIMIENTO_TOP_N_DEF',
    'S3_BUCKET_DEF',
    'S3_REGION_DEF',
    'SCORE_BONUS_BREAKING_DEF',
    'SCORE_PESO_CORROBORACION_DEF',
    'SCORE_PESO_FRESCURA_DEF',
    'SCORE_PESO_MARCA_DEF',
    'SCORE_PESO_RENDIMIENTO_DEF',
    'SCORE_PESO_VELOCIDAD_DEF',
    'SCORE_PESO_VIRALIDAD_DEF',
    'SESION_HORAS_DEF',
    'SESION_MAX_HORAS_DEF',
    'TRAD_LOTE_DEF',
    'TRAD_MIN_SCORE_DEF',
    'TRENDS_GEOS_DEF',
    'TRENDS_INTERVALO_MIN_DEF',
    'VIDEO_MAX_MB_DEF',
    'VIDEO_RENDER_TIMEOUT_DEF',
    'WORKER_SONDEO_SEGUNDOS_DEF',
    '_FALSOS',
    '_VERDADEROS',
    '_crudo',
    '_entero',
    '_leer_secreto_fichero',
    'annotations',
    'gate_maquina',
    'maquina_activa',
    'os',
    'quote',
]
