#!/bin/sh
# Despliegue / cutover de keni-social en el server Latitude (mismo host que el agente
# Woodpecker). Lo invoca `.woodpecker/deploy.yml` (disparo manual) montando el
# docker.sock del host y el .env de secretos; tambien sirve para correrlo a mano por SSH:
#
#   cd /home/ubuntu/keni-social/deploy && sh deploy.sh .env
#
# Idempotente y NO destructivo. La operacional vive en Postgres (ADR 0004; SQLite ya no
# existe); el paso de migracion garantiza el esquema (no-op tras la ADR). La media sigue
# en DISCO hasta que se bootstrapee Garage y se pongan las S3_* reales en el .env (ver
# deploy/README.md, "Cutover a Postgres + S3").
set -eu

# Ubicarse en deploy/ (el contexto de build de las imagenes propias es la raiz `..`).
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

ENVFILE="${1:-.env}"
DC="docker compose --env-file $ENVFILE"
VOL="keni-social_keni-data"   # volumen de estado (proyecto compose = keni-social)

# VERSIONADO POR CONTENIDO (deploy QUIRÚRGICO). Antes la tag era un TIMESTAMP único por deploy,
# igual para las 4 imágenes: como cambiaba SIEMPRE, el `up -d` final RECREABA TODOS los
# contenedores en cada deploy —incluido el `worker`, abortando sus `claude -p` en vuelo— aunque
# el cambio fuese solo de front. Ahora la tag de CADA imagen es un HASH de SUS entradas de build;
# así solo se (re)construye y recrea el servicio cuyo contenido cambió. Un deploy de SOLO front
# (o solo mcp) NO toca el worker. back y worker comparten `consola/`: un cambio ahí recrea ambos
# (el worker DEBE correr ese código). El hash sale del ÁRBOL de ficheros (no de git: este script
# corre en el dir estable del host, cuyo .git puede no estar sincronizado). El janitor sigue
# conservando N por repo (ordena por CreatedAt); una imagen sin cambios no se reconstruye.
RAIZ="$(cd .. && pwd)"   # raíz del repo (deploy/ es el cwd; el contexto de build es `..`)
hash_entradas() {  # $@ = paths relativos a la raíz -> 12 hex del CONTENIDO (orden estable)
  ( cd "$RAIZ" && find "$@" -type d \( -name node_modules -o -name .git -o -name __pycache__ \
        -o -name '.venv*' -o -name .ruff_cache -o -name webapp -o -name dist \) -prune \
        -o -type f -print 2>/dev/null | LC_ALL=C sort | xargs sha1sum 2>/dev/null ) \
    | sha1sum | cut -c1-12
}
# Entradas de build de cada imagen (ver los Dockerfile en deploy/<svc>/). OJO: para back/worker
# hasheamos el PAQUETE Python (consola/src + consola/pyproject.toml), NO `consola` entero: el
# Dockerfile copia `consola/` completo pero solo `pip install ./consola`, así que `consola/frontend`
# y `consola/tests` NO afectan al runtime. Si los incluyéramos, un cambio de SOLO front recrearía
# back+worker —justo lo que queremos evitar—. front sí bundlea consola/frontend. Se añade el dir
# deploy/<svc> (Dockerfile + entrypoint/nginx.conf) para que un cambio en la receta reconstruya.
FRONT_VERSION="$(hash_entradas consola/frontend deploy/front)"
BACK_VERSION="$(hash_entradas keni-shared mcp-metricas consola/src consola/pyproject.toml deploy/back)"
WORKER_VERSION="$(hash_entradas keni-shared mcp-metricas consola/src consola/pyproject.toml deploy/worker)"
MCP_VERSION="$(hash_entradas keni-shared mcp-metricas deploy/mcp)"
export FRONT_VERSION BACK_VERSION WORKER_VERSION MCP_VERSION
echo "==> versiones por contenido: front=$FRONT_VERSION back=$BACK_VERSION worker=$WORKER_VERSION mcp=$MCP_VERSION"

# Render de secretos ANTES de cualquier `compose build/run/up`: los servicios montan
# ./secrets/<n> en /run/secrets; si no existieran al instanciar contenedores, Compose
# fallaria. El codigo los lee via env `*_FILE` (no viajan como env -> no salen en
# `docker inspect`). El operador sigue editando el .env; este render es derivado.
#
# PERMISOS: el DIRECTORIO es 0700 (solo root/dueño entra) -> en el HOST nadie sin
# privilegios lee los secretos. Los FICHEROS son 0644 a proposito: Compose (no-swarm)
# bind-montea el fichero del host TAL CUAL en /run/secrets, y los contenedores de app
# corren como usuario NO-root (uid 10001); con 0600 root no podrian leerlos (back caeria
# a SQLite, el worker se quedaria sin credencial de Claude, S3/MCP off). 0644 dentro de un
# dir 0700 = legible por el usuario del contenedor PERO no por terceros en el host (el dir
# bloquea el traverse). Es el mismo modelo que el `mode: 0444` por defecto de Docker secrets.
echo "==> [1a/5] render de secretos a ./secrets/ (dir 0700, ficheros 0644)"
SECRETS_DIR="$(pwd)/secrets"
mkdir -p "$SECRETS_DIR"; chmod 700 "$SECRETS_DIR"
render_secret() {  # $1 = clave en .env ; $2 = nombre del fichero de secreto
  val="$(sed -n "s/^$1=//p" "$ENVFILE" | head -n1)"
  val="${val%\"}"; val="${val#\"}"      # quita comillas envolventes opcionales
  printf '%s' "$val" > "$SECRETS_DIR/$2"
  chmod 644 "$SECRETS_DIR/$2"           # legible por el uid no-root del contenedor (dir 0700 protege en host)
}
render_secret POSTGRES_PASSWORD        postgres_password
render_secret S3_ACCESS_KEY            s3_access_key
render_secret S3_SECRET_KEY            s3_secret_key
render_secret ANTHROPIC_API_KEY        anthropic_api_key
render_secret CLAUDE_CODE_OAUTH_TOKEN  claude_code_oauth_token
render_secret KENI_CONSOLA_ADMIN_PASS  consola_admin_pass
render_secret KENI_CONSOLA_TOKEN       consola_token
render_secret KENI_MCP_BEARER          mcp_bearer

# Build SELECTIVO: cada servicio se (re)construye SOLO si su imagen-por-hash no existe ya (=
# su contenido cambió). Si ya existe, se salta -> su tag NO cambia -> el `up -d` final no lo
# recrea (ni interrumpe el worker). `daemons` comparte la imagen de `back` (no se build aparte).
# `cambio` (imagen AÚN no construida) marca los flags ANTES de construir, para gatear los pasos
# de esquema/estado. La detección va SEPARADA del build a propósito: así un fallo de `$DC build`
# aborta el deploy por `set -e` (sin `|| true` que lo enmascare) y deja prod intacto.
cambio() { ! docker image inspect "$1" >/dev/null 2>&1; }  # 0 (true) si la imagen NO existe aún
BACK_CAMBIO=0; WORKER_CAMBIO=0
cambio "keni-social/back:$BACK_VERSION"     && BACK_CAMBIO=1   || true
cambio "keni-social/worker:$WORKER_VERSION" && WORKER_CAMBIO=1 || true

construir() {  # $1 = servicio compose ; $2 = imagen:tag esperada (keni-social/<svc>:<hash>)
  if docker image inspect "$2" >/dev/null 2>&1; then
    echo "==> $1: sin cambios ($2 ya existe) — no se reconstruye ni recrea"
    return 0
  fi
  echo "==> $1: cambió -> build $2"
  $DC build "$1"                                     # un fallo aquí aborta el deploy (set -e)
  docker tag "$2" "keni-social/$1:latest" || true   # :latest = conveniencia/rollback legible
}
echo "==> [1/5] build SELECTIVO (solo imagenes cuyo contenido cambió)"
construir front  "keni-social/front:$FRONT_VERSION"
construir back   "keni-social/back:$BACK_VERSION"
construir worker "keni-social/worker:$WORKER_VERSION"
construir mcp    "keni-social/mcp:$MCP_VERSION"

# Pasos de ESQUEMA/ESTADO: SOLO cuando cambió el código del back/worker (comparten `consola/`).
# Un deploy de solo front no toca el esquema ni el volumen de estado (ni para el back).
if [ "$BACK_CAMBIO" = 1 ]; then
  echo "==> [2/5] stop back (breve indisponibilidad mientras se aplica el esquema)"
  $DC stop back || true
else
  echo "==> [2/5] back sin cambios — no se para (sin indisponibilidad)"
fi

if [ "$BACK_CAMBIO" = 1 ] || [ "$WORKER_CAMBIO" = 1 ]; then
  echo "==> [3/5] chown del volumen de estado a uid no-root 10001 (back/worker corren no-root)"
  docker run --rm -v "$VOL":/d alpine chown -R 10001:10001 /d
else
  echo "==> [3/5] back/worker sin cambios — se omite chown del volumen"
fi

if [ "$BACK_CAMBIO" = 1 ]; then
  echo "==> [4/5] asegura esquema Postgres (idempotente; ADR 0004)"
  $DC run --rm --no-deps -T back python -m keni_consola.migracion --solo-db
else
  echo "==> [4/5] back sin cambios — esquema ya vigente, se omite la migración"
fi

echo "==> [5/5] up (recrea SOLO los servicios cuya imagen o config cambió)"
$DC up -d
$DC ps
echo "==> OK. Los servicios sin cambios (p.ej. el worker en un deploy de front) NO se recrearon."
