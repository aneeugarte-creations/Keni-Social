#!/bin/sh
# Despliegue / cutover de keni-social en el server Latitude (mismo host que el agente
# Woodpecker). Lo invoca `.woodpecker/deploy.yml` (disparo manual) montando el
# docker.sock del host y el .env de secretos; tambien sirve para correrlo a mano por SSH:
#
#   cd /home/ubuntu/keni-social/deploy && sh deploy.sh .env
#
# Idempotente y NO destructivo. La operacional vive en Postgres (ADR 0004; SQLite ya no
# existe); el paso de migracion garantiza el esquema (no-op tras la ADR). La media sigue
# en DISCO hasta que se bootstrapee Garage y se pongan las S3_* reales en el .env (ver
# deploy/README.md, "Cutover a Postgres + S3").
set -eu

# Ubicarse en deploy/ (el contexto de build de las imagenes propias es la raiz `..`).
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

ENVFILE="${1:-.env}"
DC="docker compose --env-file $ENVFILE"
VOL="keni-social_keni-data"   # volumen de estado (proyecto compose = keni-social)
REPO_VOL="keni-social_keni-repo"  # clon git del carril de auto-desarrollo (worker-dev/worker-ralph)

# Lee una clave del .env (primera ocurrencia, sin comillas envolventes).
leer_env() {
  v="$(sed -n "s/^$1=//p" "$ENVFILE" | head -n1)"
  v="${v%\"}"; v="${v#\"}"
  printf '%s' "$v"
}

# ── GUARDA: la app NO debe conectar a Postgres como SUPERUSUARIO ──────────────────────
# Con DATABASE_URL vacia el back DERIVA la URL de POSTGRES_* y conecta como el rol
# bootstrap (superusuario). En hosted eso es un agujero de minimo privilegio: la app debe
# conectar como `keni_app` (rol sin superuser que crea postgres/initdb/10-app-role.sh).
# Este deploy FALLA si la URL efectiva apunta al superusuario, salvo override explicito
# KENI_PERMITIR_SUPERUSER=1 (en el .env o exportado), pensado solo para bootstrap/recuperacion.
DB_URL_EFECTIVA="$(leer_env DATABASE_URL)"
PG_SUPERUSER="$(leer_env POSTGRES_USER)"
PERMITIR_SUPER="$(leer_env KENI_PERMITIR_SUPERUSER)"
[ "${KENI_PERMITIR_SUPERUSER:-}" = "1" ] && PERMITIR_SUPER=1
USUARIO_URL=""
case "$DB_URL_EFECTIVA" in
  *://*) USUARIO_URL="$(printf '%s' "$DB_URL_EFECTIVA" | sed -E 's#^[a-z+]+://([^:/@]*).*#\1#')" ;;
esac
if [ -z "$DB_URL_EFECTIVA" ] || { [ -n "$PG_SUPERUSER" ] && [ "$USUARIO_URL" = "$PG_SUPERUSER" ]; }; then
  if [ "$PERMITIR_SUPER" = "1" ]; then
    printf '\033[31m==> AVISO: la app conectara a Postgres como SUPERUSUARIO (override KENI_PERMITIR_SUPERUSER=1).\033[0m\n' >&2
  else
    printf '\033[31m==> ERROR: DATABASE_URL apunta al superusuario de Postgres (o esta vacia y se derivaria de POSTGRES_*).\033[0m\n' >&2
    printf '\033[31m    Fija en %s:  DATABASE_URL=postgresql://keni_app:<APP_DB_PASSWORD>@db:5432/<POSTGRES_DB>\033[0m\n' "$ENVFILE" >&2
    printf '\033[31m    (rol keni_app: ver deploy/postgres/initdb/10-app-role.sh y deploy/.env.example). Para forzar\033[0m\n' >&2
    printf '\033[31m    EXPRESAMENTE el superusuario (bootstrap/recuperacion): KENI_PERMITIR_SUPERUSER=1.\033[0m\n' >&2
    exit 1
  fi
fi

# VERSIONADO POR CONTENIDO (deploy QUIRÚRGICO). La tag de CADA imagen es un HASH de SUS entradas
# de build; así solo se (re)construye y recrea el servicio cuyo contenido cambió. Un deploy de
# SOLO front (o solo mcp) NO toca el worker. back y worker comparten `consola/`: un cambio ahí
# recrea ambos (el worker DEBE correr ese código). El hash sale del ÁRBOL de ficheros (no de git:
# este script corre en el dir estable del host, cuyo .git puede no estar sincronizado). El janitor
# sigue conservando N por repo (ordena por CreatedAt); una imagen sin cambios no se reconstruye.
RAIZ="$(cd .. && pwd)"   # raíz del repo (deploy/ es el cwd; el contexto de build es `..`)
# SEGURIDAD ante "deploy perdido": el hash debe incluir TODO lo que afecta al runtime de la
# imagen; si se dejara una entrada fuera, un cambio real no cambiaría el hash y el código viejo
# se quedaría en prod. Por eso solo BORRAMOS artefactos/VCS que NUNCA son fuente (node_modules,
# __pycache__, .git, caches, y las salidas de build webapp/dist) y, vía `$2`, la ÚNICA exclusión
# de fuente justificada: `consola/frontend` para las imágenes Python (ver abajo). Todo lo demás
# se hashea, incluidos ficheros NUEVOS a nivel `consola/` (p.ej. un MANIFEST.in futuro).
hash_entradas() {  # $1 = prefijo de path a EXCLUIR (o "") ; $2.. = paths -> 12 hex del contenido
  excl="$1"; shift
  # Post-filtro con `grep -v` (no inyectamos args en find: evita depender del word-splitting
  # del shell). El `find` imprime paths RELATIVOS a la raíz; `^$excl` ancla el prefijo a excluir.
  ( cd "$RAIZ" && find "$@" \( -name node_modules -o -name .git -o -name __pycache__ \
        -o -name '.venv*' -o -name .ruff_cache -o -name webapp -o -name dist \) -prune \
        -o -type f -print 2>/dev/null \
    | if [ -n "$excl" ]; then grep -v "^$excl"; else cat; fi \
    | LC_ALL=C sort | xargs sha1sum 2>/dev/null ) | sha1sum | cut -c1-12
}
# Entradas de build de cada imagen (ver los Dockerfile en deploy/<svc>/). Para back/worker se
# hashea `consola` ENTERO MENOS `consola/frontend`: el Dockerfile copia `consola/` completo, así
# que cualquier fichero suyo (src, pyproject, README, o uno nuevo) puede acabar en la imagen y
# DEBE contar. La ÚNICA exclusión es `consola/frontend`: es el código FUENTE del SPA (TypeScript),
# que en prod sirve nginx (front) y el back/worker NUNCA leen en runtime (sirven `webapp/`, la
# salida de vite, no el fuente). Excluirla es lo que permite que un deploy de SOLO front no recree
# el worker, y es seguro porque NO es entrada de runtime de las imágenes Python. `consola/tests`
# SÍ se incluye (no es runtime, pero incluirlo no puede causar un deploy perdido: como mucho una
# recreación de más, el lado seguro). front sí bundlea consola/frontend (sin exclusión).
FRONT_VERSION="$(hash_entradas "" consola/frontend deploy/front)"
BACK_VERSION="$(hash_entradas "consola/frontend/" keni-shared mcp-metricas consola deploy/back)"
WORKER_VERSION="$(hash_entradas "consola/frontend/" keni-shared mcp-metricas consola deploy/worker)"
MCP_VERSION="$(hash_entradas "" keni-shared mcp-metricas deploy/mcp)"
export FRONT_VERSION BACK_VERSION WORKER_VERSION MCP_VERSION
echo "==> versiones por contenido: front=$FRONT_VERSION back=$BACK_VERSION worker=$WORKER_VERSION mcp=$MCP_VERSION"

# Render de secretos ANTES de cualquier `compose build/run/up`: los servicios montan
# ./secrets/<n> en /run/secrets; si no existieran al instanciar contenedores, Compose
# fallaria. El codigo los lee via env `*_FILE` (no viajan como env -> no salen en
# `docker inspect`). El operador sigue editando el .env; este render es derivado.
#
# PERMISOS: el DIRECTORIO es 0700 (solo root/dueño entra) -> en el HOST nadie sin
# privilegios lee los secretos. Los FICHEROS van con MINIMO PRIVILEGIO por consumidor:
# Compose (no-swarm) bind-montea el fichero del host TAL CUAL en /run/secrets, asi que
# el uid/gid del host es el que ve el contenedor. Asignamos dueño = uid del contenedor
# que lo lee y modo 0400/0440:
#   - 10001:10001 0400  -> secretos SOLO de la app (back/daemons/worker corren uid 10001).
#   - 10001:999   0440  -> postgres_password: lo leen la app (uid 10001, dueño) Y el
#                          entrypoint de la imagen postgres (uid 999, via grupo).
#   - 0:0         0400  -> secretos de Garage (corre como root; ademas Garage RECHAZA
#                          ficheros de secreto world-readable).
# FALLBACK: si este script corre SIN privilegio de chown (p.ej. a mano como `ubuntu`),
# se queda el modelo anterior (0644 dentro del dir 0700, que ya bloquea el traverse a
# terceros) con un AVISO, para no romper el arranque de los contenedores.
echo "==> [1a/6] render de secretos a ./secrets/ (dir 0700; ficheros 0400/0440 por consumidor)"
SECRETS_DIR="$(pwd)/secrets"
mkdir -p "$SECRETS_DIR"; chmod 700 "$SECRETS_DIR"
render_secret() {  # $1 = clave en .env ; $2 = fichero ; $3 = dueño uid:gid ; $4 = modo
  val="$(sed -n "s/^$1=//p" "$ENVFILE" | head -n1)"
  val="${val%\"}"; val="${val#\"}"      # quita comillas envolventes opcionales
  rm -f "$SECRETS_DIR/$2"               # recrear: un run previo pudo dejarlo 0400 de otro dueño
  printf '%s' "$val" > "$SECRETS_DIR/$2"
  if chown "$3" "$SECRETS_DIR/$2" 2>/dev/null; then
    chmod "$4" "$SECRETS_DIR/$2"
  elif [ "$3" = "0:0" ]; then
    # Garage rechaza secretos world-readable: 0600 (un contenedor root los lee igual).
    chmod 600 "$SECRETS_DIR/$2"
    echo "==> AVISO: sin privilegio para chown $3 sobre secrets/$2; se deja 0600" >&2
  else
    chmod 644 "$SECRETS_DIR/$2"
    echo "==> AVISO: sin privilegio para chown $3 sobre secrets/$2; se deja 0644 (el dir 0700 protege en host)" >&2
  fi
}
render_secret POSTGRES_PASSWORD        postgres_password        10001:999    440
render_secret S3_ACCESS_KEY            s3_access_key            10001:10001  400
render_secret S3_SECRET_KEY            s3_secret_key            10001:10001  400
render_secret ANTHROPIC_API_KEY        anthropic_api_key        10001:10001  400
render_secret KENI_CONSOLA_ADMIN_PASS  consola_admin_pass       10001:10001  400
render_secret KENI_CONSOLA_TOKEN       consola_token            10001:10001  400
render_secret KENI_MCP_BEARER          mcp_bearer               10001:10001  400
render_secret GARAGE_RPC_SECRET        garage_rpc_secret        0:0          400
render_secret GARAGE_ADMIN_TOKEN       garage_admin_token       0:0          400

# Build SELECTIVO: cada servicio se (re)construye SOLO si su imagen-por-hash no existe ya (=
# su contenido cambió). Si ya existe, se salta -> su tag NO cambia -> el `up -d` final no lo
# recrea (ni interrumpe el worker). `daemons` comparte la imagen del `worker` (no se build aparte):
# `cambio` (imagen AÚN no construida) marca los flags ANTES de construir, para gatear los pasos
# de esquema/estado. La detección va SEPARADA del build a propósito: así un fallo de `$DC build`
# aborta el deploy por `set -e` (sin `|| true` que lo enmascare) y deja prod intacto.
cambio() { ! docker image inspect "$1" >/dev/null 2>&1; }  # 0 (true) si la imagen NO existe aún
BACK_CAMBIO=0; WORKER_CAMBIO=0
cambio "keni-social/back:$BACK_VERSION"     && BACK_CAMBIO=1   || true
cambio "keni-social/worker:$WORKER_VERSION" && WORKER_CAMBIO=1 || true

construir() {  # $1 = servicio compose ; $2 = imagen:tag esperada (keni-social/<svc>:<hash>)
  if docker image inspect "$2" >/dev/null 2>&1; then
    echo "==> $1: sin cambios ($2 ya existe) — no se reconstruye ni recrea"
    return 0
  fi
  echo "==> $1: cambió -> build $2"
  $DC build "$1"                                     # un fallo aquí aborta el deploy (set -e)
  docker tag "$2" "keni-social/$1:latest" || true   # :latest = conveniencia/rollback legible
}
echo "==> [1/6] build SELECTIVO (solo imagenes cuyo contenido cambió)"
construir front  "keni-social/front:$FRONT_VERSION"
construir back   "keni-social/back:$BACK_VERSION"
construir worker "keni-social/worker:$WORKER_VERSION"
construir mcp    "keni-social/mcp:$MCP_VERSION"

# Pasos de ESQUEMA/ESTADO: SOLO cuando cambió el código del back/worker (comparten `consola/`).
# Un deploy de solo front no toca el esquema ni el volumen de estado (ni para el back).
if [ "$BACK_CAMBIO" = 1 ]; then
  echo "==> [2/6] stop back (breve indisponibilidad mientras se aplica el esquema)"
  $DC stop back || true
else
  echo "==> [2/6] back sin cambios — no se para (sin indisponibilidad)"
fi

if [ "$BACK_CAMBIO" = 1 ] || [ "$WORKER_CAMBIO" = 1 ]; then
  echo "==> [3/6] chown del volumen de estado a uid no-root 10001 (back/worker corren no-root)"
  docker run --rm -v "$VOL":/d alpine chown -R 10001:10001 /d
  # El carril de auto-desarrollo (worker-dev/worker-ralph, uid 10001) escribe en /repo: el volumen
  # keni-repo nace root, así que hay que cederlo al uid del contenedor (idempotente). Crea el
  # volumen si no existe todavía.
  echo "==> [3b/6] chown del volumen keni-repo (clon git del carril dev) a uid 10001"
  docker volume create "$REPO_VOL" >/dev/null 2>&1 || true
  docker run --rm -v "$REPO_VOL":/d alpine chown -R 10001:10001 /d
else
  echo "==> [3/6] back/worker sin cambios — se omite chown del volumen"
fi

# SIEMBRA del clon git en /repo (best-effort, idempotente): si el volumen keni-repo está VACÍO y
# gh ya tiene credencial en /data/gh, clona kenitech-io/keni-social. NO aborta el deploy si falla
# (p.ej. GitHub aún sin conectar desde la UI): en ese caso el carril dev queda inerte hasta que se
# conecte el proveedor y se siembre el clon (manual o por el propio worker-dev). Corre como uid
# 10001 (dueño de /repo y /data) para que la credencial gh y los permisos cuadren.
if docker image inspect "keni-social/worker:$WORKER_VERSION" >/dev/null 2>&1; then
  echo "==> [3c/6] siembra idempotente del clon git en keni-repo (best-effort; no aborta el deploy)"
  docker run --rm --user 10001:10001 \
    -e XDG_CONFIG_HOME=/data -e GH_PROMPT_DISABLED=1 \
    -v "$REPO_VOL":/repo -v "$VOL":/data \
    --entrypoint sh "keni-social/worker:$WORKER_VERSION" -c '
      if [ -n "$(ls -A /repo 2>/dev/null)" ]; then
        echo "    /repo ya tiene contenido — no se reclona"
      elif gh auth status >/dev/null 2>&1; then
        echo "    clonando kenitech-io/keni-social en /repo (vía gh)"
        gh repo clone kenitech-io/keni-social /repo
      else
        echo "    gh sin credencial en /data/gh todavía — se sembrará al conectar GitHub (carril dev inerte)"
      fi
    ' || echo "==> AVISO: siembra de /repo no completada (no bloquea el deploy)" >&2
fi

if [ "$BACK_CAMBIO" = 1 ]; then
  echo "==> [4/6] asegura esquema Postgres (idempotente; ADR 0004)"
  $DC run --rm --no-deps -T back python -m keni_consola.migracion --solo-db
  # El `back` arranca uvicorn-factory (no pasa por `__main__`), así que la inicialización de la Texto
  # NO corre en su arranque: la materializamos aquí para que los prompts/editorial NUEVOS de la
  # imagen aparezcan en el estudio. Idempotente; no pisa ediciones del equipo.
  echo "==> [4b/6] inicializa Texto: importa prompts/editorial base que falten (idempotente)"
  $DC run --rm --no-deps -T back python -m keni_consola.inicializar
else
  echo "==> [4/6] back sin cambios — esquema ya vigente, se omite la migración/inicialización"
fi

# ── ROLLBACK AUTOMATICO ───────────────────────────────────────────────────────────────
# Antes del `up` se taggean las imagenes EN EJECUCION como `:previa` (foto del estado
# bueno). Tras el `up` se espera a que back y front queden `healthy`; si no lo logran en
# el plazo, se vuelve a `:previa` y el script sale 1 (pipeline ROJO). Robusto al primer
# despliegue: si un servicio no corre aun, simplemente no hay `:previa` para el y no se
# intenta revertirlo. NOTA: la migracion de esquema ([4/6]) no se revierte (es aditiva e
# idempotente por diseño, ADR 0004). Escape para emergencias: KENI_DEPLOY_SIN_VERIFICAR=1
# (en el .env o exportado) salta la verificacion/rollback.
echo "==> [5/6] foto de rollback: tag :previa de las imagenes en ejecucion"
foto_previa() {  # $1 = servicio
  id="$(docker inspect --format '{{.Image}}' "keni-social-$1-1" 2>/dev/null || true)"
  if [ -n "$id" ]; then docker tag "$id" "keni-social/$1:previa"; fi
}
foto_previa front; foto_previa back; foto_previa worker; foto_previa mcp

echo "==> [5b/6] up (recrea SOLO los servicios cuya imagen o config cambió)"
$DC up -d
$DC ps

espera_sano() {  # $1 = servicio compose ; $2 = timeout en segundos. 0 si llega a healthy.
  transcurrido=0
  while [ "$transcurrido" -le "$2" ]; do
    cid="$($DC ps -q "$1" 2>/dev/null | head -n1)"
    estado="desconocido"
    if [ -n "$cid" ]; then
      estado="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo desconocido)"
    fi
    if [ "$estado" = "healthy" ]; then return 0; fi
    sleep 5; transcurrido=$((transcurrido + 5))
  done
  echo "==> $1 NO esta healthy tras ${2}s (ultimo estado: $estado)" >&2
  return 1
}

SIN_VERIFICAR="$(leer_env KENI_DEPLOY_SIN_VERIFICAR)"
[ "${KENI_DEPLOY_SIN_VERIFICAR:-}" = "1" ] && SIN_VERIFICAR=1
if [ "$SIN_VERIFICAR" = "1" ]; then
  echo "==> [6/6] verificacion de salud SALTADA (KENI_DEPLOY_SIN_VERIFICAR=1)"
else
  echo "==> [6/6] verificacion de salud (back, front, daemons, worker) con rollback automatico"
  # back: healthcheck del Dockerfile = curl /healthz (start_period 20s, interval 30s).
  # daemons: healthcheck por fichero de latido (compose; el proceso lo toca cada 30s).
  # worker: healthcheck por escaneo de /proc (compose). Ambos son imagenes NUESTRAS con
  # foto :previa, asi que un fallo suyo tambien debe disparar el rollback (antes solo se
  # verificaban back/front y un daemons/worker roto pasaba en verde).
  # worker-dev / worker-ralph: imagenes NUESTRAS (misma tag WORKER_VERSION), asi que un fallo
  # suyo tambien debe disparar el rollback (que ya cubre el tag worker:previa de abajo).
  if espera_sano back 180 && espera_sano front 120 \
      && espera_sano daemons 150 && espera_sano worker 120 \
      && espera_sano worker-dev 120 && espera_sano worker-ralph 120; then
    echo "==> salud OK (back, front, daemons, worker, worker-dev y worker-ralph healthy)"
    # db y files: si NO estan sanos el problema es de CONFIG/estado (sus imagenes son
    # upstream y no entran en el rollback :previa), asi que NO se intenta rollback —
    # pero el pipeline DEBE quedar rojo para que un operador mire (p.ej. un cambio de
    # secretos de Garage que le impida arrancar).
    if ! espera_sano db 60 || ! espera_sano files 150; then
      printf '\033[31m==> db/files NO healthy tras el deploy (fallo de config/estado, sin rollback automatico). Revisa: docker logs keni-social-db-1 / keni-social-files-1\033[0m\n' >&2
      exit 1
    fi
  else
    printf '\033[31m==> VERIFICACION FALLIDA: rollback a las imagenes :previa\033[0m\n' >&2
    FRONT_NUEVA="$FRONT_VERSION"; BACK_NUEVA="$BACK_VERSION"
    WORKER_NUEVA="$WORKER_VERSION"; MCP_NUEVA="$MCP_VERSION"
    hay_previa() { docker image inspect "keni-social/$1:previa" >/dev/null 2>&1; }
    hay_previa front  && FRONT_VERSION=previa
    hay_previa back   && BACK_VERSION=previa
    hay_previa worker && WORKER_VERSION=previa
    hay_previa mcp    && MCP_VERSION=previa
    export FRONT_VERSION BACK_VERSION WORKER_VERSION MCP_VERSION
    $DC up -d || true
    $DC ps || true
    # Untag de las versiones fallidas: el proximo deploy del mismo contenido RECONSTRUYE
    # (si no, `construir` veria la imagen-por-hash ya creada y re-desplegaria la mala).
    [ "$FRONT_VERSION" = previa ]  && docker rmi "keni-social/front:$FRONT_NUEVA"   >/dev/null 2>&1 || true
    [ "$BACK_VERSION" = previa ]   && docker rmi "keni-social/back:$BACK_NUEVA"     >/dev/null 2>&1 || true
    [ "$WORKER_VERSION" = previa ] && docker rmi "keni-social/worker:$WORKER_NUEVA" >/dev/null 2>&1 || true
    [ "$MCP_VERSION" = previa ]    && docker rmi "keni-social/mcp:$MCP_NUEVA"       >/dev/null 2>&1 || true
    printf '\033[31m==> ROLLBACK aplicado; el deploy queda EN ROJO. Revisa logs: docker logs keni-social-back-1\033[0m\n' >&2
    exit 1
  fi
fi
echo "==> OK. Los servicios sin cambios (p.ej. el worker en un deploy de front) NO se recrearon."
