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
- `componer.py` — composición de marca (logo + pleca + breaking), relocalizado de
  `breaking-express`.
- `marcas.json` — tokens de marca para la placa/composición.

Estos motores se PRESERVAN intactos como cimiento del futuro **Estudio de imagen** descrito
en `docs/diseno-estudio-imagen.md` (Fases 1-4: `api/imagenes.py` + UI propia). Mientras tanto,
la generación de imagen del producto sigue por el camino directo NEUTRO
`POST /api/media/generar` (`api/media.py` → `media.generar_imagen`), que NUNCA dependió de
skills. Tests: `consola/tests/motores/`.
