#!/usr/bin/env bash
#
# Promueve la rama del worktree ACTUAL a `main` de forma SEGURA (flujo del repo:
# worktree -> push a `main`, sin PR; ver CLAUDE.md).
#
# Por qué existe: el peligro real es borrar la rama/worktree ANTES de confirmar el
# push. Con varios autores empujando directo a `main`, un push paralelo puede
# rechazar el tuyo (no fast-forward); si ya borraste la rama, el commit queda sin
# referencia. Este script hace, en orden: fetch -> rebase sobre origin/main ->
# guardia anti-regresión (corta si tu push borra trabajo reciente de main) ->
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

# ── Guardia anti-regresión ────────────────────────────────────────────────────
# El segundo peligro (visto en producción): resolver un conflicto del rebase
# "con mi versión", o promover una reescritura integral hecha sobre una base
# vieja, BORRA en silencio trabajo que otro agente acababa de meter en main.
# Detección: por cada línea que este push elimina, `git blame` sobre origin/main
# dice qué commit la añadió; si ese commit es reciente, casi seguro es una
# regresión accidental y no una retirada consciente.
umbral_dias="${KENI_PROMOVER_UMBRAL_DIAS:-2}"
ahora="$(date +%s)"
shas_borrados="$(
  git diff --name-status origin/main..HEAD | while IFS=$'\t' read -r estado archivo _; do
    # Solo M y D eliminan líneas de main. A no borra nada; R (rename) se omite:
    # el contenido sigue vivo en la ruta nueva y blamearlo daría falsos positivos.
    # (paréntesis de apertura obligatorio: un ')' suelto dentro de $() rompe bash 3.2)
    case "$estado" in (M|D) ;; (*) continue ;; esac
    git diff -U0 origin/main..HEAD -- "$archivo" |
      awk '/^@@/ { if (++c > 30) next                  # tope por archivo: blame no es gratis
                   n = split($2, a, ","); ini = substr(a[1], 2)
                   num = (n > 1) ? a[2] : 1
                   if (num + 0 > 0) print ini, num }' |
      while read -r ini num; do
        git blame --line-porcelain -L "${ini},$((ini + num - 1))" origin/main -- "$archivo" 2>/dev/null |
          awk -v ahora="$ahora" -v umbral="$((umbral_dias * 86400))" '
            /^[0-9a-f]{40} / { sha = substr($1, 1, 10) }
            /^committer-time / { if (ahora - $2 <= umbral) print sha }'
      done
  done | sort -u
)"

if [ -n "$shas_borrados" ]; then
  {
    echo
    echo "⚠ REGRESIÓN PROBABLE: este push ELIMINA líneas que main añadió en los últimos ${umbral_dias} días,"
    echo "  trabajo de estos commits:"
    echo "$shas_borrados" | while read -r s; do
      git --no-pager log -1 --format='    %h %cs %an — %s' "$s"
    done
    echo "  Revisa qué pierdes:  git diff origin/main..HEAD -- <archivo>   (las líneas '-')"
  } >&2
  if [ "${KENI_PROMOVER_ACEPTO_BORRADOS:-0}" = "1" ]; then
    echo "  KENI_PROMOVER_ACEPTO_BORRADOS=1: sigues bajo tu responsabilidad." >&2
  else
    {
      echo "  Si el borrado es INTENCIONADO (retirada/refactor consciente), repite con:"
      echo "    KENI_PROMOVER_ACEPTO_BORRADOS=1 bash scripts/promover-main.sh"
      echo "  Si NO lo es, reincorpora ese trabajo en tu rama antes de promover."
    } >&2
    exit 1
  fi
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
