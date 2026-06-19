# TRANSCRIPTOR de keni-social: servicio DEDICADO de transcripción ASR (gestor audio→texto).
#
# Reclama SOLO el carril `transcripcion` de la cola (`python -m keni_consola.worker_transcripcion`):
# jobs PROC_TRANSCRIBIR / PROC_TRANSCRIBIR_AUDIO que el motor `keni_consola.transcripcion` resuelve
# con whisper.cpp (`whisper-cli`) + el modelo `v3 turbo`. Es una imagen LEAN a propósito: NO lleva
# Node, ni la CLI `claude`, ni `gh` (no corre `claude -p` ni el carril dev) — solo Python + las
# herramientas de audio (ffmpeg + whisper-cli). Así el binario whisper-cli y el modelo (~1.6 GB) NO
# contaminan la imagen del worker general. Comparte la cola (Postgres) y la media (S3/Garage).
#
# Contexto de build: la RAIZ del repo (ver deploy/docker-compose.yml).

# --------------------------------------------------------------------------- #
# Etapa BUILDER: compila whisper.cpp (`whisper-cli`). Build ESTATICO            #
# (BUILD_SHARED_LIBS=OFF) para que el binario sea autocontenido (solo          #
# libstdc++/libgomp/libc del sistema) y poder copiar SOLO el binario a la       #
# imagen final, sin arrastrar el toolchain. Version PINEADA a la verificada     #
# CORRIENDO en local (brew whisper-cpp 1.8.3).                                  #
# --------------------------------------------------------------------------- #
FROM debian:bookworm-slim AS whisper-build
ARG WHISPER_CPP_VERSION=v1.8.3
# `-DCMAKE_C_FLAGS=-w -DCMAKE_CXX_FLAGS=-w` silencian los warnings del compilador en el código de
# whisper.cpp (sobre todo el falso positivo `-Wmaybe-uninitialized` de GCC en los intrínsecos
# AVX-512: miles de líneas de ruido en el log del build, ajenas a nuestro código). No afecta al
# binario resultante, solo a la verbosidad del build.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git build-essential cmake ca-certificates \
 && git clone --depth 1 --branch "${WHISPER_CPP_VERSION}" https://github.com/ggml-org/whisper.cpp /src \
 && cmake -S /src -B /src/build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
      -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON \
      -DCMAKE_C_FLAGS=-w -DCMAKE_CXX_FLAGS=-w \
 && cmake --build /src/build -j --config Release --target whisper-cli \
 && cp /src/build/bin/whisper-cli /usr/local/bin/whisper-cli \
 && /usr/local/bin/whisper-cli --help >/dev/null

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Mismo estado que el back/worker: secretos.toml, media, modelo whisper en /data.
    XDG_CONFIG_HOME=/data

# curl + ca-certificates: descarga del modelo whisper en el entrypoint. ffmpeg: extrae/normaliza la
# pista de voz a wav 16 kHz mono antes del ASR. libgomp1: runtime de OpenMP que necesita el
# `whisper-cli` (estático) copiado del builder. NADA de Node/claude/gh: este servicio no genera copy.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates ffmpeg libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Binario whisper-cli (whisper.cpp) compilado en la etapa builder: el motor lo invoca como
# subproceso (sin shell). El modelo lo aporta el entrypoint (descarga a /data).
COPY --from=whisper-build /usr/local/bin/whisper-cli /usr/local/bin/whisper-cli

WORKDIR /app

# Los tres paquetes Python del monorepo (mismo layout que el worker).
# ⚠ DEPLOY: la VERSIÓN de esta imagen es un hash de estas entradas + deploy/transcriptor (deploy/
# deploy.sh, hash_entradas: keni-shared + mcp-metricas + consola, menos consola/frontend). Si AÑADES
# aquí un `COPY` de OTRA ruta, AÑÁDELA también a ese hash; si no, un cambio en ella no reconstruiría
# la imagen y el transcriptor seguiría con código viejo en prod (deploy perdido).
COPY keni-shared/ ./keni-shared/
COPY mcp-metricas/ ./mcp-metricas/
COPY consola/ ./consola/
# [postgres] (psycopg) para leer la cola compartida y [s3] (boto3) para bajar el audio del bucket.
RUN pip install ./keni-shared "./mcp-metricas[deck]" "./consola[postgres,s3]"

# Entrypoint: descarga el modelo whisper a /data (una vez, en segundo plano) y arranca el worker.
COPY deploy/transcriptor/entrypoint.sh /usr/local/bin/keni-transcriptor-entrypoint.sh
RUN chmod +x /usr/local/bin/keni-transcriptor-entrypoint.sh

# HARDENING: NO corre como root. Le damos /app (código) y /data (estado compartido con el back:
# secretos.toml, media en disco si no hay S3, y el modelo whisper). Mismo uid que back/worker (10001)
# para compartir el volumen keni-data sin problemas de permisos.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin keni \
 && mkdir -p /data \
 && chown -R keni:keni /app /data
USER keni

VOLUME ["/data"]

# El transcriptor NO publica puertos ni sirve HTTP: solo consume el carril `transcripcion`. Corre el
# bucle hasta SIGTERM (compose lo reinicia con `restart: unless-stopped`).
ENTRYPOINT ["/usr/local/bin/keni-transcriptor-entrypoint.sh"]
CMD ["python", "-m", "keni_consola.worker_transcripcion"]
