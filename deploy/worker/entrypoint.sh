#!/bin/sh
# Carga las credenciales de Claude desde ficheros de secreto (Docker secrets) si vienen
# como `<VAR>_FILE`, y las exporta al entorno justo antes de arrancar el worker. El worker
# se las pasa al subproceso `claude -p` (que solo lee de env). Asi el valor NO aparece en
# `docker inspect` del contenedor (solo el path *_FILE). Si la env directa ya esta, manda.
set -e
for var in ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN; do
  eval "directa=\${$var:-}"
  eval "fichero=\${${var}_FILE:-}"
  if [ -z "$directa" ] && [ -n "$fichero" ] && [ -f "$fichero" ]; then
    export "$var=$(cat "$fichero")"
  fi
done
exec "$@"
