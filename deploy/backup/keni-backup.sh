#!/usr/bin/env bash
# Backup LOCAL de keni-social: dump de Postgres (operacional + editorial ESTRUCTURADO) +
# tar de los TRES volumenes de estado. Versiona en git el keni-backup que ya vivia en el
# host sin estar trackeado (se habria perdido en una reconstruccion del host) y conserva su
# diseno: formato de dump y layout/nombres compatibles con los ficheros ya existentes.
#
# Cubre:
#   postgres/keni-<stamp>.dump            pg_dump -Fc (CUSTOM): comprimido y restaurable con
#                                         pg_restore selectivo/paralelo.
#   volumes/keni-data-<stamp>.tar.gz      estado de la app: secretos.toml, editorial YAML,
#                                         media-en-disco, tareas.
#   volumes/garage-meta-<stamp>.tar.gz    metadatos de Garage (LMDB).
#   volumes/garage-data-<stamp>.tar.gz    blobs de media S3.
#
# ALCANCE / LIMITE HONESTO: backup LOCAL en el MISMO disco. Protege de borrados accidentales
# (`docker volume rm`), bugs y corrupcion logica; NO de la perdida total del disco/host. Para
# offsite (recomendable al escalar), define BACKUP_RCLONE_REMOTE en /etc/keni-backup.conf:
# el script hara `rclone copy` al final. Sin secretos en el host: pg_dump corre DENTRO del
# contenedor db (socket local => auth trust de la imagen oficial) con POSTGRES_USER/DB suyas.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/keni-social}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
DB_CONTAINER="${DB_CONTAINER:-keni-social-db-1}"
VOLUMES="keni-social_keni-data keni-social_garage-meta keni-social_garage-data"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR/postgres" "$BACKUP_DIR/volumes"
echo "[keni-backup] START $STAMP"

# --- Postgres: formato custom (-Fc). Escritura atomica (.partial -> rename).
echo "[keni-backup] pg_dump -Fc -> postgres/keni-$STAMP.dump"
docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' \
  > "$BACKUP_DIR/postgres/keni-$STAMP.dump.partial"
mv "$BACKUP_DIR/postgres/keni-$STAMP.dump.partial" "$BACKUP_DIR/postgres/keni-$STAMP.dump"

# --- Volumenes de estado: tar de cada uno (crash-consistent; el LMDB de Garage puede quedar
#     mid-write, suele restaurar. Consistencia fuerte de media a futuro: `mc mirror` por S3).
for vol in $VOLUMES; do
  short="${vol#keni-social_}"
  echo "[keni-backup] volume $vol -> volumes/$short-$STAMP.tar.gz"
  docker run --rm -v "$vol":/v:ro -v "$BACKUP_DIR/volumes":/backup alpine \
    tar czf "/backup/$short-$STAMP.tar.gz.partial" -C /v . \
    && mv "$BACKUP_DIR/volumes/$short-$STAMP.tar.gz.partial" "$BACKUP_DIR/volumes/$short-$STAMP.tar.gz"
done

# --- Retencion + limpieza de restos de runs fallidos.
echo "[keni-backup] prune > ${BACKUP_KEEP}d"
find "$BACKUP_DIR/postgres" -name 'keni-*.dump'   -mtime +"$BACKUP_KEEP" -delete
find "$BACKUP_DIR/volumes"  -name '*.tar.gz'       -mtime +"$BACKUP_KEEP" -delete
find "$BACKUP_DIR" -name '*.partial' -mtime +1 -delete

# --- Offsite opcional.
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  echo "[keni-backup] rclone copy -> $BACKUP_RCLONE_REMOTE"
  rclone copy "$BACKUP_DIR" "$BACKUP_RCLONE_REMOTE"
fi

echo "[keni-backup] DONE $STAMP | dir=$BACKUP_DIR keep=${BACKUP_KEEP}d"
