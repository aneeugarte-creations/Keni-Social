# motores/estudio_imagen

Herramientas del **Estudio de imagen**, siguiendo el patrón de `motores/verifica_video/`:
scripts CLI invocables por subproceso con el python de la consola, sin depender de `claude`.

- `editar.py`   — operaciones DETERMINISTAS (Pillow): recortar/redimensionar/comprimir/
  extender fondo/placa. Lee `marcas.json` (hermano).
- `expandir.py` — outpainting GENERATIVO fiel (re-compone el sujeto intacto) vía OpenRouter.
- `generar.py`  — adaptador GENERATIVO (ilustración/fondo) vía OpenRouter. Conserva
  `construir_prompt` (estilo por marca + aspecto por formato).
- `render_node/` — composición de la PLANTILLA de marca por SPEC de capas (Node + Skia,
  `@napi-rs/canvas`): el ÚNICO motor de placas (lo diseñado en el editor = lo que sale). Lee el
  spec de `plantillas_marca` y las fuentes embebidas de `fuentes/`. (Sustituyó al viejo
  `componer.py` de Pillow, retirado.)
- `fuentes/` — tipografías embebidas (SIL OFL) del catálogo de la plantilla.
- `marcas.json` — tokens de marca (semilla del spec por defecto y geometría de formatos).

Estos motores son el cimiento del **Estudio de imagen**, ya EN PRODUCCIÓN: la API
`api/imagenes.py` (`POST /api/imagenes/{generar,editar,expandir,retocar,componer,revisar,set}`
+ `GET /api/imagenes/matriz`) orquesta los jobs sobre `dominio/estudio_imagen.py`, y la UI los
consume desde `components/media/EditorImagen.tsx` y `editor/PanelIA.tsx`. El camino directo
NEUTRO `POST /api/media/generar` (`api/media.py`) sigue existiendo para generación rápida sin
marca. Diseño y fases en `docs/diseno-estudio-imagen.md`. Tests: `consola/tests/motores/`.
