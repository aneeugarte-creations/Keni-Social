#!/usr/bin/env bash
# Rescate de los OTROS stacks del host (todo lo que no es keni-social).
# El servidor sirve 7 dominios; apagarlo se los lleva a todos.
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="/var/backups/keni-rescate/otros-$STAMP"
sudo mkdir -p "$DEST"/{inventario,volumenes,postgres,secretos}
sudo chown -R ubuntu:ubuntu "$DEST"
log() { echo "[otros] $*"; }

# Dumps LOGICOS: restauran en cualquier Postgres y ocupan una fraccion del volumen crudo.
# woodpecker_pg_data son 9.8G en disco; su dump son unos cientos de MB.
dump_db() {   # $1 = contenedor, $2 = nombre de salida
  local cont="$1" out="$2"
  docker ps --format '{{.Names}}' | grep -qx "$cont" || { log "AVISO: $cont no corre, lo salto"; return 0; }
  log "pg_dump $cont -> postgres/$out.dump"
  # El usuario/base salen del entorno del propio contenedor: no hace falta saber sus credenciales.
  docker exec "$cont" sh -c 'pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" -Fc --no-owner' \
    > "$DEST/postgres/$out.dump" 2>"$DEST/postgres/$out.err" \
    || { log "  FALLO (ver postgres/$out.err)"; return 0; }
  log "  OK $(du -h "$DEST/postgres/$out.dump" | cut -f1)"
}

tar_vol() {   # $1 = volumen, $2 = salida
  docker volume inspect "$1" >/dev/null 2>&1 || { log "AVISO: sin volumen $1"; return 0; }
  log "volumen $1"
  docker run --rm -v "$1":/v:ro -v "$DEST/volumenes":/b alpine \
    tar czf "/b/$2.tar.gz.partial" -C /v . 2>/dev/null
  mv "$DEST/volumenes/$2.tar.gz.partial" "$DEST/volumenes/$2.tar.gz"
  gzip -t "$DEST/volumenes/$2.tar.gz"
  log "  OK $(du -h "$DEST/volumenes/$2.tar.gz" | cut -f1)"
}

log "=== 1/4 bases de datos (dump logico) ==="
dump_db keni-ops-stg-db-1  keni-ops-stg
dump_db deploy-errors-db-1 errores
dump_db keni-voice-db-1    keni-voice
dump_db woodpecker-postgres woodpecker-ci

log "=== 2/4 volumenes de datos ==="
# keni-voice (audio.kenitech.io)
tar_vol keni-voice_voice-models   voice-models
tar_vol keni-voice_voice-media    voice-media
tar_vol keni-voice_voice-claude   voice-claude
tar_vol keni-voice_voice-scratch  voice-scratch
tar_vol keni-voice_voice-postgres voice-postgres
# keni-guardian (guardian.kenitech.io) — pnpm-store es cache, se omite a proposito
tar_vol keni-guardian_repos      guardian-repos
tar_vol keni-guardian_trace      guardian-trace
tar_vol keni-guardian_claude-cfg guardian-claude-cfg
tar_vol keni-guardian_config     guardian-config
tar_vol keni-guardian_secrets    guardian-secrets
tar_vol keni-guardian_gh-cfg     guardian-gh-cfg
# keni-ops staging (ops-stg / ops-admin)
tar_vol keni-ops-stg_keni-ops-data  ops-stg-data
tar_vol keni-ops-stg_keni-ops-media ops-stg-media
# stack de errores (errors-stg)
tar_vol deploy_keni-ops-errors-data    errores-data
tar_vol deploy_keni-ops-errors-uploads errores-uploads
# CI: el server-data; pg_data ya va como dump logico arriba
tar_vol woodpecker_woodpecker-server-data woodpecker-server-data
# Restos sueltos del stack de keni-social que no cuelgan de ningun contenedor
tar_vol keni-social_keeper-secrets       keeper-secrets
tar_vol keni-social_keeper-trace         keeper-trace
tar_vol keni-social_guardian-claude-cfg  social-guardian-claude-cfg
# Las cache (pnpm-*, turbo-*, wp_*) se omiten: se regeneran solas y son GB inutiles.

log "=== 3/4 configuracion y secretos de cada stack ==="
for s in keni-voice keni-guardian keni-ops keni-ops-staging-login; do
  d="/home/ubuntu/$s"
  [ -d "$d" ] || continue
  mkdir -p "$DEST/secretos/$s"
  # Los .env y los compose: sin ellos los volumenes no dicen como levantarlos.
  sudo find "$d" -maxdepth 3 \( -name ".env*" -o -name "compose*.y*ml" -o -name "docker-compose*.y*ml" \) \
    -not -path "*/node_modules/*" -exec cp -a {} "$DEST/secretos/$s/" \; 2>/dev/null || true
  n=$(ls -1 "$DEST/secretos/$s" 2>/dev/null | wc -l)
  log "  $s: $n ficheros de config"
done
# Cosas sueltas del home que nadie respalda
sudo cp -a /home/ubuntu/backups                    "$DEST/secretos/home-backups"    2>/dev/null || true
sudo cp -a /home/ubuntu/woodpecker-upgrade-backups "$DEST/secretos/wp-upgrade-bk"   2>/dev/null || true
sudo cp -a /home/ubuntu/*.tar.gz /home/ubuntu/*.sql /home/ubuntu/*.csv "$DEST/secretos/" 2>/dev/null || true

log "=== 4/4 inventario y checksums ==="
{
  echo "# Otros stacks — $STAMP"
  echo; echo "## contenedores"; docker ps -a
  echo; echo "## volumenes";    docker volume ls
  echo; echo "## imagenes";     docker images --digests
  echo; echo "## rutas traefik"; docker ps --format '{{.Names}} {{.Labels}}' | tr ',' '\n' | grep -i "rule\|Host(" || true
} > "$DEST/inventario/otros.txt" 2>&1

sudo chown -R ubuntu:ubuntu "$DEST"; sudo chmod -R go-rwx "$DEST/secretos"
( cd "$DEST" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + | sort -k2 > SHA256SUMS )
echo; log "LISTO -> $DEST"; du -sh "$DEST"
