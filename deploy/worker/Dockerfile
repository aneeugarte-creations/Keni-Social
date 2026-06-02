# WORKER de generacion de keni-social (#130 Fase 2 / ADR 0002 Fase B).
#
# El back ENCOLA y ESTE servicio EJECUTA `claude -p`. Por eso esta imagen SI lleva Node +
# la CLI `claude` (la del back ya no). Consume la MISMA cola que el back (tabla `jobs` en
# el Postgres compartido) y corre `python -m keni_consola.worker` (bucle: clava un job,
# reconstruye prompt+post-procesado desde el `spec` y corre el runner #137: grupo de
# procesos propio, kill del arbol al timeout/cancel, tope de concurrencia, sin huerfanos).
#
# Comparte el mismo CODIGO y el mismo VOLUMEN de estado que el back (skills bundleadas en
# /app, secretos.toml/media en /data), porque el post-procesado escribe el historial y las
# publicaciones (borradores) en la misma persistencia. La generacion sigue siendo `claude
# -p` (ADR 0001): el worker NO usa la API de Claude.
#
# Contexto de build: la RAIZ del repo (ver deploy/docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Mismo estado que el back: secretos.toml (0600), media, etc. cuelgan de /data.
    XDG_CONFIG_HOME=/data \
    # Descubrimiento + ejecucion de skills: el repo (con skills-copy/) vive en /app.
    KENI_SKILLS_CWD=/app

# curl: script de nodesource. git: lo usan algunas skills. Node 20 + Claude Code CLI:
# AQUI SI (el worker es quien corre `claude -p`).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates git \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Los tres paquetes Python del monorepo (mismo layout que el back).
COPY keni-shared/ ./keni-shared/
COPY mcp-metricas/ ./mcp-metricas/
COPY consola/ ./consola/
# Extras de persistencia HOSTED (#130): [postgres] (psycopg) para leer la cola compartida y
# [s3] (boto3) porque el post-procesado de imagen importa al media (bucket en hosted).
RUN pip install ./keni-shared "./mcp-metricas[deck]" "./consola[postgres,s3]"

# Renderer Node de la plantilla de marca (auto-genera la placa al crear copy en el worker).
# @napi-rs/canvas trae binarios prebuilt (sin Cairo); node_modules no viaja (.dockerignore);
# se instala en la UBICACIÓN INSTALADA del paquete (site-packages), donde el subproceso resuelve
# `componer.mjs`, desde el lock versionado. Node 20 ya está presente.
RUN RN="$(python -c 'import keni_consola, os; print(os.path.join(os.path.dirname(keni_consola.__file__), "motores", "estudio_imagen", "render_node"))')" \
 && npm --prefix "$RN" ci --omit=dev \
 && npm cache clean --force

# HARDENING (#130): el worker NO corre como root. `claude` ya esta instalado globalmente
# (RUN anterior, como root) y el usuario solo lo EJECUTA; ademas, fuera de root `claude` NO
# exige el bypass `--dangerously-skip-permissions`+IS_SANDBOX (esa restriccion es solo para
# uid 0). Le damos /app (codigo + skills bundleadas), /data (estado compartido con el back)
# y un HOME propio (config/cache de `claude` y npm). Mismo aviso de volumen EXISTENTE que el
# back: re-chown una sola vez en el host (ver deploy/README.md).
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin keni \
 && mkdir -p /data \
 && chown -R keni:keni /app /data
USER keni

VOLUME ["/data"]

# El worker NO publica puertos ni sirve HTTP: solo consume la cola. Corre el bucle hasta
# SIGTERM (compose lo reinicia con `restart: unless-stopped`).
CMD ["python", "-m", "keni_consola.worker"]
