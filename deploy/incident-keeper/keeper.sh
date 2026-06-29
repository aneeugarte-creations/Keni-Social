#!/bin/sh
# INCIDENT-KEEPER: agente claude -p que mantiene `main` SANO en la nube, automático. Clon del
# "green keeper" (que el humano lanzaba a mano con "arregla el ci NNNN"). Corre en la imagen del
# worker (trae claude+git+gh), usa la cuenta de Claude PROPIA del guardián ($CLAUDE_CONFIG_DIR =
# /claude-cfg, volumen aparte; la fija guardian-ui) y la credencial de GitHub (/data/gh), y
# promueve el fix a `main` con scripts/promover-main.sh.
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
CI_ABORT_INTERVALO="${KENI_KEEPER_CI_ABORT_INTERVALO:-20}"  # cada cuánto comprueba el watchdog de aborto
# Rastro de sesiones para la UI INDEPENDIENTE (guardian-ui): el keeper deja aquí, en el volumen
# compartido /data, el stream-json de cada sesión + su meta + un heartbeat de vigilancia. La UI
# (otro contenedor) sólo LEE esto; no depende del back/db.
KEEPER_DIR="$(dirname "$0")"             # /keeper (dir bind-montado con keeper.sh + helpers)
DATA="${KENI_KEEPER_DATA:-${KENI_DATA_DIR:-/data}/keeper}"
ESTADO_VIGILANCIA="$DATA/estado.json"
RETENCION="${KENI_KEEPER_RETENCION:-50}" # sesiones a conservar
LATIDO=/tmp/keni-incident-keeper.latido
LOCK=/tmp/keni-incident-keeper.lock
CI_ULTIMO=/tmp/keni-keeper.ci-ultimo      # nº del último pipeline rojo ya intentado
CI_INTENTOS=/tmp/keni-keeper.ci-intentos  # marcas de tiempo de intentos recientes

log() { echo "incident-keeper: $*"; }

# Lanza UNA sesión claude -p en un worktree limpio desde origin/main. $1 = texto del incidente.
correr_keeper() {  # $1 = texto ; $2 = trigger (etiqueta UI) ; $3 = nº pipeline CI (vacío=incidente prod)
  texto="$1"; trigger="${2:-incidente}"; ci_num="${3:-}"
  : > "$LOCK"
  mkdir -p "$DATA" 2>/dev/null || true
  sid="$(date +%s)"
  jsonl="$DATA/$sid.jsonl"
  meta="$DATA/$sid.meta.json"
  titulo="$(printf '%s' "$texto" | head -1 | cut -c1-160)"
  # Meta inicial (estado=corriendo) para que la UI vea la sesión en cuanto arranca.
  python3 "$KEEPER_DIR/sesion.py" "$meta" - id="$sid" trigger="$trigger" titulo="$titulo" \
    inicio="$(date -u +%Y-%m-%dT%H:%M:%SZ)" estado=corriendo 2>/dev/null || true

  git -C "$REPO" fetch origin -q 2>/dev/null || log "aviso: git fetch falló"
  base="$(git -C "$REPO" rev-parse origin/main 2>/dev/null)"
  rama="keeper-$sid"
  wt="$REPO/.wt-incident-keeper"
  git -C "$REPO" worktree remove --force "$wt" >/dev/null 2>&1 || true
  rm -rf "$wt" 2>/dev/null || true

  estado=error; commit_sha=""; commit_msg=""
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
    abort_flag="$DATA/$sid.abort"; rm -f "$abort_flag"
    # claude con `exec`: el subshell se REEMPLAZA por claude, así $cl_pid ES el proceso claude y el
    # watchdog puede abortarlo. La salida va al jsonl (la UI lo lee del fichero, no de stdout).
    ( cd "$wt" && exec claude -p "$prompt" \
        --output-format stream-json --verbose --include-partial-messages \
        --dangerously-skip-permissions --model "$MODELO" ) > "$jsonl" 2>&1 &
    cl_pid=$!
    # Watchdog de ABORTO (solo en fix de CI): si mientras arreglamos aparece un pipeline MÁS NUEVO en
    # verde, el rojo ya lo resolvió otro commit -> matamos el claude para no arreglar lo ya arreglado.
    wd_pid=""
    if [ -n "$ci_num" ]; then
      ( while kill -0 "$cl_pid" 2>/dev/null; do
          sleep "$CI_ABORT_INTERVALO"
          if python3 "$CI_WATCH" --verde-despues "$ci_num" >/dev/null 2>&1; then
            log "CI #$ci_num: pipeline VERDE más nuevo -> aborto el fix (ya resuelto por otro commit)"
            : > "$abort_flag"
            kill -TERM "$cl_pid" 2>/dev/null; sleep 5; kill -KILL "$cl_pid" 2>/dev/null
            break
          fi
        done ) &
      wd_pid=$!
    fi
    wait "$cl_pid" 2>/dev/null
    [ -n "$wd_pid" ] && kill "$wd_pid" 2>/dev/null

    # ¿Commiteó/pusheó? El HEAD del worktree distinto de la base = fix promovido (gana al aborto: si
    # llegó a commitear, el fix es real). Si no commiteó pero el watchdog abortó -> `abortado`.
    head="$(git -C "$wt" rev-parse HEAD 2>/dev/null)"
    if [ -n "$head" ] && [ "$head" != "$base" ]; then
      commit_sha="$head"; commit_msg="$(git -C "$wt" log -1 --format=%s 2>/dev/null)"; estado=resuelto
    elif [ -f "$abort_flag" ]; then
      estado=abortado   # un pipeline más nuevo salió verde mientras arreglaba: el rojo ya no existía
    else
      estado=escalado   # terminó sin commitear: o escaló, o no había nada que arreglar
    fi
    rm -f "$abort_flag"
    git -C "$REPO" worktree remove --force "$wt" >/dev/null 2>&1 || true
    git -C "$REPO" branch -D "$rama" >/dev/null 2>&1 || true
    log "fin de la sesión ($estado); worktree limpio"
  else
    log "no pude crear worktree desde origin/main; ESCALO: revisa $REPO a mano"
  fi

  # Meta final: estado + commit + coste/tokens (sesion.py parsea el `result` del jsonl). Si el
  # jsonl trae is_error, sesion.py lo marca y la UI lo pinta.
  nota=""
  [ "$estado" = abortado ] && nota="Abortado: un pipeline más nuevo salió verde; el rojo ya estaba resuelto."
  python3 "$KEEPER_DIR/sesion.py" "$meta" "$jsonl" estado="$estado" \
    fin="$(date -u +%Y-%m-%dT%H:%M:%SZ)" commit_sha="$commit_sha" commit_msg="$commit_msg" \
    ${nota:+"nota=$nota"} 2>/dev/null || true
  # Retención: conserva los $RETENCION más recientes (jsonl + meta).
  ls -1t "$DATA"/*.meta.json 2>/dev/null | tail -n +"$((RETENCION + 1))" | while read -r m; do
    rm -f "$m" "${m%.meta.json}.jsonl" 2>/dev/null || true
  done
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

mkdir -p "$DATA" 2>/dev/null || true

while :; do
  : > "$LATIDO" 2>/dev/null || true   # latido para el healthcheck
  # Heartbeat de vigilancia para guardian-ui: estado de la vigilancia + último pipeline visto.
  python3 "$CI_WATCH" --heartbeat "$ESTADO_VIGILANCIA" "$CI" 2>/dev/null || true

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

$ci" "CI #$num" "$num"
      fi
    fi
  fi

  # --- Disparo 2: INCIDENTE de prod (lo escribe el guardian) ------------------------------
  if [ -f "$TRIGGER" ] && [ ! -f "$LOCK" ]; then
    inc="$(cat "$TRIGGER" 2>/dev/null)"
    log "incidente de prod recibido; lanzo diagnóstico+fix"
    correr_keeper "$inc" "incidente prod"
    # Archiva el trigger procesado (no re-disparar el mismo en bucle; si persiste, el guardian
    # escribirá uno nuevo). El antiflapping del guardian limita la cadencia.
    mv "$TRIGGER" "$ESTADO/incidente-$(date +%s).done" 2>/dev/null || rm -f "$TRIGGER"
  fi

  sleep "$INTERVALO"
done
