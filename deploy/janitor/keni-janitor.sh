#!/usr/bin/env bash
# Janitor de imagenes Docker del server de keni-social (Latitude).
#
# Politica (decidida 2026-05):
#   - Imagenes de la app con tag VERSIONADO (ver deploy/deploy.sh). Este job
#     CONSERVA las KEEP mas recientes por repo `keni-social/*` y borra los tags
#     mas viejos. Nunca borra una imagen usada por un contenedor (Docker lo
#     impide igual; ademas la saltamos explicitamente).
#   - PRUNE solo si el disco supera THRESHOLD% usado ("sobre todo si queda poco
#     espacio"): entonces baja la retencion a 1, borra dangling y vacia el build
#     cache. No hace un `prune -a` global para no tocar otras pilas del host
#     (p.ej. el sistema legado "learn").
#
# Config opcional en /etc/keni-janitor.conf (KEEP=, THRESHOLD=, REPO_REGEX=).
# Lo dispara keni-janitor.timer (diario). Idempotente y seguro.
set -uo pipefail

KEEP="${KEEP:-5}"
THRESHOLD="${THRESHOLD:-50}"
REPO_REGEX="${REPO_REGEX:-^keni-social/}"
LOG="${LOG:-/var/log/keni-janitor.log}"
# Belt-and-suspenders (#128): poda de registros YAML de generacion viejos en el volumen de
# datos. La fuente de verdad de la poda es el daemon (reaper -> generaciones.podar_generaciones,
# que respeta el piso de los N mas recientes); esto es solo una red de seguridad por si el
# daemon estuviera caido. SOLO actua si GEN_DIR apunta a un dir existente (def: el subdir de
# generaciones del volumen `keni-data`). Borra por MTIME mas viejo que GEN_DIAS dias (def 30,
# igual que el default del daemon). OFF si GEN_DIR no existe.
GEN_DIR="${GEN_DIR:-/var/lib/docker/volumes/keni-data/_data/keni-social/generaciones}"
GEN_DIAS="${GEN_DIAS:-30}"

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG" >&2; }

command -v docker >/dev/null 2>&1 || { log "ERROR: docker no encontrado"; exit 1; }

# IDs (full sha256) de imagenes usadas por CUALQUIER contenedor (vivo o parado).
mapfile -t in_use < <(docker ps -aq | xargs -r docker inspect -f '{{.Image}}' 2>/dev/null | sort -u)
is_in_use() { local id="$1" u; for u in "${in_use[@]:-}"; do [ "$u" = "$id" ] && return 0; done; return 1; }

# Disco: % usado de /
used="$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')"; used="${used:-0}"

aggressive=0; eff_keep="$KEEP"
if [ "$used" -ge "$THRESHOLD" ]; then aggressive=1; eff_keep=1; fi
log "== janitor inicio (disco=${used}% umbral=${THRESHOLD}% keep=${eff_keep} agresivo=${aggressive}) =="

# 1) Conservar las eff_keep imagenes mas recientes por repo keni-social/*
mapfile -t repos < <(docker images --format '{{.Repository}}' | sort -u | grep -E "$REPO_REGEX" || true)
for repo in "${repos[@]:-}"; do
  [ -z "$repo" ] && continue
  mapfile -t victims < <(docker images "$repo" --no-trunc \
      --format '{{.CreatedAt}}|{{.ID}}|{{.Repository}}:{{.Tag}}' \
      | sort -r | tail -n +"$((eff_keep + 1))")
  for v in "${victims[@]:-}"; do
    [ -z "$v" ] && continue
    id="${v#*|}"; id="${id%%|*}"; ref="${v##*|}"
    [ "$ref" = "${ref%%:<none>}" ] || continue   # dangling: lo maneja el prune
    if is_in_use "$id"; then log "  conservo (en uso): $ref"; continue; fi
    if docker rmi "$ref" >/dev/null 2>&1; then log "  borrado tag viejo: $ref"
    else log "  no borrado (refs/en uso): $ref"; fi
  done
done

# 2) Prune solo por encima del umbral de disco
if [ "$aggressive" = 1 ]; then
  log "  umbral superado -> prune: dangling + build cache"
  docker image prune -f    >/dev/null 2>&1 || true
  docker builder prune -af >/dev/null 2>&1 || true
  log "  disco tras prune: $(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')%"
else
  log "  bajo umbral: solo retencion de tags (sin prune)"
fi

# 3) Poda de registros de generacion viejos (belt-and-suspenders, #128). Solo registros
#    `<12hex>.yaml` mas viejos que GEN_DIAS dias; nunca toca temporales `.tmp-*` ni nada mas.
#    El daemon es la via principal (respeta el piso de los N mas recientes); esto es respaldo.
if [ -d "$GEN_DIR" ]; then
  before="$(find "$GEN_DIR" -maxdepth 1 -type f -name '*.yaml' 2>/dev/null | wc -l | tr -d ' ')"
  deleted="$(find "$GEN_DIR" -maxdepth 1 -type f -regextype posix-extended \
      -regex '.*/[0-9a-f]{12}\.yaml' -mtime "+${GEN_DIAS}" -print -delete 2>/dev/null | wc -l | tr -d ' ')"
  log "  generaciones: ${deleted:-0} registro(s) viejo(s) (>${GEN_DIAS}d) borrado(s) de ${before:-0} en $GEN_DIR"
else
  log "  generaciones: GEN_DIR no existe ($GEN_DIR), se omite poda de registros"
fi
log "== janitor fin =="
