---
titulo: "Build · implementar"
descripcion: "Cómo implementar en keni-social: estilo del repo, tests en el mismo commit, propagar ambos lados del seam, comentarios limpios y no romper fronteras (ADR 0005)."
tipo: editorial
clase: desarrollo
marcas: []
pipelines: []
creado: 2026-06-18T00:00:00+00:00
actualizado: 2026-06-18T00:00:00+00:00
---

# Build · implementar

Ejecutas el plan. Cambios pequeños y verificables. El objetivo es un diff limpio que deje `main` verde tras promover.

## Estilo del repo

- Python 3.11+, `from __future__ import annotations`, type hints. Imita el módulo vecino: nombres en español, docstrings que explican el PORQUÉ del diseño.
- Frontend: edita SIEMPRE `consola/frontend/src/`. Nunca toques `consola/src/keni_consola/webapp/` (outDir de vite, GITIGNORED). Reusa componentes shadcn de `components/ui/`.
- No introduzcas dependencias nuevas salvo que el plan lo exija explícitamente.

## Comentarios limpios (regla dura)

Un comentario describe QUÉ hace el código HOY, no el historial de bugs. Prohibido el contexto sucio: nada de «antes pasaba X», «esto se inyectaba dos veces», «regresión», «el agente anterior rompió…», «sin esto fallaba…». El porqué de un arreglo va en el MENSAJE DE COMMIT, no en el código.

## Tests en el MISMO commit

- Cambio de comportamiento = cambio de tests en el mismo commit. No promuevas dejando rojos «para que los encuentre el CI»: con varios agentes en paralelo, un rojo huérfano los bloquea a todos.
- Antes de dar por hecho un cambio, si tocas una firma de API, la FORMA de una respuesta, un esquema/constraint de BD, un contrato de fronteras (ADR 0005) o infra compartida (cola de jobs, allowlist de `tests/_postgres.py`), haz `grep` de los consumidores y actualiza sus tests en el mismo commit.

## Propaga el OTRO lado del seam

Casi todos los rojos recientes son el mismo patrón: un cambio aplicado a un lado de una frontera y no al otro. Antes de terminar, propaga la pareja de cada seam que tocaste:

- **Fachada de reexport**: símbolo en la fuente (`keni_shared`) → añádelo al import Y al `__all__` de la fachada (`keni_consola.marcas`, etc.). Si falta, lo verás como `module '…' has no attribute 'X'` en montones de tests.
- **Router nuevo**: autodescubierto bajo `api/`; si es top-level se declara en `apps/<app>.toml`; si cruza apps, enrútalo por keni-shared/gateway o añádelo a `SEAMS_PERMITIDOS` con justificación. Si declarar el `.toml` es propiedad del orquestador, déjalo en el informe.
- **Forma observable**: actualiza los tests que fijan la forma, en este commit.

## No corras la suite en local

No levantes Postgres ni ejecutes la suite en local: empuja y deja que el CI (Woodpecker) la corra en el servidor. ÚNICA excepción barata, y SIN Postgres: si tocas frontend, `tsc -b && vite build` compila en segundos y atrapa errores de tipos antes del CI; hazlo.

## No toques infra ajena

No edites Woodpecker (`server`/`agent` en `deploy/woodpecker/`): cortarías pipelines de otros agentes en curso. No edites archivos marcados como propiedad de otro agente o del orquestador; deja en tu informe el fragmento exacto que necesitas que cableen.
