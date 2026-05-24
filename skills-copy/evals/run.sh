#!/usr/bin/env bash
# run.sh — corredor LOCAL del eval de copy (usa el MODELO; NO es para CI).
#
# Ejecuta una skill de skills-copy en modo headless con `claude -p` contra una
# fixture de ejemplos/, captura la salida y le pasa las aserciones
# deterministicas (assert_output.py): limites de caracteres (contar.py), bloque
# de auto-verificacion, regla de la bandera con escudo y fidelidad de
# numeros/citas frente a la fuente.
#
# REQUISITOS (por eso es un gate LOCAL, no de CI):
#   - `claude` en el PATH y autenticado (consume modelo).
#   - Para casos de CLIP: whisper.cpp (whisper-cli) + ffmpeg + el modelo local,
#     porque clip-a-copy transcribe EN LOCAL (ver ../../docs/despliegue-local.md).
#   - python3 (para las aserciones).
#
# Uso:
#   bash run.sh                      # corre el caso por defecto (copy-desde-nota, cables)
#   bash run.sh nota                 # nota: cross-check de los dos cables
#   bash run.sh clip                 # clip: genera audio de prueba, transcribe y evalua
#   bash run.sh all                  # todos los casos sin modelo-pesado que se puedan
#   KENI_EVAL_KEEP=1 bash run.sh ... # conserva los outputs capturados en .out/
#
# Sale 0 si todas las aserciones pasan; !=0 si algo falla o falta una dependencia.

set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_COPY="$(cd "$AQUI/.." && pwd)"   # raiz de skills-copy (cwd de las skills)
EJEMPLOS="$SKILLS_COPY/ejemplos"
OUTDIR="$AQUI/.out"
mkdir -p "$OUTDIR"

CASO="${1:-nota}"

info() { printf '\033[1m== %s\033[0m\n' "$*" >&2; }
err()  { printf 'ERROR: %s\n' "$*" >&2; }

need() {
  command -v "$1" >/dev/null 2>&1 || { err "falta '$1' en el PATH. $2"; return 1; }
}

# Lanza una skill headless. El cwd debe ser la raiz de skills-copy para que
# Claude Code descubra .claude/skills y las rutas relativas del contexto.
ejecutar_skill() {
  local prompt="$1" out="$2"
  need claude "Instala/inicia sesion en Claude Code (este corredor consume modelo)." || return 1
  info "claude -p (cwd=$SKILLS_COPY)"
  ( cd "$SKILLS_COPY" && claude -p "$prompt" ) | tee "$out"
}

evaluar() {
  local out="$1"; shift
  local fuentes=()
  local ignora=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --ignorar-numero) ignora+=(--ignorar-numero "$2"); shift 2 ;;
      *) fuentes+=(--fuente "$1"); shift ;;
    esac
  done
  python3 "$AQUI/assert_output.py" --salida "$out" "${fuentes[@]}" "${ignora[@]}"
}

caso_nota() {
  info "CASO nota — copy-desde-nota con dos cables (cross-check 40/45 mde, 4/5 temporadas)"
  local out="$OUTDIR/nota.out.txt"
  ejecutar_skill \
    "Usa la skill copy-desde-nota con ejemplos/cable-1.md y ejemplos/cable-2.md, marca claro-sports. Son dos cables del mismo fichaje: sintetiza y haz cross-check de los datos. Dame una variante por plataforma y la auto-verificacion." \
    "$out"
  # 4 y 5 (temporadas) y 40/45 (mde) SI estan en las fuentes; el anio no aplica aqui.
  evaluar "$out" "$EJEMPLOS/cable-1.md" "$EJEMPLOS/cable-2.md"
}

caso_clip() {
  info "CASO clip — clip-a-copy (transcripcion LOCAL con whisper.cpp)"
  need ffmpeg "Instala ffmpeg (brew install ffmpeg)." || return 1
  need whisper-cli "Instala whisper.cpp (brew install whisper-cpp) y el modelo (ver docs/despliegue-local.md)." || return 1
  local media="${KENI_EVAL_CLIP:-/tmp/keni-clip/declaracion.m4a}"
  if [ ! -f "$media" ]; then
    info "generando clip de prueba en $media"
    ( cd "$EJEMPLOS" && bash generar-clip-prueba.sh "$media" )
  fi
  local out="$OUTDIR/clip.out.txt"
  ejecutar_skill \
    "Usa la skill clip-a-copy con $media para claro-sports. Transcribe en local, saca las citas con marca de tiempo y dame una variante por plataforma con la auto-verificacion." \
    "$out"
  # La fuente real es la transcripcion; como referencia de fidelidad usamos el
  # guion del clip de prueba (ejemplos/clip-entrevista.md cubre el caso de texto).
  # El audio sintetico hace que whisper marque cifras como dudosas (⚠️), por eso
  # ignoramos los numeros del guion en la fidelidad estricta.
  evaluar "$out" "$EJEMPLOS/clip-entrevista.md" --ignorar-numero 12 --ignorar-numero 88
}

case "$CASO" in
  nota) caso_nota ;;
  clip) caso_clip ;;
  all)
    rc=0
    caso_nota || rc=$?
    caso_clip || rc=$?
    [ "${KENI_EVAL_KEEP:-0}" = "1" ] || true
    exit "$rc"
    ;;
  *) err "caso desconocido: $CASO (usa: nota | clip | all)"; exit 2 ;;
esac

[ "${KENI_EVAL_KEEP:-0}" = "1" ] || true
