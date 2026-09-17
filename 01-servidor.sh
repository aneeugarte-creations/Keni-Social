#!/usr/bin/env bash
# Rescate de keni-social ANTES de apagar el servidor.
# Corre EN EL SERVIDOR (ubuntu@latitude). Deja todo en /var/backups/keni-rescate/<stamp>/.
#
#   ./01-servidor.sh          snapshot CALIENTE: el stack sigue arriba (la app no se cae).
#   ./01-servidor.sh --frio   para el stack antes de copiar: snapshot consistente de verdad.
#
# El backup diario (deploy/backup) solo cubre 3 volumenes. Esto cubre ADEMAS lo que falta:
# pgdata logico, keni-repo, traefik-acme, los dos volumenes de Woodpecker, los secretos y
# la configuracion del host que se aplico a mano.
set -euo pipefail

FRIO=0
[ "${1:-}" = "--frio" ] && FRIO=1

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="/var/backups/keni-rescate/$STAMP"
STACK="/home/ubuntu/keni-social/deploy"
DB_CONTAINER="keni-social-db-1"
PG_IMAGE="postgres:16.13"

sudo mkdir -p "$DEST"/{inventario,volumenes,postgres,secretos,host}
sudo chown -R ubuntu:ubuntu "$DEST"

log() { echo "[rescate] $*"; }
tar_volumen() {   # $1 = nombre del volumen docker, $2 = nombre del fichero de salida
  local vol="$1" out="$2"
  if ! docker volume inspect "$vol" >/dev/null 2>&1; then
    log "AVISO: el volumen $vol no existe, lo salto"; return 0
  fi
  log "volumen $vol -> volumenes/$out.tar.gz"
  docker run --rm -v "$vol":/v:ro -v "$DEST/volumenes":/b alpine \
    tar czf "/b/$out.tar.gz.partial" -C /v .
  mv "$DEST/volumenes/$out.tar.gz.partial" "$DEST/volumenes/$out.tar.gz"
  gzip -t "$DEST/volumenes/$out.tar.gz"   # verifica el CRC del stream completo
  log "  OK $(du -h "$DEST/volumenes/$out.tar.gz" | cut -f1)"
}

# ---------------------------------------------------------------- 1. INVENTARIO
# Lo que hace falta para reconstruir el servidor identico, no solo los datos.
log "=== 1/5 inventario ==="
{
  echo "# Rescate keni-social $STAMP"; echo
  echo "## uname";            uname -a
  echo; echo "## disco";      df -h
  echo; echo "## memoria";    free -h
  echo; echo "## docker ps";  docker ps -a
  echo; echo "## imagenes";   docker images --digests
  echo; echo "## volumenes";  docker volume ls
  echo; echo "## redes";      docker network ls
  echo; echo "## units keni"; systemctl list-units --all 'keni*' --no-pager
  echo; echo "## timers";     systemctl list-timers --all --no-pager
  echo; echo "## fallidas";   systemctl --failed --no-pager
  echo; echo "## ufw";        sudo ufw status verbose
  echo; echo "## iptables DOCKER-USER"; sudo iptables -S DOCKER-USER
  echo; echo "## fail2ban";   sudo fail2ban-client status 2>/dev/null || echo "sin fail2ban"
  echo; echo "## paquetes";   dpkg -l | tail -n +6 | awk '{print $2"\t"$3}'
} > "$DEST/inventario/sistema.txt" 2>&1

# Las VERSIONES desplegadas: sin esto no sabes que imagen corria en produccion.
docker inspect $(docker ps -q) > "$DEST/inventario/docker-inspect.json" 2>/dev/null || true
( cd "$STACK" && docker compose config ) > "$DEST/inventario/compose-resuelto.yml" 2>&1 || true
( cd "$STACK/woodpecker" && docker compose config ) > "$DEST/inventario/compose-woodpecker-resuelto.yml" 2>&1 || true
git -C /home/ubuntu/keni-social rev-parse HEAD > "$DEST/inventario/commit-desplegado.txt" 2>&1 || true

# ------------------------------------------------------- 2. PARADA (solo --frio)
# Garage guarda metadatos en LMDB: en caliente el tar sale crash-consistent. Para el
# snapshot DEFINITIVO (el de antes de apagar) conviene parar y copiar en frio.
if [ "$FRIO" = 1 ]; then
  log "=== 2/5 parando el stack (snapshot en frio) ==="
  ( cd "$STACK" && docker compose stop )
  log "stack parado; NO se borra nada"
else
  log "=== 2/5 snapshot CALIENTE: el stack sigue arriba ==="
fi

# ------------------------------------------------------------- 3. POSTGRES
# Dump logico: restaura en cualquier Postgres 16, a diferencia de un tar de pgdata.
log "=== 3/5 postgres ==="
if [ "$FRIO" = 1 ]; then ( cd "$STACK" && docker compose start db ); sleep 10; fi
docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' \
  > "$DEST/postgres/keni-$STAMP.dump"
docker run --rm -v "$DEST/postgres":/b:ro "$PG_IMAGE" \
  pg_restore --list "/b/keni-$STAMP.dump" > "$DEST/postgres/keni-$STAMP.toc" 
log "  dump OK $(du -h "$DEST/postgres/keni-$STAMP.dump" | cut -f1), verificado con pg_restore --list"
# Copia tambien el volumen crudo: red de seguridad si el dump logico fallara al restaurar.
if [ "$FRIO" = 1 ]; then ( cd "$STACK" && docker compose stop db ); fi
tar_volumen keni-social_pgdata pgdata

# ------------------------------------------------------------- 4. VOLUMENES
log "=== 4/5 volumenes ==="
tar_volumen keni-social_keni-data    keni-data      # /data: editorial, marcas.toml, voces, prompts
tar_volumen keni-social_garage-meta  garage-meta    # metadatos S3 (LMDB)
tar_volumen keni-social_garage-data  garage-data    # los blobs: TODA la media
tar_volumen keni-social_keni-repo    keni-repo      # clon del carril de auto-desarrollo
tar_volumen keni-social_traefik-acme traefik-acme   # certificados TLS
tar_volumen woodpecker_data          woodpecker-data
tar_volumen woodpecker_agent_data    woodpecker-agent-data

# ------------------------------------------------ 5. SECRETOS Y CONFIG DEL HOST
# Nada de esto esta en git: el .env es la fuente de los secretos renderizados, y la
# config del host se aplico a mano desde deploy/host/.
log "=== 5/5 secretos y config del host ==="
sudo cp -a "$STACK/.env"                "$DEST/secretos/env-keni-social"       2>/dev/null || log "AVISO: sin $STACK/.env"
sudo cp -a "$STACK/woodpecker/.env"     "$DEST/secretos/env-woodpecker"        2>/dev/null || log "AVISO: sin .env de woodpecker"
sudo cp -a "$STACK/secrets"             "$DEST/secretos/secrets-renderizados"  2>/dev/null || true
sudo cp -a /home/ubuntu/.ssh/authorized_keys "$DEST/secretos/authorized_keys"  2>/dev/null || true
sudo cp -a /home/ubuntu/.claude         "$DEST/secretos/claude-home"           2>/dev/null || true  # OAuth token de `claude -p`

for f in /etc/keni-backup.conf /etc/keni-alertas.conf /etc/apt/apt.conf.d/52-keni-auto-reboot.conf; do
  sudo cp -a "$f" "$DEST/host/" 2>/dev/null || true
done
sudo cp -a /etc/ssh/sshd_config.d      "$DEST/host/sshd_config.d"   2>/dev/null || true
sudo cp -a /etc/audit/rules.d          "$DEST/host/audit-rules.d"   2>/dev/null || true
sudo cp -a /etc/systemd/system/keni-*  "$DEST/host/"                2>/dev/null || true
sudo crontab -l > "$DEST/host/crontab-root.txt" 2>/dev/null || true
crontab -l      > "$DEST/host/crontab-ubuntu.txt" 2>/dev/null || true

sudo chown -R ubuntu:ubuntu "$DEST"
sudo chmod -R go-rwx "$DEST/secretos"   # 0600: aqui dentro hay credenciales en claro

# --------------------------------------------------------------- CHECKSUMS
# Se verifican al bajar: detectan corrupcion en tranferencia, no solo al escribir.
log "=== checksums ==="
( cd "$DEST" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + | sort -k2 > SHA256SUMS )

if [ "$FRIO" = 1 ]; then
  log "El stack sigue PARADO. Para levantarlo: cd $STACK && docker compose start"
fi
echo
log "LISTO -> $DEST"
du -sh "$DEST"
find "$DEST" -maxdepth 2 -type f -printf '  %10s  %p\n' | sort -k2
