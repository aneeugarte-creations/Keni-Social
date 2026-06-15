#!/bin/sh
# Exporta secretos OPCIONALES de Claude desde ficheros de secreto (Docker secrets) si vienen
# como `<VAR>_FILE`, justo antes de arrancar el worker. Hoy solo la API key opcional
# (ANTHROPIC_API_KEY); la CUENTA de Claude se fija con `claude auth login` desde el panel y
# vive como credenciales en CLAUDE_CONFIG_DIR (/data), no como env. Así el valor NO aparece en
# `docker inspect` (solo el path *_FILE). Si la env directa ya esta, manda.
set -e
for var in ANTHROPIC_API_KEY; do
  eval "directa=\${$var:-}"
  eval "fichero=\${${var}_FILE:-}"
  if [ -z "$directa" ] && [ -n "$fichero" ] && [ -f "$fichero" ]; then
    export "$var=$(cat "$fichero")"
  fi
done
exec "$@"
