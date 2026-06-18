#!/bin/sh
# Exporta secretos OPCIONALES de Claude desde ficheros de secreto (Docker secrets) si vienen
# como `<VAR>_FILE`, justo antes de arrancar el worker. Hoy solo la API key opcional
# (ANTHROPIC_API_KEY) y el bearer del MCP de la app para los Ralph operativos (KENI_MCP_BEARER);
# la CUENTA de Claude se fija con `claude auth login` desde el panel y vive como credenciales en
# CLAUDE_CONFIG_DIR (/data), no como env. Así el valor NO aparece en `docker inspect` (solo el
# path *_FILE). Si la env directa ya esta, manda.
set -e
for var in ANTHROPIC_API_KEY KENI_MCP_BEARER; do
  eval "directa=\${$var:-}"
  eval "fichero=\${${var}_FILE:-}"
  if [ -z "$directa" ] && [ -n "$fichero" ] && [ -f "$fichero" ]; then
    export "$var=$(cat "$fichero")"
  fi
done

# Identidad de git para el carril de AUTO-DESARROLLO (worker-dev / worker-ralph): si vienen
# KENI_GIT_AUTHOR_NAME / KENI_GIT_AUTHOR_EMAIL, las fija como config global de git. Idempotente
# (cada arranque escribe el mismo valor); inocuo en worker/daemons (vars ausentes -> no hace nada).
if [ -n "${KENI_GIT_AUTHOR_NAME:-}" ]; then
  git config --global user.name "$KENI_GIT_AUTHOR_NAME"
fi
if [ -n "${KENI_GIT_AUTHOR_EMAIL:-}" ]; then
  git config --global user.email "$KENI_GIT_AUTHOR_EMAIL"
fi

exec "$@"
