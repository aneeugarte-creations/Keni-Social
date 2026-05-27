# Gateway de keni-social: API Starlette (`consola/`) + fallback del SPA.
#
# IMAGEN INTERINA a proposito: incluye Node + la CLI `claude` porque HOY la
# generacion corre con `claude -p` en proceso (ADR 0001, Fase 0). ADR 0002 Fase B
# extrae un worker que llamara a la API de Claude (SDK) y dejara esta imagen sin
# Node. Hasta entonces, esto es lo que hace funcionar la generacion de copy.
#
# Contexto de build: la RAIZ del repo (ver deploy/docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Todo el estado de la app (consola.db SQLite, secretos.toml 0600, media,
    # tareas.json) cuelga de XDG_CONFIG_HOME -> volumen montado en /data.
    XDG_CONFIG_HOME=/data \
    # Descubrimiento de skills DENTRO del contenedor (cierra #133 aqui): el repo
    # vive en /app, que contiene skills-copy/.
    KENI_SKILLS_CWD=/app

# curl: healthcheck + script de nodesource. git: lo usan algunas skills.
# Node 20 + Claude Code CLI = INTERINO (generacion por `claude -p`).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates git \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Los tres paquetes Python del monorepo, de mas baja a mas alta dependencia.
# keni-shared no tiene deps; mcp-metricas usa httpx/pydantic/mcp; consola usa
# starlette/uvicorn. Ninguno se publica en PyPI: se instalan desde la ruta local.
COPY keni-shared/ ./keni-shared/
COPY mcp-metricas/ ./mcp-metricas/
COPY consola/ ./consola/
COPY skills-copy/ ./skills-copy/
# El extra [deck] (python-pptx + reportlab) habilita el reporte del lunes: la
# Consola exporta .pptx y PDF NATIVO (sin LibreOffice) desde la API (#141).
# Extras de persistencia HOSTED (#130): [postgres] (psycopg) y [s3] (boto3), porque en el
# back las vars DATABASE_URL/S3_* estan cableadas y db.py/almacen_media.py las consumen.
RUN pip install ./keni-shared "./mcp-metricas[deck]" "./consola[postgres,s3]" \
 && pip install "uvicorn[standard]>=0.31.1"

EXPOSE 8765
VOLUME ["/data"]

# GET / no exige token (sirve el SPA/placeholder): vale como healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8765/ >/dev/null || exit 1

# --factory: `crear_app()` resuelve token (KENI_CONSOLA_TOKEN) y bootstrapea el
#   admin (#130) desde env. Bind 0.0.0.0 es seguro: el contenedor NO publica
#   puertos al host; solo Traefik lo alcanza por la red interna de Docker.
# --proxy-headers + --forwarded-allow-ips=*: confiar en las X-Forwarded-* de Traefik.
# 1 worker: el runner de jobs es in-process (cola/estado en memoria); con varios
#   workers se romperia. Concurrencia real = KENI_MAX_JOBS dentro del proceso.
CMD ["uvicorn", "keni_consola.app:crear_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8765", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
