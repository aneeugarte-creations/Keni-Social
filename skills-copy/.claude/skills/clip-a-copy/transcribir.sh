#!/usr/bin/env bash
# transcribir.sh — transcripcion local (sin nube) de video/audio a texto con marcas de tiempo.
#
# Usa whisper.cpp (whisper-cli) con el modelo large-v3-turbo en espanol. Todo
# corre en la maquina: ni el video ni el audio salen de aqui. Pensado para los
# Mac del equipo (Apple Silicon). Produce:
#   <base>.txt  -> texto corrido (para leer/redactar)
#   <base>.srt  -> texto con marcas de tiempo (para sacar citas y puntos de corte)
#   <base>.json -> segmentos con offsets en ms (precision para clips)
#
# Uso:
#   bash transcribir.sh ENTRADA [--idioma es] [--salida DIR] [--modelo RUTA] \
#                       [--prompt "Claro Sports, UnoTV..."] [--keep-wav]
#
# La ultima linea de stdout es 'TRANSCRIPCION=<ruta .txt>' (parseable por la skill).

set -euo pipefail

err() { echo "ERROR: $*" >&2; exit 1; }

# --- argumentos ---
ENTRADA="${1:-}"
[ -n "$ENTRADA" ] || err "falta la ruta del video/audio. Uso: bash transcribir.sh ENTRADA [opciones]"
shift || true
[ -f "$ENTRADA" ] || err "no existe el archivo: $ENTRADA"

IDIOMA="es"
SALIDA=""
MODELO=""
PROMPT=""
KEEP_WAV=0
while [ $# -gt 0 ]; do
  case "$1" in
    --idioma) IDIOMA="${2:-es}"; shift 2 ;;
    --salida) SALIDA="${2:-}"; shift 2 ;;
    --modelo) MODELO="${2:-}"; shift 2 ;;
    --prompt) PROMPT="${2:-}"; shift 2 ;;
    --keep-wav) KEEP_WAV=1; shift ;;
    *) err "opcion desconocida: $1" ;;
  esac
done

# --- dependencias ---
command -v whisper-cli >/dev/null 2>&1 || err "whisper-cli no encontrado. Instala whisper.cpp: brew install whisper-cpp"
command -v ffmpeg >/dev/null 2>&1 || err "ffmpeg no encontrado. Instala: brew install ffmpeg"

# --- modelo (env > flag > rutas habituales) ---
if [ -z "$MODELO" ]; then MODELO="${KENI_WHISPER_MODEL:-}"; fi
if [ -z "$MODELO" ]; then
  for cand in "$HOME/models/ggml-large-v3-turbo.bin" "$HOME/.cache/whisper/ggml-large-v3-turbo.bin"; do
    [ -f "$cand" ] && MODELO="$cand" && break
  done
fi
[ -n "$MODELO" ] && [ -f "$MODELO" ] || err "modelo no encontrado. Define KENI_WHISPER_MODEL o pasa --modelo RUTA (p. ej. ggml-large-v3-turbo.bin)."

# --- salida ---
if [ -z "$SALIDA" ]; then SALIDA="$(dirname "$ENTRADA")/transcripciones"; fi
mkdir -p "$SALIDA"
nombre="$(basename "${ENTRADA%.*}")"
base="$SALIDA/$nombre"
wav="$base.16k.wav"

# --- duracion (informativa) ---
if command -v ffprobe >/dev/null 2>&1; then
  dur="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$ENTRADA" 2>/dev/null || echo "")"
  [ -n "$dur" ] && printf 'Duracion del audio: %.0f s (~%.0f min)\n' "$dur" "$(echo "$dur/60" | bc -l)" >&2
fi

# --- 1) extraer audio normalizado: 16 kHz mono PCM (lo que espera whisper.cpp) ---
echo "Extrayendo audio a 16 kHz mono..." >&2
ffmpeg -nostdin -loglevel error -y -i "$ENTRADA" -ar 16000 -ac 1 -c:a pcm_s16le "$wav"

# --- 2) transcribir en local ---
echo "Transcribiendo en local (whisper.cpp, $IDIOMA)... esto puede tardar en audios largos." >&2
args=(-m "$MODELO" -f "$wav" -l "$IDIOMA" -otxt -osrt -oj -of "$base" -np -pp)
[ -n "$PROMPT" ] && args+=(--prompt "$PROMPT")
whisper-cli "${args[@]}" >/dev/null

# --- 3) limpieza ---
[ "$KEEP_WAV" -eq 1 ] || rm -f "$wav"

echo "Listo. Salidas:" >&2
echo "  texto:     $base.txt" >&2
echo "  con tiempo: $base.srt" >&2
echo "  json:      $base.json" >&2
# ultima linea parseable por la skill:
echo "TRANSCRIPCION=$base.txt"
