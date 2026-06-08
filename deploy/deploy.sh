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

# Tag VERSIONADO para que el janitor (deploy/janitor) conserve N versiones por imagen y
# permita rollback legible. Sin override => timestamp. Compose interpola ${KENI_VERSION:-latest}.
KENI_VERSION="${KENI_VERSION:-$(date +%Y%m%d-%H%M%S)}"
export KENI_VERSION
echo "==> version de build: $KENI_VERSION"

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

echo "==> [1/5] build de imagenes (back SIN Node, worker CON claude, front, mcp)"
$DC build
# Cada imagen versionada apunta tambien a :latest (conveniencia/rollback legible).
for svc in front back worker mcp; do
  docker tag "keni-social/$svc:$KENI_VERSION" "keni-social/$svc:latest" || true
done

echo "==> [2/5] stop back (breve indisponibilidad mientras se aplica el esquema)"
$DC stop back || true

echo "==> [3/5] chown del volumen de estado a uid no-root 10001 (back/worker corren no-root)"
docker run --rm -v "$VOL":/d alpine chown -R 10001:10001 /d

echo "==> [4/5] asegura esquema Postgres (idempotente; ADR 0004)"
$DC run --rm --no-deps -T back python -m keni_consola.migracion --solo-db

echo "==> [5/5] up (recrea back no-root sobre Postgres + arranca el worker de generacion)"
$DC up -d
$DC ps
echo "==> OK. El esquema se crea idempotente al arrancar el back; este paso lo adelanta."
