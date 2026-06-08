#!/usr/bin/env bash
# Backup LOCAL de keni-social: dump de Postgres (operacional + editorial ESTRUCTURADO,
# lo verdaderamente irreemplazable) + snapshot de la media de Garage. Escribe en
# BACKUP_DIR (def /var/backups/keni-social) con retencion de BACKUP_KEEP dias. Pensado
# como timer systemd diario (mismo patron que deploy/janitor/keni-janitor).
#
# ALCANCE / LIMITE HONESTO: es un backup LOCAL en el MISMO disco. Protege de borrados
# accidentales (`docker volume rm`), bugs y corrupcion logica; NO protege de la perdida
# total del disco/host. Para offsite (lo recomendable antes de escalar), define
# BACKUP_RCLONE_REMOTE en /etc/keni-backup.conf y el script hara `rclone copy` al final
# (instala rclone + configura el remoto una vez). Migrar a offsite = una linea.
#
# Sin secretos en el host: pg_dump corre DENTRO del contenedor db (socket local => auth
# `trust` de la imagen oficial) usando POSTGRES_USER/DB del propio contenedor.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/keni-social}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
DB_CONTAINER="${DB_CONTAINER:-keni-social-db-1}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR/postgres" "$BACKUP_DIR/garage"

echo "==> [1/3] pg_dump ($DB_CONTAINER) -> postgres/keni-$STAMP.sql.gz"
# --no-owner: el restore no exige recrear el rol exacto. pipefail aborta si pg_dump falla.
docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' \
  | gzip -c > "$BACKUP_DIR/postgres/keni-$STAMP.sql.gz.partial"
mv "$BACKUP_DIR/postgres/keni-$STAMP.sql.gz.partial" "$BACKUP_DIR/postgres/keni-$STAMP.sql.gz"

echo "==> [2/3] tar volumenes Garage (meta+data) -> garage/garage-$STAMP.tgz"
# Crash-consistent: la media son blobs; el meta es LMDB (puede quedar mid-write, suele
# restaurar). Consistencia FUERTE de media a futuro: `mc mirror` por la API S3 de Garage.
docker run --rm \
  -v keni-social_garage-meta:/v/meta:ro \
  -v keni-social_garage-data:/v/data:ro \
  -v "$BACKUP_DIR/garage":/backup \
  alpine sh -c "tar czf /backup/garage-$STAMP.tgz.partial -C /v meta data" \
  && mv "$BACKUP_DIR/garage/garage-$STAMP.tgz.partial" "$BACKUP_DIR/garage/garage-$STAMP.tgz"

echo "==> [3/3] retencion (>${BACKUP_KEEP}d) + offsite opcional"
find "$BACKUP_DIR/postgres" -name 'keni-*.sql.gz'  -mtime +"$BACKUP_KEEP" -delete
find "$BACKUP_DIR/garage"   -name 'garage-*.tgz'   -mtime +"$BACKUP_KEEP" -delete
find "$BACKUP_DIR" -name '*.partial' -mtime +1 -delete  # restos de un run fallido

if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  echo "==> rclone copy -> $BACKUP_RCLONE_REMOTE"
  rclone copy "$BACKUP_DIR" "$BACKUP_RCLONE_REMOTE"
fi

echo "==> backup OK: $BACKUP_DIR (retencion ${BACKUP_KEEP}d)"
