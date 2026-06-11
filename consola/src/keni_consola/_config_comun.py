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

# Economia de tokens de la generacion (la suscripcion `claude` es COMPARTIDA con el equipo):
# presupuesto DIARIO de tokens con corte automatico + kill switch humano (`presupuesto_ia.py`).
ENV_PRESUPUESTO_TOKENS_DIA = "KENI_PRESUPUESTO_TOKENS_DIA"
ENV_PRESUPUESTO_MARGEN_MANUAL = "KENI_PRESUPUESTO_MARGEN_MANUAL"
ENV_GENERACION_PAUSADA = "KENI_GENERACION_PAUSADA"
# Tope de INTENTOS de ejecucion de un job de la cola (anti crash-loop del re-reclamo).
ENV_JOBS_MAX_INTENTOS = "KENI_JOBS_MAX_INTENTOS"
# Economia de CONTEXTO: tope duro y umbral de aviso del tamano del prompt por generacion.
ENV_PROMPT_MAX_CHARS = "KENI_PROMPT_MAX_CHARS"
ENV_PROMPT_AVISO_CHARS = "KENI_PROMPT_AVISO_CHARS"

# Generacion `claude -p`.
ENV_CLAUDE_TIMEOUT = "KENI_CLAUDE_TIMEOUT"
ENV_CLAUDE_MAX_USD = "KENI_CLAUDE_MAX_USD"
ENV_CLAUDE_MAX_TURNS = "KENI_CLAUDE_MAX_TURNS"
ENV_CLAUDE_SKIP_PERMISSIONS = "KENI_CLAUDE_SKIP_PERMISSIONS"
# Herramientas VETADAS en la generacion (`--disallowed-tools`). Defensa contra
# prompt-injection: la generacion de copy no necesita ejecutar comandos ni navegar.
ENV_CLAUDE_DISALLOWED_TOOLS = "KENI_CLAUDE_DISALLOWED_TOOLS"

# Texto de prompts + linea editorial (almacen unico de documentos markdown).
ENV_TEXTO_DIR = "KENI_TEXTO_DIR"

# Programadores en segundo plano.
ENV_COMERCIAL_INTERVALO_SEGUNDOS = "KENI_COMERCIAL_INTERVALO_SEGUNDOS"
ENV_COMERCIAL_INTERVALO_HORAS = "KENI_COMERCIAL_INTERVALO_HORAS"
ENV_PROGRAMADOR_INTERVALO_SEGUNDOS = "KENI_PROGRAMADOR_INTERVALO_SEGUNDOS"
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

# INTERRUPTOR GENERAL de la maquina de contenido (kill-switch GLOBAL). `KENI_MAQUINA`
# afirmativo ENCIENDE la maquina; ausente/falso la deja APAGADA (def OFF). Cuando esta OFF,
# NINGUN daemon de automatizacion de CONTENIDO corre, aunque su toggle individual este ON: es
# la condicion necesaria que se ANDea con cada toggle (ver `gate_maquina`). Cuando esta ON,
# cada subsistema sigue EXACTAMENTE su propio toggle, como hasta ahora. NO afecta a los daemons
# de mantenimiento (metricas, alertas, vencimientos, reaper, GC de media) ni a la publicacion.
ENV_MAQUINA = "KENI_MAQUINA"

# Investigador (Fase 1): daemon que MATERIALIZA por marca un snapshot del Radar (temas
# consolidados + score/razon/estado) en Postgres, para que la Parrilla y el Radar lean del
# snapshot (rapido, sin re-descargar fuentes) en vez de golpear Trends/feeds en cada request.
# CONSERVADOR por defecto (OFF): sin el flag, el snapshot NUNCA se lee (los endpoints siguen
# en vivo, comportamiento de Fase 0 intacto) y el daemon arranca pero no materializa nada.
ENV_INVESTIGADOR = "KENI_INVESTIGADOR"
ENV_INVESTIGADOR_INTERVALO_HORAS = "KENI_INVESTIGADOR_INTERVALO_HORAS"

# (El antiguo KENI_PRIORIZA_METRICAS / _RANGO del "loop de aprendizaje Fase 5" se RETIRO:
# nunca tuvo llamador productivo. La señal de metricas en el ranking vive ahora en
# KENI_RENDIMIENTO_RANKING + KENI_SCORE_PESO_RENDIMIENTO, sobre las historias del pool.)

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

# Google Trends como fuente externa: el daemon ingiere las tendencias (con sus noticias) al
# pool. GATEADO OFF por defecto (KENI_TRENDS). `KENI_TRENDS_GEOS` = CSV de geos (def "MX").
ENV_TRENDS = "KENI_TRENDS"
ENV_TRENDS_INTERVALO_MIN = "KENI_TRENDS_INTERVALO_MIN"
ENV_TRENDS_GEOS = "KENI_TRENDS_GEOS"

# MOTOR DE INGESTA PERSISTENTE (Ola A): un hilo demonio sondea en background los feeds RSS
# VENCIDOS (cadencia por feed/categoría) y PERSISTE cada artículo en `noticias_items` (archivo
# a nivel de artículo). A diferencia del resto, SOLO LEE feeds públicos y persiste; no genera ni
# publica nada. Def OFF para CI/tests; se ACTIVA en producción (deploy: KENI_PIPELINE_SELECCION=1). `BATCH`
# = feeds por barrido; `WORKERS` = descargas en paralelo; `MAX_ITEMS` = artículos por feed.
ENV_PIPELINE_SELECCION = "KENI_PIPELINE_SELECCION"
# Encaje de MARCA con IA (Haiku) para historias sin marca (Trends/agencias). Cuando el
# vocabulario no las encaja quedan con marca='' e invisibles/no-promovibles; con este flag ON
# un breaking sin marca se clasifica en una de `KENI_MARCAS_ACTIVAS` (o cae a `KENI_MARCA_NOTICIAS`
# como catch-all). Def OFF: gasta tokens, se activa a propósito. `MARCAS_ACTIVAS` = candidatas (CSV
# de ids); `MARCA_NOTICIAS` = la de noticias generales (fallback ante duda/fallo).
ENV_CLASIFICAR_MARCA_IA = "KENI_CLASIFICAR_MARCA_IA"
ENV_MARCAS_ACTIVAS = "KENI_MARCAS_ACTIVAS"
ENV_MARCA_NOTICIAS = "KENI_MARCA_NOTICIAS"
# Piloto AMX: noticias (unotv), deportes (claro-sports), gaming (nacion-gamer). El resto de
# marcas no participan en el encaje automático mientras no se añadan aquí.
MARCAS_ACTIVAS_DEF = "unotv,claro-sports,nacion-gamer"
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
ENV_INGESTA_INTERVALO_TENDENCIAS = "KENI_INGESTA_INTERVALO_TENDENCIAS"
ENV_INGESTA_INTERVALO_CIENCIA_TECH = "KENI_INGESTA_INTERVALO_CIENCIA_TECH"
ENV_INGESTA_INTERVALO_GAMING = "KENI_INGESTA_INTERVALO_GAMING"
ENV_INGESTA_INTERVALO_DEFECTO = "KENI_INGESTA_INTERVALO_DEFECTO"

# Clustering de HISTORIAS (Ola B): ventana reciente de agrupación, umbral fuzzy de cruce de
# títulos y heurística de "breaking" (N fuentes distintas en < M horas). Clustering INCREMENTAL
# acotado por la ventana: nunca re-cluster el archivo entero. Corre dentro del barrido de ingesta.
ENV_CLUSTER_VENTANA_H = "KENI_CLUSTER_VENTANA_H"
ENV_CLUSTER_UMBRAL = "KENI_CLUSTER_UMBRAL"
# Umbral del MERGE LÉXICO TARDÍO de la ventana (fundir historias ya formadas que se
# descubren iguales): MÁS estricto que el de asignación. 0 = apagado.
ENV_CLUSTER_UMBRAL_MERGE = "KENI_CLUSTER_UMBRAL_MERGE"
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
# por la consola para que el equipo afine el ranking sin tocar código (clamp [0,1]; default =
# los de `dominio.clustering.PesosScore`). El daemon de ingesta los inyecta en `clustering.puntuar`.
ENV_SCORE_PESO_CORROBORACION = "KENI_SCORE_PESO_CORROBORACION"
ENV_SCORE_PESO_VELOCIDAD = "KENI_SCORE_PESO_VELOCIDAD"
ENV_SCORE_PESO_FRESCURA = "KENI_SCORE_PESO_FRESCURA"
ENV_SCORE_PESO_VIRALIDAD = "KENI_SCORE_PESO_VIRALIDAD"
ENV_SCORE_PESO_MARCA = "KENI_SCORE_PESO_MARCA"
ENV_SCORE_BONUS_BREAKING = "KENI_SCORE_BONUS_BREAKING"

# Monitor de COBERTURA + traducción completa + auto-verificación (Ola D). Aditivo sobre A-C.
#   MAX_ERRORES: tras N errores seguidos el daemon AUTO-DESACTIVA el feed (deja de sondearlo).
#   FEED_SLA_MIN: un feed activo sin items nuevos en > N min cuenta como "stale" en /salud.
#   TRAD_MIN_SCORE: score mínimo de un cluster extranjero para entrar a traducción.
#   TRAD_LOTE: clusters por barrido a traducir (acotado; el resto se cogen en el siguiente).
#   FUENTES_BAJA_CONFIANZA: dominios/outlets agregadores/foros que marcan una historia 'dudosa'
#     si son su única fuente (lista CSV configurable).
ENV_INGESTA_MAX_ERRORES = "KENI_INGESTA_MAX_ERRORES"
ENV_FEED_SLA_MIN = "KENI_FEED_SLA_MIN"
ENV_TRAD_MIN_SCORE = "KENI_TRAD_MIN_SCORE"
ENV_TRAD_LOTE = "KENI_TRAD_LOTE"
ENV_FUENTES_BAJA_CONFIANZA = "KENI_FUENTES_BAJA_CONFIANZA"

# Pipeline de contenido CI→CD→QA por marca (fase3 auto-produccion, Flujo "tubería"). Un hilo
# demonio que, cada N horas y por marca con feeds RSS activos, ingiere temas frescos (CI),
# lanza la generacion de copy+arte de marca (CD, mismo camino que el boton manual) y valida
# automaticamente los borradores recientes (QA), registrando CADA etapa en "Actividad IA" como
# un pipeline de CI/CD. Deja BORRADORES en la cola de revision para la aprobacion humana; NUNCA
# publica. CONSERVADOR por defecto (OFF): sin `KENI_PIPELINE_COPY` el comportamiento no cambia.
ENV_PIPELINE_COPY = "KENI_PIPELINE_COPY"
ENV_PIPELINE_MAX = "KENI_PIPELINE_MAX"
# FLUJO CONTINUO: el pipeline ya no barre por tandas (sin intervalo configurable: tick corto
# constante en `pipeline_contenido._barrido`) ni tiene topes por etapa (QA/Copy/autogen/revisar):
# el volumen lo regula la ADMISIÓN (gate serial en vuelo por marca) + el backpressure de la cola.
ENV_PIPELINE_EN_VUELO_MAX = "KENI_PIPELINE_EN_VUELO_MAX"  # gate serial: temas en vuelo por marca
# Enriquecimiento de la NOTA de origen en ingesta: antes de encolar el copy, el daemon descarga
# el CUERPO del/los artículo(s) (no solo el snippet RSS) y, en clusters, agrega el texto de CADA
# fuente —no solo sus URLs—. Así `claude -p` sintetiza sobre material real sin gastar turnos en
# WebFetch ni pedir permisos. CONSERVADOR por defecto (OFF): sin el flag la nota es título+resumen
# como hasta ahora. Best-effort: un fetch que falle cae a título+resumen (nunca rompe el barrido).
ENV_PIPELINE_FETCH_FUENTE = "KENI_PIPELINE_FETCH_FUENTE"  # ingerir el cuerpo del artículo en la nota
# Frescura del pipeline (ventana deslizante sobre el ranking): TTL en horas de un tema EN VUELO.
# Lo que no se completó a tiempo CADUCA y libera su hueco; hoy entra lo de hoy, no el backlog.
ENV_PIPELINE_TEMA_TTL_HORAS = "KENI_PIPELINE_TEMA_TTL_HORAS"  # caducidad de temas en vuelo

# Etapa de QA del pipeline: "Validar (QA)" (`KENI_PIPELINE_VALIDACION`, toggle de etapa por marca). Es la criba
# de la FUENTE (pre-copy): un `claude -p` evalúa la nota de origen antes de generar copy. Toggle
# PROPIO (1 toggle = 1 etapa): apagarla por marca la deja como "Saltada" y el copy se genera
# igual (sin la criba). CONSERVADOR por defecto (OFF), como el resto de etapas: sin `KENI_PIPELINE_VALIDACION` no
# se criba (la etapa aparece saltada). Encender desde el panel admin para activar la verificación.
ENV_PIPELINE_VALIDACION = "KENI_PIPELINE_VALIDACION"

# Etapa de ARTE del pipeline: "Generar arte" (`KENI_PIPELINE_ARTE`, toggle de etapa). Tras la
# etapa de copy, el pipeline genera UN arte por IA (mismo proveedor que `/api/media/generar`)
# para los temas con copy pero sin imagen y lo adjunta. CONSERVADOR por defecto (OFF): sin
# `KENI_PIPELINE_ARTE` no se ilustra. Sin proveedor de imagen configurado, no hace nada.
# `KENI_AUTOGEN_ARTE_MAX` acota cuántos temas se ilustran por barrido (cada uno cuesta).
ENV_PIPELINE_ARTE = "KENI_PIPELINE_ARTE"
ENV_AUTOGEN_ARTE_MAX = "KENI_AUTOGEN_ARTE_MAX"

# La etapa de AVANCE (un borrador COMPLETO pasa SOLO a la cola de revisión con la misma cadena
# que el envío humano) ya NO es configurable: corre incondicionalmente bajo el maestro
# KENI_MAQUINA. «Borrador» dejó de ser un estado donde descanse una pieza completa, así que no
# hay toggle (`KENI_PIPELINE_AVANCE`) ni exclusión por marca que la apaguen.

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

# QA de la FUENTE (criba pre-copy del pipeline): es un filtro PERMISIVO, no redaccion, asi
# que corre BARATO por defecto: modelo rapido (Haiku), esfuerzo bajo y timeout corto. Cada
# una es configurable; vacia ("") = se usa el global correspondiente.
ENV_QA_FUENTE_MODELO = "KENI_QA_FUENTE_MODELO"
ENV_QA_FUENTE_ESFUERZO = "KENI_QA_FUENTE_ESFUERZO"
ENV_QA_FUENTE_TIMEOUT = "KENI_QA_FUENTE_TIMEOUT"
# Saneador de temas zombi `qa_veredicto='en_curso'`: si el lanzamiento/generacion de la criba
# muere sin finalizador, el tema quedaba excluido para siempre de la re-criba (y contando en
# el cupo en vuelo). El reaper resetea a "" los `en_curso` mas viejos que este TTL (minutos).
ENV_QA_EN_CURSO_TTL_MIN = "KENI_QA_EN_CURSO_TTL_MIN"

# Recoleccion de basura (GC) de MEDIA HUERFANA (Estudio de imagen, diseno §5). El Estudio
# genera N variantes; las NO elegidas quedan como objetos sueltos en el almacen de media que
# nadie borra. Un hilo demonio barre periodicamente el almacen y borra SOLO los objetos
# HUERFANOS: ni referenciados por una publicacion (`imagen`) ni catalogados en catalogo-media
# y mas VIEJOS que un umbral (def 24h, para no tocar variantes recien generadas que el usuario
# aun revisa). CONSERVADOR por defecto (OFF): sin `KENI_MEDIA_GC` no se borra nada.
ENV_MEDIA_GC = "KENI_MEDIA_GC"
ENV_MEDIA_GC_INTERVALO_HORAS = "KENI_MEDIA_GC_INTERVALO_HORAS"
ENV_MEDIA_GC_ANTIGUEDAD_HORAS = "KENI_MEDIA_GC_ANTIGUEDAD_HORAS"

# GC del POOL DE NOTICIAS por RELEVANCIA (no por edad sola). Un hilo demonio barre y borra el
# ruido: historias `nuevo` no llevadas al tablero, de UNA fuente, score bajo y sin actividad
# reciente, + items huérfanos viejos. CONSERVA usados/ligados/corroborados/score alto/recientes.
# CONSERVADOR por defecto (OFF): sin `KENI_NOTICIAS_GC` no se borra nada.
ENV_NOTICIAS_GC = "KENI_NOTICIAS_GC"
ENV_NOTICIAS_GC_INTERVALO_HORAS = "KENI_NOTICIAS_GC_INTERVALO_HORAS"
ENV_NOTICIAS_GC_SCORE_UMBRAL = "KENI_NOTICIAS_GC_SCORE_UMBRAL"
ENV_NOTICIAS_GC_INACTIVIDAD_HORAS = "KENI_NOTICIAS_GC_INACTIVIDAD_HORAS"

# Perfil editorial por marca (Fase 2): un agente Haiku extrae las keywords/temas de la línea
# editorial (página texto) y el ranking las usa como relevancia de marca (reemplaza el diccionario
# hardcodeado). GATEADO por `KENI_RANKING_PERFIL_IA` (def OFF): sin el flag se usa el vocabulario
# semilla. El refresco (Haiku) corre acotado por marca + TTL en el daemon de ingesta. (Nombre
# previo: `KENI_PIPELINE_EDITORIAL`; migrado por alias legado. ADR 0011: es ranking, no voz.)
ENV_RANKING_PERFIL_IA = "KENI_RANKING_PERFIL_IA"
ENV_PERFIL_EDITORIAL_TTL_HORAS = "KENI_PERFIL_EDITORIAL_TTL_HORAS"

# Fusión SEMÁNTICA de historias del mismo evento (Fase 2b): un agente Haiku agrupa las historias
# recientes de una marca que cubren el mismo acontecimiento (titulares distintos) y el daemon las
# funde en una sola (n_fuentes real). GATEADO por `KENI_PIPELINE_FUSION` (def OFF). `_MAX` acota
# cuántas historias por marca se mandan a Haiku por barrido (coste/contexto).
ENV_PIPELINE_FUSION = "KENI_PIPELINE_FUSION"
ENV_FUSION_SEMANTICA_MAX = "KENI_FUSION_SEMANTICA_MAX"

# Señal de RENDIMIENTO en el ranking (Fase 2c): prioriza historias de las líneas editoriales que
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
# `--model` y `claude` usa su propio default. Ver `dominio/insumos_parse.py`.
ENV_INSUMOS_MODELO = "KENI_INSUMOS_MODELO"
# Modelo de la FUSIÓN semántica de historias (decide qué se corrobora con qué; el juicio
# fino "mismo evento vs mismo tema" se le escapaba a haiku). Def "sonnet"; "" = sin --model.
ENV_FUSION_MODELO = "KENI_FUSION_MODELO"

# Traducción + tropicalización MX de temas extranjeros en el Radar (Ola 4). La traducción es
# SIEMPRE ON (no tiene toggle propio: corre dentro de la etapa de ingesta, gateada por
# KENI_PIPELINE_SELECCION + KENI_MAQUINA). `KENI_TRADUCCION_MAX` acota cuántos temas extranjeros del top
# se traducen por request (def 15). Se usa el mismo modelo de `KENI_INSUMOS_MODELO` (Haiku).
ENV_TRADUCCION_MAX = "KENI_TRADUCCION_MAX"

# Imagen / secretos (precedencia con el fichero vive en `secretos.py`).
ENV_IMAGEN_API_KEY = "KENI_IMAGEN_API_KEY"
ENV_IMAGEN_PROVEEDOR = "KENI_IMAGEN_PROVEEDOR"

# Motor de VIDEO (Ola VIDEO). El render (ffmpeg) y la transcripcion (faster-whisper) son
# locales, gratuitos y BAJO DEMANDA (solo corren cuando un humano pulsa "Renderizar" /
# "Transcribir"; no hay daemon que los dispare ni consumen tokens), asi que NO tienen
# kill-switch ni estan gateados por la maquina. Aqui solo queda configuracion legitima:
#   - KENI_WHISPER_MODELO     (str, def "medium"): modelo de faster-whisper para el ASR.
#   - KENI_FFMPEG_BIN         (str, def "ffmpeg"): binario de ffmpeg (path o nombre en PATH).
#   - KENI_VIDEO_RENDER_TIMEOUT (int, def 1800 s): wall-timeout del render de un video.
ENV_WHISPER_MODELO = "KENI_WHISPER_MODELO"
ENV_FFMPEG_BIN = "KENI_FFMPEG_BIN"
ENV_VIDEO_RENDER_TIMEOUT = "KENI_VIDEO_RENDER_TIMEOUT"
WHISPER_MODELO_DEF = "medium"
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
# Tope absoluto de vida de sesion (horas). Def 720 = 30 dias: MUY por encima de la ventana
# deslizante (def 12h), asi nunca corta una sesion en uso normal del piloto; solo bota las que
# se renuevan indefinidamente (token vivo o robado-y-usado) pasados los 30 dias desde `creada`.
SESION_MAX_HORAS_DEF = 720
ADMIN_USER_DEF = "admin"
LOG_LEVEL_DEF = "INFO"
MAX_JOBS_DEF = 4
MAX_COLA_DEF = 16
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
# QA de la fuente: timeout corto (criba permisiva con modelo rapido) y TTL del saneador de
# temas `en_curso` huerfanos (minutos; muy superior al timeout de la criba).
QA_FUENTE_TIMEOUT_DEF = 180
QA_EN_CURSO_TTL_MIN_DEF = 30
# Cadencia de sondeo de la cola por el worker (s). Bajo para que el job arranque casi
# al instante tras encolarse (la UX de "Generar" no debe notar el desacoplo).
WORKER_SONDEO_SEGUNDOS_DEF = 0.5
# Presupuesto DIARIO de tokens de la generacion (in+out, dia UTC). 0 = SIN limite (defecto:
# no cambia el comportamiento de un deploy existente; se enciende fijando un valor > 0).
PRESUPUESTO_TOKENS_DIA_DEF = 0
# Margen EXTRA (%) sobre el presupuesto que se concede SOLO a los lanzamientos manuales del
# equipo cuando el fondo ya esta cortado. Al superarlo, corte TOTAL (tambien lo manual).
PRESUPUESTO_MARGEN_MANUAL_DEF = 20
# Intentos maximos de ejecucion de un job (el normal + re-reclamos de huerfano). 3 da dos
# reintentos automaticos tras muertes del worker sin permitir un crash-loop infinito.
JOBS_MAX_INTENTOS_DEF = 3
# Tope DURO del prompt por generacion (chars; ~4 chars = 1 token). 200k chars ~ 50k tokens:
# muy por encima de cualquier prompt legitimo de copy; corta los patologicos (avalancha de
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
# son ~540 puntos por pieza; la poda mantiene la tabla acotada (ADR 0007).
METRICAS_HISTORICO_RETENCION_DIAS_DEF = 90
# Cadencia del barrido de alertas de rendimiento (horas).
ALERTAS_INTERVALO_HORAS_DEF = 6
# Umbral de engagement (%) por debajo del cual una pieza dispara alerta de bajo rendimiento.
ALERTAS_UMBRAL_ENGAGEMENT_DEF = 1.0

# Cadencia del barrido de eventos internos (vencimientos del tablero). 5 min basta: el
# vencimiento es por DIA (`fecha_entrega`), no hace falta granularidad fina.
EVENTOS_INTERVALO_SEGUNDOS_DEF = 300.0

# Cadencia del barrido del Investigador (Fase 1): materializa el snapshot del Radar por marca
# cada N horas. Intervalo holgado (def 6h, igual que radar-auto): el snapshot vive con un TTL
# de ~2 intervalos, asi que con 6h las lecturas sirven datos de a lo sumo medio dia.
INVESTIGADOR_INTERVALO_HORAS_DEF = 6

# Auto-refresco de Algoritmos: intervalo holgado (def 6h); los blogs de plataforma no
# cambian a cada minuto y no conviene martillear los feeds.
ALGORITMOS_INTERVALO_HORAS_DEF = 6

# Digest de sugerencias editoriales: 1 vez al dia, pocas plataformas por barrido (cada una
# cuesta un claude -p). Conservador a proposito.
SUGERENCIAS_EDITORIALES_INTERVALO_HORAS_DEF = 24
SUGERENCIAS_EDITORIALES_MAX_DEF = 3

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
INGESTA_INTERVALO_TENDENCIAS_DEF = 600
INGESTA_INTERVALO_CIENCIA_TECH_DEF = 1800
INGESTA_INTERVALO_GAMING_DEF = 1800
# Categoría desconocida / sin clasificar: cadencia general.
INGESTA_INTERVALO_DEFECTO_DEF = 600
# Tope del backoff exponencial (segundos): un feed que falla repetidamente no se pausa más de
# esto (1 hora), para que se reintente con regularidad cuando vuelva.
INGESTA_BACKOFF_TOPE_SEG = 3600

# Clustering de historias (Ola B): defaults. Ventana de 72h (una historia evoluciona varios
# días); umbral fuzzy 0.82 (alto, conservador: solo une variantes claras del mismo titular);
# breaking PONDERADO = masa de fuentes (Σ peso por outlet) >= 3.0 sumadas en la ventana
# ACTUAL de 6h: 3 normales, 1 potente + 1 normal, o 2 potentes. Anclado en ahora: decae solo.
CLUSTER_VENTANA_H_DEF = 72
CLUSTER_UMBRAL_DEF = 0.82
CLUSTER_UMBRAL_MERGE_DEF = 0.86
CLUSTER_BREAKING_FUENTES_DEF = 3  # LEGADO (conteo); ver CLUSTER_BREAKING_PESO_DEF
CLUSTER_BREAKING_PESO_DEF = 3.0
BREAKING_EXTRA_DIA_DEF = 4
CLUSTER_BREAKING_VENTANA_H_DEF = 6

# Pesos del algoritmo de ponderación del score (defaults; espejan `clustering.PesosScore`).
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
#   subirlo limita la traducción a historias más relevantes. Lote de 40 por barrido para no
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

# Etapa de ARTE del pipeline: cap bajo por barrido (def 3), porque cada item llama al
# proveedor de imagen (coste).
AUTOGEN_ARTE_MAX_DEF = 3

# Pipeline de contenido (FLUJO CONTINUO): la Selección admite hasta este nº de historias por
# marca en cada admisión, acotada además por el gate serial en vuelo. Cada admisión acaba en
# `claude -p` (coste); el cap del worker (`KENI_MAX_JOBS`) sigue aplicando aguas abajo.
PIPELINE_MAX_DEF = 3
# WIP del gate serial: piezas EN VUELO (sin terminar QA→Copy) por marca. ES el regulador del
# flujo continuo: in=out (no se admite más hasta que algo sale por el otro lado).
PIPELINE_EN_VUELO_MAX_DEF = 8
# TTL por defecto de un tema EN VUELO (horas): un día. "Lo que no entró ayer no entra hoy":
# el pipeline prioriza siempre lo fresco del ranking, nunca arrastra backlog.
PIPELINE_TEMA_TTL_HORAS_DEF = 24


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

# GC del pool de noticias: cada 6h; purga historias con score < 0.15 (ruido) e inactivas > 48h.
NOTICIAS_GC_INTERVALO_HORAS_DEF = 6
NOTICIAS_GC_SCORE_UMBRAL_DEF = 0.15
NOTICIAS_GC_INACTIVIDAD_HORAS_DEF = 48

# Perfil editorial: se re-extrae con Haiku cada 24h (o si cambia la línea editorial).
PERFIL_EDITORIAL_TTL_HORAS_DEF = 24

# Fusión semántica: hasta 40 historias por marca y barrido se mandan a Haiku a agrupar.
FUSION_SEMANTICA_MAX_DEF = 40

# Rendimiento en el ranking (Fase 2c): peso de la señal (0.15), top-3 líneas, muestra mínima 5.
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
    'QA_EN_CURSO_TTL_MIN_DEF',
    'QA_FUENTE_TIMEOUT_DEF',
    'CLUSTER_BREAKING_FUENTES_DEF',
    'BREAKING_EXTRA_DIA_DEF',
    'CLUSTER_BREAKING_PESO_DEF',
    'CLUSTER_BREAKING_VENTANA_H_DEF',
    'CLUSTER_UMBRAL_DEF',
    'CLUSTER_UMBRAL_MERGE_DEF',
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
    'ENV_PIPELINE_ARTE',
    'ENV_AUTOGEN_ARTE_MAX',
    'ENV_AUTO_PREAPROBACION',
    'ENV_AUTO_PROGRAMAR',
    'ENV_TEXTO_DIR',
    'ENV_CLAUDE_DISALLOWED_TOOLS',
    'ENV_CLAUDE_MAX_TURNS',
    'ENV_CLAUDE_MAX_USD',
    'ENV_CLAUDE_SKIP_PERMISSIONS',
    'ENV_CLAUDE_TIMEOUT',
    'ENV_CLUSTER_BREAKING_FUENTES',
    'ENV_BREAKING_EXTRA_DIA',
    'ENV_CLUSTER_BREAKING_PESO',
    'ENV_CLUSTER_BREAKING_VENTANA_H',
    'ENV_CLUSTER_UMBRAL',
    'ENV_CLUSTER_UMBRAL_MERGE',
    'ENV_CLUSTER_VENTANA_H',
    'ENV_COMERCIAL_INTERVALO_HORAS',
    'ENV_COMERCIAL_INTERVALO_SEGUNDOS',
    'ENV_CONFIG',
    'ENV_CONSOLA_URL_PUBLICA',
    'ENV_COOKIE_SECURE',
    'ENV_DATABASE_URL',
    'ENV_DATA_DIR',
    'ENV_DB_POOL',
    'ENV_DB_POOL_MAX',
    'ENV_DB_POOL_MIN',
    'ENV_EVENTOS_INTERVALO_SEGUNDOS',
    'ENV_EVENTOS_VENCIMIENTOS',
    'ENV_FEED_SLA_MIN',
    'ENV_PIPELINE_FUSION',
    'ENV_FUSION_SEMANTICA_MAX',
    'ENV_FFMPEG_BIN',
    'ENV_FUENTES_BAJA_CONFIANZA',
    'ENV_GENERACIONES',
    'ENV_GENERACIONES_TTL_HORAS',
    'ENV_HOST',
    'ENV_HTTPS',
    'ENV_IMAGEN_API_KEY',
    'ENV_IMAGEN_PROVEEDOR',
    'ENV_INDICE',
    'ENV_PIPELINE_SELECCION',
    'ENV_INGESTA_BATCH',
    'ENV_INGESTA_INTERVALO_BREAKING',
    'ENV_INGESTA_INTERVALO_CIENCIA_TECH',
    'ENV_INGESTA_INTERVALO_DEFECTO',
    'ENV_INGESTA_INTERVALO_DEPORTES',
    'ENV_INGESTA_INTERVALO_GAMING',
    'ENV_INGESTA_INTERVALO_INTERNACIONAL',
    'ENV_INGESTA_INTERVALO_MX',
    'ENV_INGESTA_INTERVALO_TENDENCIAS',
    'ENV_INGESTA_MAX_ERRORES',
    'ENV_INGESTA_MAX_ITEMS',
    'ENV_INGESTA_WORKERS',
    'ENV_FUSION_MODELO',
    'ENV_INSUMOS_MODELO',
    'ENV_INVESTIGADOR',
    'ENV_INVESTIGADOR_INTERVALO_HORAS',
    'ENV_LOG_LEVEL',
    'ENV_MAQUINA',
    'ENV_MAX_COLA',
    'ENV_MAX_JOBS',
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
    'ENV_RANKING_PERFIL_IA',
    'ENV_PERFIL_EDITORIAL_TTL_HORAS',
    'ENV_PG_DB',
    'ENV_PG_HOST',
    'ENV_PG_PASSWORD',
    'ENV_PG_PORT',
    'ENV_PG_USER',
    'ENV_PIPELINE_COPY',
    'ENV_PIPELINE_MAX',
    'ENV_PIPELINE_EN_VUELO_MAX',
    'ENV_PIPELINE_TEMA_TTL_HORAS',
    'ENV_PORT',
    'ENV_PREFERENCIAS',
    'ENV_PRESUPUESTO_MARGEN_MANUAL',
    'ENV_PRESUPUESTO_TOKENS_DIA',
    'ENV_GENERACION_PAUSADA',
    'ENV_JOBS_MAX_INTENTOS',
    'ENV_PROMPT_MAX_CHARS',
    'ENV_PROMPT_AVISO_CHARS',
    'ENV_PROGRAMADOR_INTERVALO_SEGUNDOS',
    'ENV_PUBLICAR_REAL',
    'ENV_PIPELINE_VALIDACION',
    'ENV_QA_EN_CURSO_TTL_MIN',
    'ENV_QA_FUENTE_ESFUERZO',
    'ENV_QA_FUENTE_MODELO',
    'ENV_QA_FUENTE_TIMEOUT',
    'ENV_RAIZ',
    'ENV_REAPER_INTERVALO_MIN',
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
    'ENV_SESION_HORAS',
    'ENV_SESION_MAX_HORAS',
    'ENV_SUGERENCIAS',
    'ENV_SUGERENCIAS_EDITORIALES',
    'ENV_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS',
    'ENV_SUGERENCIAS_EDITORIALES_MAX',
    'ENV_TOKEN',
    'ENV_TRADUCCION_MAX',
    'ENV_TRAD_LOTE',
    'ENV_TRAD_MIN_SCORE',
    'ENV_TRENDS',
    'ENV_TRENDS_GEOS',
    'ENV_TRENDS_INTERVALO_MIN',
    'ENV_VIDEO_MAX_MB',
    'ENV_VIDEO_RENDER_TIMEOUT',
    'ENV_WHISPER_MODELO',
    'ENV_WORKER_EXTERNO',
    'ENV_WORKER_SONDEO_SEGUNDOS',
    'EVENTOS_INTERVALO_SEGUNDOS_DEF',
    'FEED_SLA_MIN_DEF',
    'FFMPEG_BIN_DEF',
    'FUENTES_BAJA_CONFIANZA_DEF',
    'FUSION_SEMANTICA_MAX_DEF',
    'GENERACIONES_TTL_HORAS_DEF',
    'HOST_DEF',
    'INGESTA_BACKOFF_TOPE_SEG',
    'INGESTA_BATCH_DEF',
    'INGESTA_INTERVALO_BREAKING_DEF',
    'INGESTA_INTERVALO_CIENCIA_TECH_DEF',
    'INGESTA_INTERVALO_DEFECTO_DEF',
    'INGESTA_INTERVALO_DEPORTES_DEF',
    'INGESTA_INTERVALO_GAMING_DEF',
    'INGESTA_INTERVALO_INTERNACIONAL_DEF',
    'INGESTA_INTERVALO_MX_DEF',
    'INGESTA_INTERVALO_TENDENCIAS_DEF',
    'INGESTA_MAX_ERRORES_DEF',
    'INGESTA_MAX_ITEMS_DEF',
    'INGESTA_WORKERS_DEF',
    'INVESTIGADOR_INTERVALO_HORAS_DEF',
    'LOG_LEVEL_DEF',
    'JOBS_MAX_INTENTOS_DEF',
    'PROMPT_MAX_CHARS_DEF',
    'PROMPT_AVISO_CHARS_DEF',
    'MAX_COLA_DEF',
    'MAX_JOBS_DEF',
    'PRESUPUESTO_MARGEN_MANUAL_DEF',
    'PRESUPUESTO_TOKENS_DIA_DEF',
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
    'PIPELINE_EN_VUELO_MAX_DEF',
    'PIPELINE_TEMA_TTL_HORAS_DEF',
    'PORT_DEF',
    'Path',
    'REAPER_INTERVALO_MIN_DEF',
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
    'SUGERENCIAS_EDITORIALES_INTERVALO_HORAS_DEF',
    'SUGERENCIAS_EDITORIALES_MAX_DEF',
    'TRAD_LOTE_DEF',
    'TRAD_MIN_SCORE_DEF',
    'TRENDS_GEOS_DEF',
    'TRENDS_INTERVALO_MIN_DEF',
    'VIDEO_MAX_MB_DEF',
    'VIDEO_RENDER_TIMEOUT_DEF',
    'WHISPER_MODELO_DEF',
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
