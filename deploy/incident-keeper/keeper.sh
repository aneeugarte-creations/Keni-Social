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
TIMEOUT="${KENI_KEEPER_TIMEOUT:-1800}"   # máx duración de una sesión claude -p (corta cuelgues)
VERIF_MAX="${KENI_KEEPER_VERIF_MAX:-2400}"  # máx espera de un `verificando` antes de darlo por perdido
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

# Estado global para la PARADA CON GRACIA (trap de SIGTERM): un deploy recrea este contenedor y, si
# hay una sesión en curso, sin esto el claude moriría a medias y la meta quedaría huérfana en
# `corriendo`. El trap cierra la sesión limpia dentro del stop_grace_period (30s).
PARAR=""; cl_pid=""; abort_flag=""

# Identidad git de los commits del keeper. El clon `/repo` trae un `user.name` LOCAL (p. ej. "Keni",
# compartido con los demás carriles) que PISA al global que fija el entrypoint; sin esto los commits
# del keeper se firmarían con ESA identidad y la detección por autor (`git log --author`) no los
# reconocería -> los marcaba «escalado» aunque sí hubiese arreglado y pusheado. `GIT_AUTHOR_*` /
# `GIT_COMMITTER_*` tienen PRECEDENCIA sobre cualquier config (local incluido) y se heredan al
# `claude -p`, así que sus commits SIEMPRE llevan esta identidad — la misma que busca la detección.
export GIT_AUTHOR_NAME="${KENI_GIT_AUTHOR_NAME:-keni incident-keeper}"
export GIT_AUTHOR_EMAIL="${KENI_GIT_AUTHOR_EMAIL:-incident-keeper@kenitech.io}"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

log() { echo "incident-keeper: $*"; }

# SIGTERM/SIGINT (parada o deploy): mata el claude en curso marcando la razón `shutdown` (la sesión
# se cerrará como `interrumpido`, no huérfana) y pide salir del bucle. EXIT: suelta el lock siempre.
parar() {
  PARAR=1
  if [ -n "$cl_pid" ] && kill -0 "$cl_pid" 2>/dev/null; then
    log "SIGTERM (parada/deploy): cierro con gracia la sesión en curso"
    [ -n "$abort_flag" ] && printf shutdown > "$abort_flag" 2>/dev/null
    kill -TERM "$cl_pid" 2>/dev/null; sleep 2; kill -KILL "$cl_pid" 2>/dev/null
  fi
}
trap parar TERM INT
trap 'rm -f "$LOCK" 2>/dev/null' EXIT

# Lanza UNA sesión claude -p en un worktree limpio desde origin/main.
correr_keeper() {  # $1=texto ; $2=trigger ; $3=nº pipeline CI ; $4=huella de fallos ; $5=session a RESUMIR
  texto="$1"; trigger="${2:-incidente}"; ci_num="${3:-}"; huella="${4:-}"; resume_id="${5:-}"
  : > "$LOCK"
  mkdir -p "$DATA" 2>/dev/null || true
  sid="$(date +%s)"
  jsonl="$DATA/$sid.jsonl"
  meta="$DATA/$sid.meta.json"
  titulo="$(printf '%s' "$texto" | head -1 | cut -c1-160)"
  # Meta inicial (estado=corriendo) para que la UI vea la sesión en cuanto arranca. `huella` permite
  # saber luego si un rojo nuevo es 'lo mismo' que esta sesión ya está arreglando.
  python3 "$KEEPER_DIR/sesion.py" "$meta" - id="$sid" trigger="$trigger" titulo="$titulo" \
    inicio="$(date -u +%Y-%m-%dT%H:%M:%SZ)" estado=corriendo huella="$huella" 2>/dev/null || true

  git -C "$REPO" fetch origin -q 2>/dev/null || log "aviso: git fetch falló"
  base="$(git -C "$REPO" rev-parse origin/main 2>/dev/null)"
  rama="keeper-$sid"
  wt="$REPO/.wt-incident-keeper"
  git -C "$REPO" worktree remove --force "$wt" >/dev/null 2>&1 || true
  rm -rf "$wt" 2>/dev/null || true

  estado=error; commit_sha=""; commit_msg=""; razon=""
  if git -C "$REPO" worktree add -b "$rama" "$wt" origin/main >/dev/null 2>&1; then
    prompt="$(cat "$ROL" 2>/dev/null)

## Incidente actual (resuélvelo según tu rol)
$texto

Estás en un worktree limpio desde origin/main ($wt, rama $rama). Diagnostica, decide el tipo
de incidente y actúa. Si es de código, promueve el fix con
\`bash $REPO/scripts/promover-main.sh\` desde este worktree y vigila que el pipeline vuelva a
verde. Si debes ESCALAR (fuera de tus límites o causa no clara), NO actúes: deja aquí un
diagnóstico claro y el plan para un humano."

    [ -n "$resume_id" ] && log "RESUMO la sesión $resume_id (mismos fallos persisten)"
    log "claude -p en $wt (rama $rama)"
    abort_flag="$DATA/$sid.abort"; rm -f "$abort_flag"
    # claude con `exec`: el subshell se REEMPLAZA por claude, así $cl_pid ES el proceso claude y el
    # watchdog puede abortarlo. La salida va al jsonl (la UI lo lee del fichero, no de stdout). Si hay
    # `resume_id`, CONTINÚA esa conversación (el agente ya sabe qué intentó) en vez de empezar de cero.
    ( cd "$wt" && exec claude -p "$prompt" \
        --output-format stream-json --verbose --include-partial-messages \
        --dangerously-skip-permissions --model "$MODELO" ${resume_id:+--resume "$resume_id"} ) > "$jsonl" 2>&1 &
    cl_pid=$!
    # Watchdog: corre SIEMPRE en paralelo y mata el claude por dos motivos (escribe la razón en el
    # flag): (1) TIMEOUT — supera $TIMEOUT s (un cuelgue no debe quedarse eterno reteniendo el lock);
    # (2) VERDE — solo en fix de CI: apareció un pipeline más nuevo en verde, el rojo ya lo resolvió
    # otro commit (no arreglar lo ya arreglado).
    deadline=$(( $(date +%s) + TIMEOUT ))
    ( while kill -0 "$cl_pid" 2>/dev/null; do
        sleep "$CI_ABORT_INTERVALO"
        if [ "$(date +%s)" -ge "$deadline" ]; then
          log "sesión supera ${TIMEOUT}s sin terminar -> la corto (posible cuelgue)"
          printf timeout > "$abort_flag"
          kill -TERM "$cl_pid" 2>/dev/null; sleep 5; kill -KILL "$cl_pid" 2>/dev/null; break
        fi
        if [ -n "$ci_num" ] && python3 "$CI_WATCH" --verde-despues "$ci_num" >/dev/null 2>&1; then
          log "CI #$ci_num: pipeline VERDE más nuevo -> aborto el fix (ya resuelto por otro commit)"
          printf verde > "$abort_flag"
          kill -TERM "$cl_pid" 2>/dev/null; sleep 5; kill -KILL "$cl_pid" 2>/dev/null; break
        fi
      done ) &
    wd_pid=$!
    wait "$cl_pid" 2>/dev/null
    kill "$wd_pid" 2>/dev/null

    # PRIMERO: ¿el keeper PUSHEÓ un fix? = un commit SUYO (autor del keeper) en `origin/main` durante
    # la sesión (base..origin/main). NO vale «HEAD del worktree != base»: el agente puede
    # `git fetch && git rebase origin/main` y mover su HEAD a commits de OTROS sin arreglar nada.
    git -C "$REPO" fetch origin -q 2>/dev/null || true
    razon="$(cat "$abort_flag" 2>/dev/null)"
    autor="${KENI_GIT_AUTHOR_NAME:-keni incident-keeper}"
    mio="$(git -C "$REPO" log --author="$autor" --format=%H "$base..origin/main" 2>/dev/null | head -1)"
    if [ -n "$mio" ]; then
      # Pusheó un fix, PERO push != resuelto: el veredicto lo da la ETAPA VERDE de ESE commit. Si su
      # pipeline aún corre, queda `verificando` y el bucle lo resuelve cuando termine (verde=resuelto,
      # rojo=fallido; si lo dejó verde OTRO commit, abortado).
      commit_sha="$mio"; commit_msg="$(git -C "$REPO" log -1 --format=%s "$mio" 2>/dev/null)"
      estado="$(python3 "$CI_WATCH" --verdicto-fix "$mio" 2>/dev/null)"
      case "$estado" in resuelto|fallido|abortado|verificando) ;; *) estado=verificando ;; esac
    elif [ "$razon" = verde ]; then
      estado=abortado      # un pipeline más nuevo salió verde mientras arreglaba: el rojo ya no existía
    elif [ "$razon" = timeout ] || [ "$razon" = shutdown ]; then
      estado=interrumpido  # se cortó por tiempo (cuelgue) o por parada del keeper (deploy)
    else
      estado=escalado      # terminó sin pushear un fix propio: escaló o no había nada que arreglar
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
  case "$estado" in
    abortado) nota="Abortado: otro commit dejó main verde; el fix del keeper quedó superado." ;;
    verificando) nota="Fix pusheado; esperando a que su pipeline termine para confirmar el verde." ;;
    fallido) nota="El pipeline del fix salió ROJO: el arreglo no bastó." ;;
    interrumpido)
      case "$razon" in
        timeout) nota="Interrumpido: la sesión superó el límite de tiempo (${TIMEOUT}s) y se cortó." ;;
        *)       nota="Interrumpido: el keeper se detuvo (p. ej. un deploy) durante la sesión." ;;
      esac ;;
  esac
  # session_id de claude (del evento init): para poder RESUMIR esta conversación si el mismo fallo
  # persiste (fix-aware), en vez de empezar de cero.
  claude_session="$(grep -o '"session_id":"[^"]*"' "$jsonl" 2>/dev/null | head -1 | cut -d'"' -f4)"
  python3 "$KEEPER_DIR/sesion.py" "$meta" "$jsonl" estado="$estado" \
    fin="$(date -u +%Y-%m-%dT%H:%M:%SZ)" commit_sha="$commit_sha" commit_msg="$commit_msg" \
    huella="$huella" claude_session="$claude_session" ${nota:+"nota=$nota"} 2>/dev/null || true
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

# Lee un campo de una meta (cadena vacía si no existe). $1=fichero meta, $2=clave.
meta_get() {
  python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2" 2>/dev/null
}

# Busca la sesión MÁS RECIENTE con huella=$1 y estado=$2. Devuelve 0 e imprime su claude_session
# (puede ser vacío) si existe; 1 si no hay ninguna. Las metas van por epoch: nombre mayor = más nuevo.
buscar_huella() {
  [ -n "$1" ] || return 1
  for meta in $(ls -1 "$DATA"/*.meta.json 2>/dev/null | sort -r); do
    [ "$(meta_get "$meta" huella)" = "$1" ] || continue
    [ "$(meta_get "$meta" estado)" = "$2" ] || continue
    meta_get "$meta" claude_session
    return 0
  done
  return 1
}

# Busca una sesión RESUMIBLE para el rojo actual: la más reciente que quedó `interrumpido` (deploy
# que cortó el contenedor) o `fallido` (su fix no bastó) PARA EL MISMO incidente, con un
# claude_session capturado. Empareja por huella ($1, si la hay) o por trigger ($2, p. ej. "CI #65",
# estable al anclar en el ORIGEN de la racha). Así, tras reiniciarse a media sesión, el keeper
# CONTINÚA la conversación (el agente ya sabe qué diagnosticó/intentó) en vez de empezar de cero.
# Imprime su claude_session y devuelve 0; 1 si no hay ninguna resumible.
buscar_resumible() {  # $1=huella  $2=trigger
  for meta in $(ls -1 "$DATA"/*.meta.json 2>/dev/null | sort -r); do
    case "$(meta_get "$meta" estado)" in interrumpido|fallido) ;; *) continue ;; esac
    h="$(meta_get "$meta" huella)"; t="$(meta_get "$meta" trigger)"
    if { [ -n "$1" ] && [ "$h" = "$1" ]; } || [ "$t" = "$2" ]; then
      cs="$(meta_get "$meta" claude_session)"
      [ -n "$cs" ] || continue   # sin session_id no se puede resumir; sigue buscando una que sí lo tenga
      printf '%s' "$cs"; return 0
    fi
  done
  return 1
}

# ¿El rojo $1 (trigger "CI #N") quedó PENDIENTE de re-trabajo? = su sesión MÁS RECIENTE acabó
# `interrumpido` (un deploy la cortó) o `fallido` (su fix no bastó). Devuelve 0 si sí. Es lo que
# permite RE-DISPARAR el MISMO nº de pipeline tras una interrupción: sin esto, `CI_ULTIMO` (antiflap)
# bloqueaba para siempre el rojo ya intentado y el keeper se quedaba mudo aunque main siguiera rojo.
# Mira solo la sesión más reciente del trigger: si la última fue corriendo/verificando/resuelto/
# abortado, NO re-disparamos (hay algo en marcha o ya resuelto).
pendiente_para() {  # $1 = trigger, p. ej. "CI #78"
  for meta in $(ls -1 "$DATA"/*.meta.json 2>/dev/null | sort -r); do
    [ "$(meta_get "$meta" trigger)" = "$1" ] || continue
    case "$(meta_get "$meta" estado)" in interrumpido|fallido) return 0 ;; *) return 1 ;; esac
  done
  return 1
}

# Reconcilia sesiones HUÉRFANAS: una meta en `corriendo` al ARRANCAR significa que un keeper previo
# se cayó/reinició (p. ej. un deploy recrea el contenedor) y mató el claude sin cerrar la sesión.
# La marcamos `interrumpido` (para que la UI no la muestre eternamente "corriendo") CAPTURANDO su
# claude_session del jsonl: así el bucle puede RESUMIRLA cuando vuelva a detectar el mismo rojo.
reconciliar_huerfanas() {
  for meta in "$DATA"/*.meta.json; do
    [ -f "$meta" ] || continue
    if [ "$(meta_get "$meta" estado)" = corriendo ]; then
      sidn="$(basename "$meta" .meta.json)"
      cs="$(grep -o '"session_id":"[^"]*"' "$DATA/$sidn.jsonl" 2>/dev/null | head -1 | cut -d'"' -f4)"
      log "sesión huérfana $sidn: marco interrumpida${cs:+ (resumible: $cs)}"
      python3 "$KEEPER_DIR/sesion.py" "$meta" - estado=interrumpido \
        fin="$(date -u +%Y-%m-%dT%H:%M:%SZ)" claude_session="$cs" \
        nota="Interrumpido: el keeper se reinició (p. ej. un deploy) mientras la sesión corría." 2>/dev/null || true
    fi
  done
}

# Resuelve sesiones en `verificando`: el keeper pusheó un fix y esperamos el VEREDICTO de su pipeline.
# Cada ciclo re-consulta el commit; cuando su etapa termina, cierra la sesión (verde=resuelto,
# rojo=fallido; si lo dejó verde OTRO commit, abortado). Mientras corre, sigue en `verificando`.
verificar_pendientes() {
  for meta in "$DATA"/*.meta.json; do
    [ -f "$meta" ] || continue
    [ "$(meta_get "$meta" estado)" = verificando ] || continue
    sha="$(meta_get "$meta" commit_sha)"; [ -n "$sha" ] || continue
    v="$(python3 "$CI_WATCH" --verdicto-fix "$sha" 2>/dev/null)"
    case "$v" in
      resuelto) nota="El pipeline del fix salió VERDE." ;;
      fallido)  nota="El pipeline del fix salió ROJO: el arreglo no bastó." ;;
      abortado) nota="Otro commit dejó main verde; el fix del keeper quedó superado." ;;
      *)
        # Sigue corriendo: lo dejamos en verificando, SALVO que lleve demasiado (pipeline perdido/
        # colgado): no debe bloquear para siempre el reintento del mismo fallo.
        sidn="$(basename "$meta" .meta.json)"
        case "$sidn" in *[!0-9]*) continue ;; esac
        if [ "$(( $(date +%s) - sidn ))" -gt "$VERIF_MAX" ]; then
          v=escalado; nota="No se pudo confirmar el verde del fix (pipeline perdido tras ${VERIF_MAX}s); revísalo."
        else
          continue
        fi ;;
    esac
    log "sesión $(basename "$meta" .meta.json): $v (veredicto del pipeline del fix)"
    python3 "$KEEPER_DIR/sesion.py" "$meta" - estado="$v" \
      fin="$(date -u +%Y-%m-%dT%H:%M:%SZ)" nota="$nota" 2>/dev/null || true
  done
}

# Credencial de git via la cuenta gh de /data/gh (idempotente, best-effort; igual que worker_dev).
gh auth setup-git >/dev/null 2>&1 || log "aviso: gh auth setup-git falló (¿gh sin login en /data/gh?); el push podría fallar"

log "arranca (repo=$REPO modelo=$MODELO intervalo=${INTERVALO}s CI=$CI)"

mkdir -p "$DATA" 2>/dev/null || true
reconciliar_huerfanas

while :; do
  [ -n "$PARAR" ] && { log "parada limpia"; exit 0; }   # SIGTERM recibido (deploy/stop): salir
  : > "$LATIDO" 2>/dev/null || true   # latido para el healthcheck
  # Heartbeat de vigilancia para guardian-ui: estado de la vigilancia + último pipeline visto.
  python3 "$CI_WATCH" --heartbeat "$ESTADO_VIGILANCIA" "$CI" 2>/dev/null || true
  # Cierra las sesiones `verificando` cuyo pipeline del fix ya tenga veredicto (verde/rojo).
  [ "$CI" = 1 ] && verificar_pendientes

  # No tocar `main` durante un deploy ni con un keeper ya en marcha.
  if [ -f "$FLAG_DEPLOY" ] || [ -f "$LOCK" ]; then
    sleep "$INTERVALO"; continue
  fi

  # --- Disparo 1: CI ROJO (réplica de ci-verde) -------------------------------------------
  if [ "$CI" = 1 ]; then
    ci="$(python3 "$CI_WATCH" 2>/dev/null)"
    num="$(printf '%s\n' "$ci" | sed -n 's/^PIPELINE_ROJO=//p' | head -1)"
    huella_nueva="$(printf '%s\n' "$ci" | sed -n 's/^HUELLA=//p' | head -1)"
    if [ -z "$num" ]; then
      :  # último completo verde / nada que arreglar
    elif buscar_huella "$huella_nueva" verificando >/dev/null 2>&1; then
      # FIX-AWARE: ya tengo un fix MÍO EN VERIFICACIÓN para ESTOS MISMOS fallos. El rojo nuevo es el
      # lag de propagación de algo que ya estoy esperando: NO re-intento, espero su veredicto.
      log "CI ROJO #$num: mismos fallos que un fix en verificación -> espero su veredicto (no re-intento)"
    elif [ "$num" != "$(cat "$CI_ULTIMO" 2>/dev/null)" ] || pendiente_para "CI #$num"; then
      # Dispara si el rojo es NUEVO (≠ CI_ULTIMO, antiflapping) O si el MISMO rojo quedó pendiente de
      # re-trabajo (su última sesión fue interrumpida/fallida). Lo segundo rompe el deadlock: un deploy
      # que cortaba la sesión dejaba CI_ULTIMO=N y el keeper saltaba N para siempre. Las sesiones
      # corriendo (LOCK, arriba) y verificando (rama de arriba) ya están cubiertas, así que esto no
      # re-dispara sobre algo en marcha.
      n="$(ci_intentos_recientes)"
      if [ "$n" -ge "$CI_MAX" ]; then
        log "CI sigue rojo tras $n intentos en ${CI_VENTANA_MIN}min: pauso el auto-fix; requiere humano"
      else
        # ¿ya hay una sesión RESUMIBLE para este rojo? — un fix que NO bastó (`fallido`) o uno que un
        # deploy CORTÓ a media sesión (`interrumpido`). Resume esa conversación (el agente ya sabe qué
        # diagnosticó/intentó) en vez de empezar de cero. Empareja por huella o por trigger "CI #$num".
        resume_id="$(buscar_resumible "$huella_nueva" "CI #$num" 2>/dev/null)" || resume_id=""
        echo "$num" > "$CI_ULTIMO"; echo "$(date +%s)" >> "$CI_INTENTOS"
        log "CI ROJO pipeline #$num: lanzo fix${resume_id:+ (resume $resume_id)}"
        correr_keeper "El pipeline #$num de \`main\` está ROJO en el CI (Woodpecker). Es el ORIGEN de
la racha roja actual (el primer rojo tras el último verde); puede haber rojos posteriores que
HEREDEN este fallo, así que arreglar este suele devolver \`main\` a verde. Es un fix de CÓDIGO:
arréglalo según la sección de CI de tu rol y promueve a main. Evidencia:

$ci" "CI #$num" "$num" "$huella_nueva" "$resume_id"
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
