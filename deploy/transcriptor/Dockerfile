# TRANSCRIPTOR de keni-social: servicio DEDICADO de transcripción ASR (gestor audio→texto).
#
# Reclama SOLO el carril `transcripcion` de la cola (`python -m keni_consola.worker_transcripcion`):
# jobs PROC_TRANSCRIBIR / PROC_TRANSCRIBIR_AUDIO que el motor `keni_consola.transcripcion` resuelve
# con faster-whisper (whisper sobre CTranslate2, modelo `large-v3-turbo` = v3 turbo). Imagen LEAN a
# propósito: NO lleva Node, ni la CLI `claude`, ni `gh` (no corre `claude -p` ni el carril dev) — y
# tampoco compila nada: el motor es un WHEEL de Python. Comparte la cola (Postgres) y la media (S3).
#
# NO RECOMPILA NI RE-DESCARGA si ya lo tiene:
#   - El motor (faster-whisper/CTranslate2) se instala como WHEEL precompilado, en su PROPIA capa
#     ANTES de copiar la app: un cambio de código NO reinstala el motor (Docker reutiliza la capa).
#   - El modelo (~1.6 GB) lo descarga faster-whisper UNA vez al cache PERSISTENTE `/data/models`
#     (`KENI_WHISPER_DIR`, volumen keni-data); comprueba el cache y no lo vuelve a bajar.
#
# Contexto de build: la RAIZ del repo (ver deploy/docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Mismo estado que el back/worker: media en disco si no hay S3, y el modelo whisper en /data.
    XDG_CONFIG_HOME=/data

# ca-certificates: TLS para la descarga del modelo desde Hugging Face. libgomp1: runtime de OpenMP
# que usa CTranslate2. NADA de Node/claude/gh ni ffmpeg del sistema (faster-whisper trae su propio
# decodificador de audio en la rueda).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# MOTOR ASR en su PROPIA capa, ANTES de copiar la app: así un cambio de código de la consola NO
# reinstala faster-whisper/CTranslate2 (Docker reutiliza esta capa cacheada). Wheel precompilado:
# no compila nada. La version se fija para builds reproducibles; el extra `asr` de consola la exige.
# `requests`: faster-whisper 1.1.0 lo IMPORTA directo (utils.py) pero NO lo declara, y huggingface_hub
# 1.x ya no lo arrastra (migró a httpx); sin él `import faster_whisper` revienta. La VERIFICACION de
# import al final hace FALLAR el build si las deps quedan incompletas (en vez de desplegar una imagen
# que arranca pero no transcribe).
ARG FASTER_WHISPER_VERSION=1.1.0
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install "faster-whisper==${FASTER_WHISPER_VERSION}" "requests>=2" \
 && python -c "from faster_whisper import WhisperModel"

WORKDIR /app

# Los tres paquetes Python del monorepo (mismo layout que el worker).
# ⚠ DEPLOY: la VERSIÓN de esta imagen es un hash de estas entradas + deploy/transcriptor (deploy/
# deploy.sh, hash_entradas: keni-shared + mcp-metricas + consola, menos consola/frontend). Si AÑADES
# aquí un `COPY` de OTRA ruta, AÑÁDELA también a ese hash; si no, un cambio en ella no reconstruiría
# la imagen y el transcriptor seguiría con código viejo en prod (deploy perdido).
COPY keni-shared/ ./keni-shared/
COPY mcp-metricas/ ./mcp-metricas/
COPY consola/ ./consola/
# [asr] trae faster-whisper (ya instalado arriba como wheel; pip lo da por satisfecho), [postgres]
# (psycopg) para leer la cola y [s3] (boto3) para bajar el audio del bucket.
# Cache de pip en mount de BuildKit (no viaja a la imagen): reusa wheels ya bajados al reinstalar.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install ./keni-shared "./mcp-metricas[deck]" "./consola[asr,postgres,s3]"

# HARDENING: NO corre como root. Mismo uid que back/worker (10001) para compartir el volumen
# keni-data sin problemas de permisos (ahí cachea el modelo y, sin S3, la media).
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin keni \
 && mkdir -p /data \
 && chown -R keni:keni /app /data
USER keni

VOLUME ["/data"]

# El transcriptor NO publica puertos ni sirve HTTP: solo consume el carril `transcripcion`. Corre el
# bucle hasta SIGTERM (compose lo reinicia con `restart: unless-stopped`). Al arrancar pre-calienta
# el modelo (lo descarga/carga en segundo plano) para que la primera transcripción no espere.
CMD ["python", "-m", "keni_consola.worker_transcripcion"]
