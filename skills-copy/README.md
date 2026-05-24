# skills-copy

Sistema de producción de copy para el equipo de redes de AMX, como **Agent Skills de Claude Code** + un **contexto editorial versionado**. Convierte una nota o un clip en copy publicable (voz de marca + tu voz + tropicalización mexicana + auto-verificación) en lugar de un borrador que haya que reescribir.

## Skills

| Skill | Para qué |
|---|---|
| **copy-desde-nota** | Nota o transcripción de clip → copy por plataforma (X, IG, FB, TikTok, YouTube) con auto-verificación. La principal. |
| **clip-a-copy** | **Video/audio** (entrevista, declaración, podcast) → copy por plataforma + **citas con marca de tiempo** para cortar el clip. Transcribe en **local** (whisper.cpp, el audio no sale de la máquina). |
| **resumen-tendencia** | Tema/fuentes → brief interno: qué pasa + ángulo por marca + riesgos legales. |
| **nota-a-formato** | Nota cruda → normalizada a la voz de la casa (limpia giros españoles). Paso previo opcional. |
| **publica-preview** | Copy ya aprobado → pre-vuelo final en **dry-run**: muestra EXACTO qué se publicaría por plataforma (texto, conteo, hashtags, hilo/carrusel, media referenciada) + avisos + checklist humana. **No publica.** |

## Layout

```
.claude/skills/            # las skills (auto-descubiertas por Claude Code)
contexto-editorial/
  plataformas.md           # formato/largo por red
  tropicalizacion.md       # español de México (España → México)
  reglas-legales.md        # bandera/escudo, menores, datos + checklist de verificación
  marcas/                  # VOZ INSTITUCIONAL por marca (estable, la define el equipo)
  voces/                   # voces personales versionadas (fallback). Tu voz vive mejor en ~/.config/keni-social/voces/ (sobrevive a updates)
ejemplos/                  # una nota y un clip para probar
```

**marcas vs voces:** la marca pone la línea editorial; tu voz pone el toque personal. La skill compone tu voz *sobre* la de marca *sobre* las reglas globales. Tú editas solo tu `voces/tu-nombre.md`.

## Uso

Trabaja con Claude Code en esta carpeta (o instala el conjunto como plugin). Luego:

```
> usa copy-desde-nota con ejemplos/clip-entrevista.md, marca claro-sports, voz tescu
```

Claude carga el contexto editorial, redacta una variante por plataforma y cierra con la auto-verificación (✅/⚠️/❌). Si tu voz está vacía, te avisa y usa solo la de marca. **Nada se publica: es dry-run, tú apruebas.**

Partiendo de un **video o audio** (en vez de una nota escrita):

```
> usa clip-a-copy con /ruta/al/video.mp4 para claro-sports
```

Transcribe el archivo **en local** (no sube nada), saca las mejores citas con su marca de tiempo para cortar el clip, y redacta el copy. Requisitos de transcripción (whisper.cpp + ffmpeg + modelo) en `../docs/despliegue-local.md`. Para probar sin un video real: `cd ejemplos && bash generar-clip-prueba.sh`. Como la transcripción automática **falla en nombres y cifras**, la skill los marca como "verificar contra el audio" — saber cuándo creerle a la IA es parte del entregable.

Cuando el copy ya está aprobado y quieres el **último vistazo antes de publicar**:

```
> usa publica-preview con este copy para X e Instagram, media reel-jugada.mp4
```

Muestra plataforma por plataforma **exactamente qué se publicaría** (texto final, conteo con `contar.py`, hashtags, desglose de hilo/carrusel y qué media acompaña — solo referenciada, nunca subida), avisos por red (Instagram exige media, un enlace en X cuesta caracteres extra, último repaso legal) y cierra con una **checklist** que marcas tú. Es dry-run puro: **nada se publica; la publicación real llega en una fase futura.**

## Personaliza tu voz (5 minutos)

1. Copia `contexto-editorial/voces/_plantilla.md` a **`~/.config/keni-social/voces/tu-nombre.md`** (ubicación recomendada, ver abajo).
2. Rellena tus 3–5 rasgos, tus muletillas, lo que nunca haces y **pega 2 copies tuyos** que te enorgullezcan.
3. Vuelve a correr `copy-desde-nota` con `voz tu-nombre` y compara: ahora sale en tu voz.

(Si ya escribiste tu estilo en tu CLAUDE.md personal del Día 3, cópialo aquí: este es el archivo que la skill lee.)

### Dónde guardar tu voz (sobrevive a las actualizaciones)

Las skills buscan tu voz `tu-nombre.md` en este orden y usan **la primera que exista**:

1. **`~/.config/keni-social/voces/tu-nombre.md`** — fuera del repo. **Recomendado**: tu voz personal NO se pierde ni se sobrescribe cuando el plugin/repo se actualiza.
2. `contexto-editorial/voces/tu-nombre.md` — dentro del repo (fallback). Útil para una voz compartida del equipo, pero una actualización puede sobrescribirla.

Como mínimo, crea la carpeta una vez: `mkdir -p ~/.config/keni-social/voces`.

## Integración con métricas (loop)

Si tienes el MCP `keni-metricas` conectado (ver `../mcp-metricas/`), `copy-desde-nota` consulta **antes de redactar** qué plataforma rinde más y qué piezas funcionaron mejor en esa marca (`metricas_resumen` + `mejores_piezas`), y **adapta ángulo, plataforma y tono** a lo que funciona — diciendo en una línea qué aprendió. Si el MCP no está conectado, lo dice y sigue sin métricas (no es obligatorio).
