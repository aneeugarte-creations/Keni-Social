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

# ── Gate de seams (pre-push, síncrono, SIN Postgres) ──────────────────────────
# Con ~7 autores empujando directo a `main`, los rojos más frecuentes son seams no
# propagados (un cambio en un lado de una frontera sin tocar el otro) y errores de
# fronteras/catálogo/tipos. Hoy solo se ven en CI DESPUÉS de aterrizar en `main`,
# donde bloquean a todos. Este gate replica los steps BARATOS del CI (sin BD) sobre
# el árbol final ya rebasado, con el autor presente para arreglar:
#   - contrato-fronteras: lint de fronteras + catálogo (.woodpecker/fronteras.yml).
#   - frontend: tsc + bundle (.woodpecker/frontend-build.yml), solo si tocas el front.
# Es PARCIAL a propósito: no levanta la suite pytest (necesita Postgres y es lenta).
# Degradación elegante: si el entorno del que promueve no puede correr un check (sin
# venv editable, sin node_modules…), AVISA y CONTINÚA — no bloquea a ciegas a quien
# no tenga el entorno; el CI sigue siendo la red final.
# Kill-switch: KENI_PROMOVER_SIN_GATE=1 lo salta entero (emergencias).
if [ "${KENI_PROMOVER_SIN_GATE:-0}" = "1" ]; then
  echo "⚠ KENI_PROMOVER_SIN_GATE=1: me salto el gate de seams (bajo tu responsabilidad)." >&2
else
  raiz="$(git rev-parse --show-toplevel)"
  archivos_cambiados="$(git diff --name-only origin/main..HEAD)"
  toca() { printf '%s\n' "$archivos_cambiados" | grep -qE "$1"; }
  py="$(command -v python || command -v python3 || true)"

  # contrato-fronteras: corre si el diff toca backend o los workflows (mismo path
  # filter que .woodpecker/fronteras.yml).
  if toca '^(consola/|keni-shared/|mcp-metricas/|\.woodpecker/)'; then
    if [ -z "$py" ] || ! "$py" -c 'import keni_consola, pytest' >/dev/null 2>&1; then
      echo "⚠ Gate fronteras OMITIDO: sin entorno Python editable (instala con" >&2
      echo "  'pip install -e ./keni-shared -e ./mcp-metricas -e ./consola'). El CI lo cubrirá." >&2
    else
      echo "→ Gate: contrato de fronteras + catálogo"
      if ! "$py" -m pytest "$raiz/consola/tests/test_fronteras.py" "$raiz/consola/tests/test_catalogo.py" "$raiz/consola/tests/test_facades.py" -q; then
        echo "✗ Gate de fronteras ROJO. Arréglalo antes de promover (o KENI_PROMOVER_SIN_GATE=1 para saltarlo)." >&2
        exit 1
      fi
    fi
  fi

  # frontend: corre si el diff toca el front o el contrato de tipos (mismo path
  # filter que .woodpecker/frontend-build.yml). `npm run build` = tsc -b && vite build.
  if toca '^(consola/frontend/|consola/src/keni_consola/esquema_api/)'; then
    if ! command -v npm >/dev/null 2>&1 || [ ! -d "$raiz/consola/frontend/node_modules" ]; then
      echo "⚠ Gate frontend OMITIDO: falta npm o node_modules (corre 'npm ci' en consola/frontend). El CI lo cubrirá." >&2
    else
      echo "→ Gate: build del frontend (tsc -b && vite build)"
      if ! ( cd "$raiz/consola/frontend" && npm run build ); then
        echo "✗ Gate de frontend ROJO (tipos/bundle). Arréglalo antes de promover (o KENI_PROMOVER_SIN_GATE=1)." >&2
        exit 1
      fi
    fi
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
