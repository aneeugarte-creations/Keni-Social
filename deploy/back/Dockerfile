# Gateway de keni-social: API Starlette (`consola/`) + fallback del SPA.
#
# El back ENCOLA la generacion (ADR 0002 Fase B); ya NO ejecuta `claude -p`.
# Por eso esta imagen NO lleva Node ni la CLI `claude` (eso vive ahora en la imagen del
# servicio `worker`, ver deploy/worker/Dockerfile). La generacion sigue siendo `claude -p`
# (ADR 0001): la corre el worker, no el back. El back arranca con KENI_WORKER_EXTERNO=1
# para NO levantar su worker in-proceso (lo hace el contenedor `worker`).
#
# Despliegue: corre en cpuset 0-2 dedicado (ver docker-compose.yml) y se actualiza por
# blue-green sin downtime cuando KENI_DEPLOY_BLUEGREEN=1 (ver deploy/deploy.sh).
#
# Contexto de build: la RAIZ del repo (ver deploy/docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Todo el estado de la app (consola.db SQLite, secretos.toml 0600, media,
    # tareas.json) cuelga de XDG_CONFIG_HOME -> volumen montado en /data.
    XDG_CONFIG_HOME=/data \
    # El back NO ejecuta `claude -p`: solo ENCOLA. El servicio `worker` consume la cola.
    KENI_WORKER_EXTERNO=1

# curl: healthcheck + script de nodesource. git: lo usan algunas skills al renderizar.
# Node 20: el back compone la PLANTILLA de marca (logo+copy-in) con el renderer Node
# (`motores/estudio_imagen/render_node`, @napi-rs/canvas prebuilt — sin Cairo) en
# integrar-foto y en el Estudio. NO ejecuta `claude` (eso es del worker).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates git \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Los tres paquetes Python del monorepo, de mas baja a mas alta dependencia.
# keni-shared no tiene deps; mcp-metricas usa httpx/pydantic/mcp; consola usa
# starlette/uvicorn. Ninguno se publica en PyPI: se instalan desde la ruta local.
# ⚠ DEPLOY: la VERSIÓN de esta imagen es un hash de estas mismas entradas (deploy/deploy.sh,
# hash_entradas: keni-shared + mcp-metricas + consola, menos consola/frontend). Si AÑADES
# aquí un `COPY` de OTRA ruta, AÑÁDELA también a ese hash; si no, un cambio en ella no
# reconstruiría la imagen y el código viejo se quedaría en prod (deploy perdido).
COPY keni-shared/ ./keni-shared/
COPY mcp-metricas/ ./mcp-metricas/
COPY consola/ ./consola/
# El extra [deck] (python-pptx + reportlab) habilita el reporte del lunes: la
# Consola exporta .pptx y PDF NATIVO (sin LibreOffice) desde la API.
# Extras de persistencia HOSTED: [postgres] (psycopg) y [s3] (boto3), porque en el
# back las vars DATABASE_URL/S3_* estan cableadas y db.py/almacen_media.py las consumen.
# Cache de descargas/wheels de pip en un mount de BuildKit (NO viaja a la imagen): cuando un
# cambio de fuente invalida esta capa, pip reutiliza los wheels ya bajados en vez de re-descargar
# y recompilar todo el árbol de dependencias.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install ./keni-shared "./mcp-metricas[deck]" "./consola[postgres,s3]" \
 && pip install "uvicorn[standard]>=0.31.1"

# Renderer Node de la plantilla de marca: instala SOLO sus deps de runtime (@napi-rs/canvas
# trae binarios prebuilt; no compila Cairo). `node_modules` no viaja en el contexto
# (.dockerignore); se instala en la UBICACIÓN INSTALADA del paquete (site-packages), que es
# donde el subproceso resuelve `componer.mjs` (keni_consola.__file__), desde el lock versionado.
RUN RN="$(python -c 'import keni_consola, os; print(os.path.join(os.path.dirname(keni_consola.__file__), "motores", "estudio_imagen", "render_node"))')" \
 && npm --prefix "$RN" ci --omit=dev \
 && npm cache clean --force

# HARDENING: el proceso NO corre como root. Creamos un usuario sin privilegios y le
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

# Liveness por /healthz: 200 JSON barato, sin token ni BD, y SIN pasar por el servido del
# SPA. Pegar a `/` arrastra FileResponse + todo el middleware, que bajo carga del unico
# worker uvicorn puede tardar y fallar el chequeo, marcando el contenedor "unhealthy"; como
# Traefik NO enruta a contenedores no-sanos, eso tiraria el router `back` y los POST /api
# caerian al nginx del front -> "405 Not Allowed".
# start-period AMPLIO (120s): durante un deploy el server corre hasta 3 pipelines de CI a
# la vez (builds tsc/vite + pytest), y arrancar los 2 workers uvicorn bajo esa carga puede
# tardar >>20s en ligar :8765; un start-period corto los marcaria "unhealthy" y dispararia
# un rollback espurio con el codigo perfectamente OK.
# start-interval (5s): durante el start-period se sondea cada 5s (no cada 30s), así el back se
# marca `healthy` en cuanto liga :8765 y el deploy no espera al siguiente tick de 30s. Tras
# quedar sano vuelve al interval de 30s normal. Solo adelanta la detección; nunca la retrasa.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --start-interval=5s --retries=3 \
  CMD curl -fsS http://localhost:8765/healthz >/dev/null || exit 1

# --factory: `crear_app()` resuelve token (KENI_CONSOLA_TOKEN) y bootstrapea el
#   admin desde env. Bind 0.0.0.0 es seguro: el contenedor NO publica
#   puertos al host; solo Traefik lo alcanza por la red interna de Docker.
# --proxy-headers + --forwarded-allow-ips: confiar en las X-Forwarded-* SOLO desde la red
#   privada Docker (172.16.0.0/12 cubre los rangos por defecto de bridge/compose), no desde
#   cualquier IP ("*"). Traefik puede correr en host-mode, pero alcanza al back por la red
#   interna del compose, asi que la IP de origen cae en ese rango privado. OJO: si cambia la
#   topologia de red (otra subred Docker, ingress en otra red, etc.) hay que ajustar este valor.
# 2 workers uvicorn: el back NO ejecuta `claude -p` (eso es el servicio `worker`), pero SI
#   es un proceso interactivo de cara al equipo: sirve /api (UI humana), /mcp (trafico de
#   agentes Claude Code) y SSE de larga vida (generacion token a token) — todo en el mismo
#   proceso. Con 1 solo worker eso es un cuello + micro-SPOF: una SSE colgada o un /mcp lento
#   degrada la UI, y un reciclaje del proceso corta a todos. Subimos a 2 (resiliencia y
#   concurrencia baratas). Es SEGURO multi-proceso: el back es STATELESS entre peticiones —
#   sesiones y cola de jobs viven en Postgres compartido, no en memoria; arranca con
#   KENI_WORKER_EXTERNO=1 (no levanta worker in-proceso) y NO corre daemons/scheduler
#   in-proc (eso es el servicio `daemons`). El bootstrap y las migraciones del arranque son
#   idempotentes y best-effort (correr 2 veces es inocuo). El lifespan del MCP (session
#   manager + cliente in-proc) es por-proceso, asi que cada worker tiene el suyo: correcto.
#   No subir mas alla de 2 sin re-presupuestar RAM (cada worker reimporta la app entera; el
#   mem_limit/cpus del back en el compose estan dimensionados para 2). Concurrencia real de
#   GENERACION = KENI_MAX_JOBS por proceso worker (el tope de admision lo respeta tambien el
#   encolado del back).
CMD ["uvicorn", "keni_consola.app:crear_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8765", "--workers", "2", \
     "--proxy-headers", "--forwarded-allow-ips=172.16.0.0/12"]
