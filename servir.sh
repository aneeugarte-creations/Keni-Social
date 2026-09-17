#!/usr/bin/env bash
# Sirve la maqueta de la presentación PDF de Métricas en localhost.
# Uso: bash servir.sh   ->   http://localhost:4456/presentacion.html
set -euo pipefail
cd "$(dirname "$0")/consola/frontend"
exec npm run dev -- --port 4456 --strictPort
