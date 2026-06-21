#!/usr/bin/env bash
# Backup LOCAL de keni-social: dump de Postgres (operacional + editorial ESTRUCTURADO) +
# tar de los TRES volumenes de estado.
#
# Cubre:
#   postgres/keni-<stamp>.dump            pg_dump -Fc (CUSTOM): comprimido y restaurable con
#                                         pg_restore selectivo/paralelo.
#   volumes/keni-data-<stamp>.tar.gz      estado de la app: secretos.toml, editorial YAML,
#                                         media-en-disco, tareas.
#   volumes/garage-meta-<stamp>.tar.gz    metadatos de Garage (LMDB).
#   volumes/garage-data-<stamp>.tar.gz    blobs de media S3.
#   estado.json                           resultado del ULTIMO run (ok/fallo, bytes,
#                                         verificacion, duracion) para el panel Sistema.
#
# VERIFICACION: un backup sin probar no es un backup. Cada run VERIFICA lo
# que acaba de escribir: el dump con `pg_restore --list` (lee el TOC entero del archivo
# custom; detecta dumps truncados/corruptos) y cada tar.gz con `gzip -t` (CRC del stream
# completo). El resultado queda en estado.json (`verificado`) y un fallo de verificacion
# FALLA el run (OnFailure= -> keni-alertas). El restore COMPLETO en un Postgres efimero se
# prueba a mano (ver deploy/host/README.md §1); esto cubre la corrupcion silenciosa diaria.
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
# Imagen para verificar el dump FUERA del contenedor vivo (ya esta en el host: es la del
# servicio db). pg_restore --list necesita ver el fichero, que vive en el host.
PG_IMAGE="${PG_IMAGE:-postgres:16.13}"
VOLUMES="keni-social_keni-data keni-social_garage-meta keni-social_garage-data"
STAMP="$(date +%Y%m%d-%H%M%S)"
T_INICIO="$(date +%s)"

mkdir -p "$BACKUP_DIR/postgres" "$BACKUP_DIR/volumes"
# Legible para el panel Sistema: el back (contenedor NO-root) monta $BACKUP_DIR :ro y
# necesita atravesar los dirs y leer estado.json/dumps. 755/644 es aceptable aqui: el
# host es single-admin (ubuntu+root); los secretos reales van aparte (deploy/secrets 0400).
chmod 755 "$BACKUP_DIR" "$BACKUP_DIR/postgres" "$BACKUP_DIR/volumes" 2>/dev/null || true
echo "[keni-backup] START $STAMP"

# --- estado.json para el panel Sistema (la Consola monta $BACKUP_DIR solo-lectura). Se
#     escribe SIEMPRE (exito o fallo vía trap ERR) y de forma atomica (.tmp -> mv).
ESTADO="$BACKUP_DIR/estado.json"
PASO="inicio"
VERIFICADO=false
DUMP_BYTES=0
VOLS_JSON=""
escribir_estado() {  # $1 = true|false (ok)   $2 = texto de error ("" si ok)
  local dur=$(( $(date +%s) - T_INICIO ))
  local err; err="$(printf '%s' "${2:-}" | tr '"\n' "'_")"
  printf '{"stamp":"%s","ok":%s,"paso":"%s","error":"%s","duracion_seg":%d,"dump_bytes":%d,"verificado":%s,"volumenes":[%s]}\n' \
    "$STAMP" "$1" "$PASO" "$err" "$dur" "$DUMP_BYTES" "$VERIFICADO" "$VOLS_JSON" \
    > "$ESTADO.tmp" && mv "$ESTADO.tmp" "$ESTADO"
}
trap 'escribir_estado false "fallo en el paso: $PASO"' ERR

# --- Postgres: formato custom (-Fc). Escritura atomica (.partial -> rename).
PASO="pg_dump"
echo "[keni-backup] pg_dump -Fc -> postgres/keni-$STAMP.dump"
docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' \
  > "$BACKUP_DIR/postgres/keni-$STAMP.dump.partial"
mv "$BACKUP_DIR/postgres/keni-$STAMP.dump.partial" "$BACKUP_DIR/postgres/keni-$STAMP.dump"
DUMP_BYTES="$(stat -c %s "$BACKUP_DIR/postgres/keni-$STAMP.dump")"

# --- Verificacion del dump: pg_restore --list lee el TOC del archivo custom entero;
#     un dump truncado/corrupto falla aqui (y el run entero, via set -e + trap).
PASO="verificar_dump"
echo "[keni-backup] verify: pg_restore --list (dump de $DUMP_BYTES bytes)"
docker run --rm -v "$BACKUP_DIR/postgres":/b:ro "$PG_IMAGE" \
  pg_restore --list "/b/keni-$STAMP.dump" > /dev/null

# --- Volumenes de estado: tar de cada uno (crash-consistent; el LMDB de Garage puede quedar
#     mid-write, suele restaurar. Consistencia fuerte de media a futuro: `mc mirror` por S3).
for vol in $VOLUMES; do
  short="${vol#keni-social_}"
  PASO="tar_$short"
  echo "[keni-backup] volume $vol -> volumes/$short-$STAMP.tar.gz"
  docker run --rm -v "$vol":/v:ro -v "$BACKUP_DIR/volumes":/backup alpine \
    tar czf "/backup/$short-$STAMP.tar.gz.partial" -C /v . \
    && mv "$BACKUP_DIR/volumes/$short-$STAMP.tar.gz.partial" "$BACKUP_DIR/volumes/$short-$STAMP.tar.gz"
  # Verificacion del tar: gzip -t valida el CRC del stream COMPLETO (detecta truncados).
  PASO="verificar_$short"
  gzip -t "$BACKUP_DIR/volumes/$short-$STAMP.tar.gz"
  bytes="$(stat -c %s "$BACKUP_DIR/volumes/$short-$STAMP.tar.gz")"
  VOLS_JSON="${VOLS_JSON:+$VOLS_JSON,}{\"volumen\":\"$short\",\"bytes\":$bytes}"
done
VERIFICADO=true

# --- Retencion + limpieza de restos de runs fallidos.
PASO="retencion"
echo "[keni-backup] prune > ${BACKUP_KEEP}d"
find "$BACKUP_DIR/postgres" -name 'keni-*.dump'   -mtime +"$BACKUP_KEEP" -delete
find "$BACKUP_DIR/volumes"  -name '*.tar.gz'       -mtime +"$BACKUP_KEEP" -delete
find "$BACKUP_DIR" -name '*.partial' -mtime +1 -delete

# --- Offsite opcional.
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  PASO="rclone"
  echo "[keni-backup] rclone copy -> $BACKUP_RCLONE_REMOTE"
  rclone copy "$BACKUP_DIR" "$BACKUP_RCLONE_REMOTE"
fi

PASO="fin"
escribir_estado true ""
echo "[keni-backup] DONE $STAMP | dir=$BACKUP_DIR keep=${BACKUP_KEEP}d verificado=$VERIFICADO"
