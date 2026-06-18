---
titulo: "Review · checklist antes de promover"
descripcion: "Checklist final antes de promover a main en keni-social: diff limpio, tests propagados, build de frontend si toca, y el flujo worktree → promover-main."
tipo: editorial
clase: desarrollo
marcas: []
pipelines: []
creado: 2026-06-18T00:00:00+00:00
actualizado: 2026-06-18T00:00:00+00:00
---

# Review · antes de promover a main

Última puerta antes de que el cambio llegue a `main`. En auto-desarrollo, la promoción real a `main` SIEMPRE requiere checkpoint humano: no hagas push directo a `main` por tu cuenta.

## Checklist de diff

- ¿El diff resuelve SOLO lo pedido? Sin archivos colaterales, sin refactors oportunistas, sin debug suelto.
- ¿Comentarios limpios? Describen el código de hoy, sin historial de bugs. El porqué del arreglo va en el mensaje de commit.
- ¿Sin secretos ni credenciales en el diff? La credencial gh vive en `/data/gh`, los tokens viajan por env/`*_FILE`, nunca en el código.
- ¿No tocaste `webapp/` (GITIGNORED), ni Woodpecker, ni archivos propiedad de otro agente/orquestador?

## Checklist de seams y tests

- Cada seam que tocaste tiene su OTRO lado propagado en el mismo commit (fachada de reexport: import + `__all__`; router: declarado/enrutado; forma observable: tests actualizados).
- `grep` de consumidores hecho para toda firma de API, forma de respuesta, esquema de BD o contrato de fronteras que cambiaste.
- Tests de comportamiento actualizados en el mismo commit. No dejes rojos huérfanos para el CI.

## Frontend

- Si tocaste `consola/frontend/src/`, corre `tsc -b && vite build` (segundos, sin Postgres) y confirma que compila antes de promover.

## Flujo git (worktree → promover-main)

- Trabaja SIEMPRE en tu propio worktree+rama; nunca sobre el checkout de `main`. No publiques ramas de feature en `origin` (solo `main` vive remoto).
- Commit con mensaje claro (el PORQUÉ del cambio va aquí). Cierra el mensaje con la línea Co-Authored-By que pida el repo.
- Promover: `bash scripts/promover-main.sh` desde tu worktree (hace fetch+rebase+push e imprime la limpieza; NO borra nada por ti). Borra worktree+rama solo tras ver «push OK».
- Si te rechaza el push: `git fetch && git rebase origin/main` y reintenta.

## Después de promover

- Valida que el pipeline de CI salga VERDE en el servidor (Woodpecker, `ci-social.kenitech.io`). La auto-cancelación por push está OFF en `main`: cada commit corre su pipeline entero y deja veredicto real.
- NO persigas el CI con una ráfaga de fix-commits. Un rojo casi siempre es comportamiento real sin propagar: arréglalo EN LOTE, idealmente un commit por foto. Si lo que cae es un flake ajeno, sigue; ya lo arreglará otro agente o el humano en una pasada dedicada.
