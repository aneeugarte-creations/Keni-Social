# Cierre de deuda residual: H6 (etapa 3) y N13

> **Tipo:** Refactor de cierre · sin issue dedicado
> **Fecha:** 2026-05-26
> **Autor:** Claude Code (claude-opus-4-7, 1M)
> **Estado:** ✅ Cerrado · merge fast-forward a `main` (SHA `d5f7c31`)

Cierra los dos puntos de deuda residual que quedaron tras las dos primeras etapas del
hallazgo **H6** (adelgazar `api/skills.py`) y el acoplamiento **N13** (dominio/CLI que
importaban de `api/`).

---

## Punto 1 — H6, 3ª etapa: separar generación/ejecución de `api/skills.py`

`api/skills.py` había quedado en **773 líneas** tras las dos primeras etapas, todavía por
encima del umbral. Esta etapa saca los **handlers HTTP de generación/ejecución** a un
módulo nuevo y deja `skills.py` como **fachada de reexports**.

**Qué se movió:**

- Handlers HTTP → **`api/skills_generacion_api.py`** (módulo nuevo, con su propia `RUTAS`,
  auto-descubierta por `api.descubrir`; **`app.py` no se toca**):
  `opciones`, `ejecutar`, `ejecutar_archivo`, `historial`, `historial_detalle`,
  `historial_guardar`, más sus helpers privados de HTTP (validación de campos, subida
  segura de archivo, límites de tamaño, saneado de extensión, preview, etc.).
- Orquestación de lanzamiento y resolución de cwd → **`dominio/skills.py`**:
  `lanzar_generacion_copy`, `lanzar_generacion_skill`, `_lanzar_con_procesar`,
  `etiqueta_generacion`, `nombre_skill`, `cwd_skills`, `cwd_ejecucion_skills`.

**Qué quedó en `api/skills.py`** (124 líneas): la **fachada estable** de reexports que
otros módulos consumen como `skills.<símbolo>` (allowlists de marcas/skills, tope de
texto, parseo del stream, prompts, post-procesado, cwd y lanzamiento), para no romper a
`api.rss`, `api.hashtags`, `api.termometro`, `api.agentes` ni los tests, que dependen de
esa API pública. **URLs y contratos HTTP idénticos.**

| Archivo | Antes | Después |
|---|---|---|
| `api/skills.py` | 773 L | **124 L** |
| `api/skills_generacion_api.py` | — | 573 L (nuevo) |
| `dominio/skills.py` | 298 L | 466 L |

## Punto 2 — N13: cortar `from .api import skills` en dominio/CLI

Dos módulos de dominio/CLI importaban de la capa `api/`:

- `termometro_cli.py` → usaba `api_skills._arg_presupuesto`, `normalizar_redes`,
  `_cwd_ejecucion_skills`, `parsear_resultado_json`, `SkillError`,
  `construir_procesar_documento`. Ahora resuelve todo desde `dominio.stream` y
  `dominio.skills`.
- `skills_catalogo.dir_skills()` → usaba `api_skills._cwd_skills`. Ahora importa
  `dominio.skills.cwd_skills` de forma **perezosa** (dentro de la función) para no crear
  ciclo, ya que `dominio.skills` importa `skills_catalogo` a nivel de módulo.

Ningún módulo de `dominio/` ni el CLI importa ya de `api/`.

**Nota de alcance:** `termometro_cli.py` mantiene un `from .api import rss`
**preexistente** (helpers `leer_items_fuente` / `item_pasa_filtros`). No formaba parte de
N13 (que nombraba solo el import de `skills`) y moverlo obligaría a tocar `api/rss.py`,
fuera del alcance de esta tanda. Queda anotado como deuda menor para una tanda futura.

---

## Verificación

Mirror de CI local (venv aislado) en verde sobre el árbol ya rebaseado a `origin/main`:

- `ruff check .` (consola) → OK
- `pytest -q` (consola) → OK
- `pytest -q` (mcp-metricas, sanity) → OK
- Auto-descubrimiento: las 6 rutas `/api/skills{,/ejecutar,/ejecutar-archivo,/historial,
  /historial/{id},/historial/{id}/guardar}` se montan desde el módulo nuevo, sin colisión
  de `(path, method)`.
