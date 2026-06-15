# WORKER de generacion de keni-social (#130 Fase 2 / ADR 0002 Fase B).
#
# El back ENCOLA y ESTE servicio EJECUTA `claude -p`. Por eso esta imagen SI lleva Node +
# la CLI `claude` (la del back ya no). Consume la MISMA cola que el back (tabla `jobs` en
# el Postgres compartido) y corre `python -m keni_consola.worker` (bucle: clava un job,
# reconstruye prompt+post-procesado desde el `spec` y corre el runner #137: grupo de
# procesos propio, kill del arbol al timeout/cancel, tope de concurrencia, sin procesos sueltos).
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
    XDG_CONFIG_HOME=/data

# VERSION PINEADA de la CLI de Claude Code. ANTES estaba SIN pinear (`npm install -g
# @anthropic-ai/claude-code` a secas): cada rebuild traia la ULTIMA publicada y un cambio en
# el formato de `--stream-json` podia ROMPER en prod el parseo del worker sin que nadie lo
# pidiera. Fijamos una version concreta para builds REPRODUCIBLES; el upgrade debe ser
# DELIBERADO: sube este valor a conciencia, valida el stream-json del worker contra la nueva
# version y despliega aparte (no lo mezcles con otro cambio). Overridable por build-arg.
#   ⚠ 2.1.173 = version verificada CORRIENDO en prod (worker container, 2026-06-13).
#     Se fija a la de prod, NO a "la ultima de npm", para que un rebuild no altere el
#     comportamiento de stream-json ya validado. Sube a conciencia y valida aparte.
ARG CLAUDE_CODE_VERSION=2.1.173

# curl: script de nodesource. git: lo usan algunas skills. Node 20 + Claude Code CLI:
# AQUI SI (el worker es quien corre `claude -p`). ffmpeg: motor de RENDER de video (Ola VIDEO)
# — el worker tambien ejecuta los jobs de proceso `render-video` (filtergraph: scale/crop/pad,
# overlay, xstack/vstack, subtitles=ASS). NOTA: la dependencia ASR (faster-whisper/torch) NO se
# bakea aqui (pesado, rompe el build): es OPCIONAL y se instala en el servidor cuando se active
# la transcripcion (import perezoso en motores/transcripcion; degrada con error claro si falta).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates git ffmpeg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
 && npm cache clean --force \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Los tres paquetes Python del monorepo (mismo layout que el back).
# ⚠ DEPLOY: la VERSIÓN de esta imagen es un hash de estas entradas + deploy/worker (deploy/
# deploy.sh, hash_entradas: keni-shared + mcp-metricas + consola, menos consola/frontend). Si
# AÑADES aquí un `COPY` de OTRA ruta, AÑÁDELA también a ese hash; si no, un cambio en ella no
# reconstruiría la imagen y el worker seguiría con código viejo en prod (deploy perdido).
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

# Entrypoint: exporta las credenciales de Claude desde sus ficheros de secreto (*_FILE) a
# env antes de arrancar (claude -p solo lee de env), asi no salen en docker inspect. Se
# copia como root y se hace ejecutable antes de bajar a usuario no-root.
COPY deploy/worker/entrypoint.sh /usr/local/bin/keni-worker-entrypoint.sh
RUN chmod +x /usr/local/bin/keni-worker-entrypoint.sh

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
# SIGTERM (compose lo reinicia con `restart: unless-stopped`). El ENTRYPOINT hidrata las
# credenciales de Claude desde los ficheros de secreto y luego ejecuta el CMD via `exec "$@"`.
ENTRYPOINT ["/usr/local/bin/keni-worker-entrypoint.sh"]
CMD ["python", "-m", "keni_consola.worker"]
