#!/bin/zsh
# Wrapper de cron/launchd para el reporte de métricas (+ picos).
#
# RED DE SEGURIDAD:
# - LOCK (mkdir atómico) para no solaparse con otra ejecución.
# - Logging con timestamps.
# - SOLO LECTURA: keni-reporte agrega métricas y alertas; NUNCA publica ni hace
#   nada destructivo. No reintenta solo (evita bucles).
# - PATH fijado (cron/launchd arrancan con entorno mínimo).

set -u
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

BIN="${KENI_REPORTE_BIN:-keni-reporte}"
DIR_SALIDA="${KENI_REPORTE_DIR:-$HOME/keni-reportes}"
RANGO="${KENI_REPORTE_RANGO:-semana}"
LOCK="${TMPDIR:-/tmp}/keni-reporte.lock"

mkdir -p "$DIR_SALIDA"
LOG="$DIR_SALIDA/cron.log"

# lock: mkdir es atómico; si ya existe, hay otra ejecución en curso.
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date '+%F %T') :: ya hay una ejecución en curso, salgo." >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

FECHA="$(date '+%Y-%m-%d')"
SALIDA="$DIR_SALIDA/reporte-$RANGO-$FECHA.md"

echo "$(date '+%F %T') :: generando $SALIDA (rango=$RANGO)" >> "$LOG"
if "$BIN" --rango "$RANGO" --picos --salida "$SALIDA" >> "$LOG" 2>&1; then
  echo "$(date '+%F %T') :: OK" >> "$LOG"
else
  echo "$(date '+%F %T') :: FALLO (exit $?) — no se reintenta automáticamente" >> "$LOG"
fi
