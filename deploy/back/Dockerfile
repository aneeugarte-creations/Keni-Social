# Gateway de keni-social: API Starlette (`consola/`) + fallback del SPA.
#
# El back ENCOLA la generacion (#130 Fase 2 / ADR 0002 Fase B); ya NO ejecuta `claude -p`.
# Por eso esta imagen NO lleva Node ni la CLI `claude` (eso vive ahora en la imagen del
# servicio `worker`, ver deploy/worker/Dockerfile). La generacion sigue siendo `claude -p`
# (ADR 0001): la corre el worker, no el back. El back arranca con KENI_WORKER_EXTERNO=1
# para NO levantar su worker in-proceso (lo hace el contenedor `worker`).
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
    KENI_SKILLS_CWD=/app \
    # El back NO ejecuta `claude -p`: solo ENCOLA. El servicio `worker` consume la cola.
    KENI_WORKER_EXTERNO=1

# curl: solo para el healthcheck. git: lo usan algunas skills al renderizar. SIN Node ni
# `claude` (el back ya no genera; eso lo hace la imagen del worker).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates git \
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

# HARDENING (#130): el proceso NO corre como root. Creamos un usuario sin privilegios y le
# damos /app (codigo, solo lectura en runtime) y /data (estado: SQLite, secretos 0600, media).
# Crear y CHOWNear /data AQUI cubre el caso de un volumen NUEVO (Docker copia el contenido y
# los permisos de este punto de montaje al inicializarlo). OJO con un volumen YA EXISTENTE
# (poblado siendo root en un deploy anterior): Docker NO re-chownea uno con datos, asi que hay
# que ajustarlo UNA vez en el host (ver deploy/README.md, "Hardening / contenedor no-root").
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin keni \
 && mkdir -p /data \
 && chown -R keni:keni /app /data
USER keni

EXPOSE 8765
VOLUME ["/data"]

# GET / no exige token (sirve el SPA/placeholder): vale como healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8765/ >/dev/null || exit 1

# --factory: `crear_app()` resuelve token (KENI_CONSOLA_TOKEN) y bootstrapea el
#   admin (#130) desde env. Bind 0.0.0.0 es seguro: el contenedor NO publica
#   puertos al host; solo Traefik lo alcanza por la red interna de Docker.
# --proxy-headers + --forwarded-allow-ips=*: confiar en las X-Forwarded-* de Traefik.
# 1 worker uvicorn: el back solo ENCOLA (la cola vive en Postgres compartido). La
#   ejecucion (`claude -p`) corre en el servicio `worker`. Concurrencia real = KENI_MAX_JOBS
#   por proceso worker (el tope de admision lo respeta tambien el encolado del back).
CMD ["uvicorn", "keni_consola.app:crear_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8765", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
