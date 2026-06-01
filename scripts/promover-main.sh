#!/usr/bin/env bash
#
# Promueve la rama del worktree ACTUAL a `main` de forma SEGURA (flujo del repo:
# worktree -> push a `main`, sin PR; ver CLAUDE.md).
#
# Por qué existe: el footgun real es borrar la rama/worktree ANTES de confirmar el
# push. Con varios autores empujando directo a `main`, un push paralelo puede
# rechazar el tuyo (no fast-forward); si ya borraste la rama, el commit queda sin
# referencia. Este script hace, en orden: fetch -> rebase sobre origin/main ->
# enseña qué commits añade -> push. NO borra nada: la limpieza la haces tú DESPUÉS
# de ver "push OK", con los comandos que imprime al final.
#
# Uso: desde dentro del worktree de tu rama de integración:
#   bash scripts/promover-main.sh
#
set -euo pipefail

rama="$(git rev-parse --abbrev-ref HEAD)"
if [ "$rama" = "main" ]; then
  echo "✗ Estás en 'main'. Trabaja en un worktree + rama de integración, no sobre main." >&2
  exit 1
fi

echo "→ git fetch origin"
git fetch origin

echo "→ git rebase origin/main"
if ! git rebase origin/main; then
  echo "✗ Rebase con conflictos. Resuélvelos (o 'git rebase --abort') y reintenta." >&2
  exit 1
fi

# Qué vas a meter en main: revísalo. Si aparece algo que no es tuyo, PARA.
echo
echo "Commits que se añadirían a main (origin/main..HEAD):"
git --no-pager log --oneline origin/main..HEAD
echo

echo "→ git push origin ${rama}:main"
git push origin "${rama}:main"

echo
echo "✓ push OK. Ahora limpia (desde el checkout principal de main):"
echo "    git worktree remove $(git rev-parse --show-toplevel)"
echo "    git branch -D ${rama}"
echo "    git -C <checkout-main> pull --ff-only origin main"
