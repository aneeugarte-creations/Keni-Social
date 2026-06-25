#!/bin/sh
# INCIDENT-KEEPER: agente claude -p que mantiene `main` SANO en la nube, automático. Clon del
# "green keeper" (que el humano lanzaba a mano con "arregla el ci NNNN"). Corre en la imagen del
# worker (trae claude+git+gh), hereda la cuenta de Claude (/data/claude-cfg) y la credencial de
# GitHub (/data/gh), y promueve el fix a `main` con scripts/promover-main.sh.
#
# DOS DISPAROS, mismo motor (un claude -p por incidente, un solo keeper a la vez por el lock):
#   1) CI ROJO (el principal, réplica de ci-verde): vigila el datastore de Woodpecker; si el
#      ÚLTIMO pipeline de `main` está en rojo, lo arregla. Activar con KENI_KEEPER_CI=1.
#   2) INCIDENTE de prod: el `guardian` escribe $TRIGGER con la evidencia (servicio caído + logs)
#      cuando el autoheal no basta. Activar con KENI_GUARDIAN_ESCALAR=1 (en el guardian).
#
# Sólo actúa con `main` estable: NO durante un deploy (flag) y respetando los límites del ROL.
set -u

ESTADO="${KENI_KEEPER_ESTADO:-/estado}"
TRIGGER="$ESTADO/incidente.json"
FLAG_DEPLOY="${KENI_GUARDIAN_FLAG_DEPLOY:-$ESTADO/desplegando}"
REPO="${KENI_DEV_REPO:-/repo}"
ROL="${KENI_KEEPER_ROL:-/keeper/ROL.md}"
INTERVALO="${KENI_KEEPER_INTERVALO:-10}"
MODELO="${KENI_KEEPER_MODELO:-opus}"
# Vigilancia de CI: 1 = activa (réplica de ci-verde). ci_watch.py lee el sqlite de Woodpecker.
CI="${KENI_KEEPER_CI:-0}"
CI_WATCH="${KENI_KEEPER_CI_WATCH:-/keeper/ci_watch.py}"
CI_MAX="${KENI_KEEPER_CI_MAX:-3}"        # tope de sesiones de fix de CI por ventana
CI_VENTANA_MIN="${KENI_KEEPER_CI_VENTANA_MIN:-30}"
LATIDO=/tmp/keni-incident-keeper.latido
LOCK=/tmp/keni-incident-keeper.lock
CI_ULTIMO=/tmp/keni-keeper.ci-ultimo      # nº del último pipeline rojo ya intentado
CI_INTENTOS=/tmp/keni-keeper.ci-intentos  # marcas de tiempo de intentos recientes

log() { echo "incident-keeper: $*"; }

# Lanza UNA sesión claude -p en un worktree limpio desde origin/main. $1 = texto del incidente.
correr_keeper() {
  texto="$1"
  : > "$LOCK"
  git -C "$REPO" fetch origin -q 2>/dev/null || log "aviso: git fetch falló"
  rama="keeper-$(date +%s)"
  wt="$REPO/.wt-incident-keeper"
  git -C "$REPO" worktree remove --force "$wt" >/dev/null 2>&1 || true
  rm -rf "$wt" 2>/dev/null || true

  if git -C "$REPO" worktree add -b "$rama" "$wt" origin/main >/dev/null 2>&1; then
    prompt="$(cat "$ROL" 2>/dev/null)

## Incidente actual (resuélvelo según tu rol)
$texto

Estás en un worktree limpio desde origin/main ($wt, rama $rama). Diagnostica, decide el tipo
de incidente y actúa. Si es de código, promueve el fix con
\`bash $REPO/scripts/promover-main.sh\` desde este worktree y vigila que el pipeline vuelva a
verde. Si debes ESCALAR (fuera de tus límites o causa no clara), NO actúes: deja aquí un
diagnóstico claro y el plan para un humano."

    log "claude -p en $wt (rama $rama)"
    ( cd "$wt" && claude -p "$prompt" \
        --output-format stream-json --verbose --include-partial-messages \
        --dangerously-skip-permissions --model "$MODELO" ) 2>&1 || log "claude -p terminó con error"

    git -C "$REPO" worktree remove --force "$wt" >/dev/null 2>&1 || true
    git -C "$REPO" branch -D "$rama" >/dev/null 2>&1 || true
    log "fin de la sesión; worktree limpio"
  else
    log "no pude crear worktree desde origin/main; ESCALO: revisa $REPO a mano"
  fi
  rm -f "$LOCK"
}

# Intentos de fix de CI en la ventana reciente (poda los viejos de paso).
ci_intentos_recientes() {
  ahora="$(date +%s)"; corte=$((ahora - CI_VENTANA_MIN * 60))
  if [ -f "$CI_INTENTOS" ]; then
    awk -v c="$corte" '$1 >= c' "$CI_INTENTOS" > "$CI_INTENTOS.tmp" 2>/dev/null && mv "$CI_INTENTOS.tmp" "$CI_INTENTOS"
    wc -l < "$CI_INTENTOS" | tr -d ' '
  else
    echo 0
  fi
}

# Credencial de git via la cuenta gh de /data/gh (idempotente, best-effort; igual que worker_dev).
gh auth setup-git >/dev/null 2>&1 || log "aviso: gh auth setup-git falló (¿gh sin login en /data/gh?); el push podría fallar"

log "arranca (repo=$REPO modelo=$MODELO intervalo=${INTERVALO}s CI=$CI)"

while :; do
  : > "$LATIDO" 2>/dev/null || true   # latido para el healthcheck

  # No tocar `main` durante un deploy ni con un keeper ya en marcha.
  if [ -f "$FLAG_DEPLOY" ] || [ -f "$LOCK" ]; then
    sleep "$INTERVALO"; continue
  fi

  # --- Disparo 1: CI ROJO (réplica de ci-verde) -------------------------------------------
  if [ "$CI" = 1 ]; then
    ci="$(python3 "$CI_WATCH" 2>/dev/null)"
    num="$(printf '%s\n' "$ci" | sed -n 's/^PIPELINE_ROJO=//p' | head -1)"
    if [ -n "$num" ] && [ "$num" != "$(cat "$CI_ULTIMO" 2>/dev/null)" ]; then
      n="$(ci_intentos_recientes)"
      if [ "$n" -ge "$CI_MAX" ]; then
        log "CI sigue rojo tras $n intentos en ${CI_VENTANA_MIN}min: pauso el auto-fix; requiere humano"
      else
        echo "$num" > "$CI_ULTIMO"; echo "$(date +%s)" >> "$CI_INTENTOS"
        log "CI ROJO pipeline #$num: lanzo fix"
        correr_keeper "El pipeline #$num de \`main\` está ROJO en el CI (Woodpecker). Es un fix de
CÓDIGO: arréglalo según la sección de CI de tu rol y promueve a main. Evidencia:

$ci"
      fi
    fi
  fi

  # --- Disparo 2: INCIDENTE de prod (lo escribe el guardian) ------------------------------
  if [ -f "$TRIGGER" ] && [ ! -f "$LOCK" ]; then
    inc="$(cat "$TRIGGER" 2>/dev/null)"
    log "incidente de prod recibido; lanzo diagnóstico+fix"
    correr_keeper "$inc"
    # Archiva el trigger procesado (no re-disparar el mismo en bucle; si persiste, el guardian
    # escribirá uno nuevo). El antiflapping del guardian limita la cadencia.
    mv "$TRIGGER" "$ESTADO/incidente-$(date +%s).done" 2>/dev/null || rm -f "$TRIGGER"
  fi

  sleep "$INTERVALO"
done
