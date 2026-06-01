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

echo "==> [4/5] asegura esquema Postgres + copia editorial YAML->PG (idempotente; ADR 0004/0006)"
$DC run --rm --no-deps -T back python -m keni_consola.migracion --solo-db

echo "==> [5/5] up (recrea back no-root sobre Postgres + arranca el worker de generacion)"
$DC up -d
$DC ps
echo "==> OK. El esquema se crea idempotente al arrancar el back; este paso lo adelanta."
