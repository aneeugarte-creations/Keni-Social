#!/usr/bin/env bash
# Baja el rescate del servidor, lo verifica y cifra los secretos. Corre EN EL MAC.
#   ./02-bajar-y-verificar.sh <stamp> [destino]
# <stamp> es el directorio que imprimio 01-servidor.sh (p.ej. 20260917-142530).
set -euo pipefail

STAMP="${1:?falta el stamp, p.ej. 20260917-142530}"
DESTINO="${2:-$HOME/keni-social-rescate}"
REMOTO="latitude"                      # usa ~/.ssh/config; por tailnet, que evita fail2ban
ORIGEN="/var/backups/keni-rescate/$STAMP"
LOCAL="$DESTINO/$STAMP"

log() { echo "[rescate] $*"; }
mkdir -p "$LOCAL"

# ------------------------------------------------------------------ 1. BAJAR
# --partial + --append-verify: si se corta a mitad de un tar de varios GB, reanuda.
log "=== 1/5 bajando $ORIGEN ==="
rsync -avhP --append-verify \
  -e "ssh -o ControlMaster=auto -o ControlPath=$HOME/.ssh/cm/lat-%r@%h:%p -o ControlPersist=30m" \
  "$REMOTO:$ORIGEN/" "$LOCAL/"

# Tambien el backup diario que ya existia: son las fotos de dias anteriores, por si la
# de hoy tuviera datos ya corrompidos por un fallo que nadie vio.
log "=== 2/5 bajando el historico de backups diarios ==="
rsync -avhP --append-verify \
  -e "ssh -o ControlMaster=auto -o ControlPath=$HOME/.ssh/cm/lat-%r@%h:%p -o ControlPersist=30m" \
  "$REMOTO:/var/backups/keni-social/" "$DESTINO/historico-diario/" || log "AVISO: sin historico"

# --------------------------------------------------------------- 3. VERIFICAR
# El checksum se calculo en el servidor: cuadrar aqui prueba que la copia es identica.
log "=== 3/5 verificando checksums ==="
( cd "$LOCAL" && shasum -a 256 -c SHA256SUMS ) \
  && log "  todos los ficheros cuadran" \
  || { log "ERROR: checksums NO cuadran. NO apagues el servidor."; exit 1; }

# ------------------------------------------------- 4. PROBAR EL RESTORE DE VERDAD
# Un backup sin restore probado no es un backup. Levanta un Postgres limpio y restaura.
log "=== 4/5 probando el restore de Postgres ==="
if docker info >/dev/null 2>&1; then
  DUMP="$(ls "$LOCAL"/postgres/keni-*.dump | head -1)"
  docker rm -f pg-restore-test >/dev/null 2>&1 || true
  docker run --rm -d --name pg-restore-test -e POSTGRES_PASSWORD=t postgres:16.13 >/dev/null
  until docker exec pg-restore-test pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
  docker exec -i pg-restore-test pg_restore -U postgres -d postgres --no-owner < "$DUMP" 2>&1 | tail -5 || true
  TABLAS="$(docker exec pg-restore-test psql -U postgres -tAc \
    "select count(*) from pg_tables where schemaname='public'")"
  FILAS="$(docker exec pg-restore-test psql -U postgres -tAc \
    "select coalesce(sum(n_live_tup),0) from pg_stat_user_tables")"
  docker rm -f pg-restore-test >/dev/null
  log "  restauradas $TABLAS tablas, ~$FILAS filas"
  [ "$TABLAS" -gt 0 ] || { log "ERROR: el dump restaura 0 tablas. NO apagues el servidor."; exit 1; }
else
  log "  AVISO: Docker no corre. Arrancalo y repite este paso ANTES de apagar el servidor."
fi

# Los tars solo se verifican de integridad; descomprimirlos enteros aqui no aporta.
log "=== verificando los tars ==="
for t in "$LOCAL"/volumenes/*.tar.gz; do
  gzip -t "$t" && echo "  OK  $(basename "$t")  $(du -h "$t" | cut -f1)"
done

# ----------------------------------------------------------- 5. CIFRAR SECRETOS
# En claro hay tokens OAuth y credenciales de Postgres/S3. Nunca van a git sin cifrar.
log "=== 5/5 cifrando los secretos ==="
if [ -d "$LOCAL/secretos" ]; then
  tar czf - -C "$LOCAL" secretos | gpg --symmetric --cipher-algo AES256 \
    --output "$LOCAL/secretos.tar.gz.gpg"
  rm -rf "$LOCAL/secretos"
  chmod 600 "$LOCAL/secretos.tar.gz.gpg"
  log "  secretos -> secretos.tar.gz.gpg (el claro se borro). GUARDA LA PASSPHRASE."
fi

echo
log "LISTO -> $LOCAL"
du -sh "$LOCAL" "$DESTINO/historico-diario" 2>/dev/null
