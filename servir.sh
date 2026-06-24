#!/usr/bin/env bash
# Sirve la vista previa del Informe PDF de Métricas en localhost.
# Uso: bash servir.sh   ->   http://localhost:4460/preview-informe.html
set -euo pipefail
cd "$(dirname "$0")/consola/frontend"
exec npm run dev -- --port 4460 --strictPort
