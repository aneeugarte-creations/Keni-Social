# motores/estudio_imagen

Herramientas del **Estudio de imagen** relocalizadas fuera de `skills-copy/` (que se
retiró junto con el sistema de skills), siguiendo el patrón de `motores/verifica_video/`:
scripts CLI invocables por subproceso con el python de la consola, sin depender del motor
de skills ni de `claude`.

- `editar.py`   — operaciones DETERMINISTAS (Pillow): recortar/redimensionar/comprimir/
  extender fondo/placa. Lee `marcas.json` (hermano, relocalizado de `breaking-express`).
- `expandir.py` — outpainting GENERATIVO fiel (re-compone el sujeto intacto) vía OpenRouter.
- `generar.py`  — adaptador GENERATIVO (ilustración/fondo) vía OpenRouter. Conserva
  `construir_prompt` (estilo por marca + aspecto por formato).
- `render_node/` — composición de la PLANTILLA de marca por SPEC de capas (Node + Skia,
  `@napi-rs/canvas`): el ÚNICO motor de placas (lo diseñado en el editor = lo que sale). Lee el
  spec de `plantillas_marca` y las fuentes embebidas de `fuentes/`. (Sustituyó al viejo
  `componer.py` de Pillow, retirado.)
- `fuentes/` — tipografías embebidas (SIL OFL) del catálogo de la plantilla.
- `marcas.json` — tokens de marca (semilla del spec por defecto y geometría de formatos).

Estos motores se PRESERVAN intactos como cimiento del futuro **Estudio de imagen** descrito
en `docs/diseno-estudio-imagen.md` (Fases 1-4: `api/imagenes.py` + UI propia). Mientras tanto,
la generación de imagen del producto sigue por el camino directo NEUTRO
`POST /api/media/generar` (`api/media.py` → `media.generar_imagen`), que NUNCA dependió de
skills. Tests: `consola/tests/motores/`.
