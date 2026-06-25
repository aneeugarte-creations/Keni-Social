#!/bin/sh
# INCIDENT-KEEPER: agente claude -p que, ante un incidente de produccion que el autoheal NO
# pudo resolver (un contenedor que no arranca o flapea), lee la evidencia, diagnostica y —si la
# causa es de CODIGO— commitea el fix a `main` (que dispara test->deploy). Clon del "green keeper"
# pero para incidentes de prod, en la nube y automatico. Corre en la imagen del worker (trae
# claude+git+gh), hereda la cuenta de Claude (/data/claude-cfg) y la credencial de GitHub (/data/gh).
#
# DISPARO: el `guardian` escribe $TRIGGER (estado/incidente.json) con la evidencia ya recogida
# (servicio, exit code, logs recientes). Este bucle lo detecta, lanza UN claude -p con el ROL y la
# evidencia, y archiva el trigger. Un solo keeper a la vez (lock). El keeper NO toca docker: la
# mitigacion (resucitar contenedores) es del guardian; este se centra en el fix de codigo.
set -u

ESTADO="${KENI_KEEPER_ESTADO:-/estado}"
TRIGGER="$ESTADO/incidente.json"
FLAG_DEPLOY="${KENI_GUARDIAN_FLAG_DEPLOY:-$ESTADO/desplegando}"
REPO="${KENI_DEV_REPO:-/repo}"
ROL="${KENI_KEEPER_ROL:-/keeper/ROL.md}"
INTERVALO="${KENI_KEEPER_INTERVALO:-10}"
MODELO="${KENI_KEEPER_MODELO:-opus}"
LATIDO=/tmp/keni-incident-keeper.latido
LOCK=/tmp/keni-incident-keeper.lock

log() { echo "incident-keeper: $*"; }

# Credencial de git via la cuenta gh de /data/gh (idempotente, best-effort; igual que worker_dev).
gh auth setup-git >/dev/null 2>&1 || log "aviso: gh auth setup-git falló (¿gh sin login en /data/gh?); el push podría fallar"

log "arranca (repo=$REPO modelo=$MODELO intervalo=${INTERVALO}s)"

while :; do
  : > "$LATIDO" 2>/dev/null || true   # latido para el healthcheck

  # Nada que hacer: sin trigger, durante un deploy, o con un keeper ya en marcha.
  if [ ! -f "$TRIGGER" ] || [ -f "$FLAG_DEPLOY" ] || [ -f "$LOCK" ]; then
    sleep "$INTERVALO"; continue
  fi

  : > "$LOCK"
  inc="$(cat "$TRIGGER" 2>/dev/null)"
  log "incidente recibido; lanzo diagnóstico+fix"

  git -C "$REPO" fetch origin -q 2>/dev/null || log "aviso: git fetch falló"
  rama="keeper-$(date +%s)"
  wt="$REPO/.wt-incident-keeper"
  git -C "$REPO" worktree remove --force "$wt" >/dev/null 2>&1 || true
  rm -rf "$wt" 2>/dev/null || true

  if git -C "$REPO" worktree add -b "$rama" "$wt" origin/main >/dev/null 2>&1; then
    prompt="$(cat "$ROL" 2>/dev/null)

## Incidente actual (resuélvelo según tu rol)
$inc

Estás en un worktree limpio desde origin/main ($wt, rama $rama). Diagnostica, decide
operativo vs. de código y actúa. Si es de código, promueve el fix con
\`bash $REPO/scripts/promover-main.sh\` desde este worktree y vigila que el pipeline
vuelva a verde. Si debes ESCALAR (fuera de tus límites o causa no clara), NO actúes:
deja aquí un diagnóstico claro y el plan para un humano."

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

  # Archiva el trigger procesado para no re-disparar el mismo incidente en bucle. Si la avería
  # persiste, el guardian escribirá un trigger NUEVO (su antiflapping limita la cadencia).
  mv "$TRIGGER" "$ESTADO/incidente-$(date +%s).done" 2>/dev/null || rm -f "$TRIGGER"
  rm -f "$LOCK"
  sleep "$INTERVALO"
done
