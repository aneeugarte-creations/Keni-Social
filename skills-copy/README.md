# skills-copy

Sistema de producción de copy para el equipo de redes de AMX, como **Agent Skills de Claude Code** + un **contexto editorial versionado**. Convierte una nota o un clip en copy publicable (voz de marca + tu voz + tropicalización mexicana + auto-verificación) en lugar de un borrador que haya que reescribir.

## Skills

| Skill | Para qué |
|---|---|
| **copy-desde-nota** | Nota o transcripción de clip → copy por plataforma (X, IG, FB, TikTok, YouTube) con auto-verificación. La principal. |
| **resumen-tendencia** | Tema/fuentes → brief interno: qué pasa + ángulo por marca + riesgos legales. |
| **nota-a-formato** | Nota cruda → normalizada a la voz de la casa (limpia giros españoles). Paso previo opcional. |

## Layout

```
.claude/skills/            # las skills (auto-descubiertas por Claude Code)
contexto-editorial/
  plataformas.md           # formato/largo por red
  tropicalizacion.md       # español de México (España → México)
  reglas-legales.md        # bandera/escudo, menores, datos + checklist de verificación
  marcas/                  # VOZ INSTITUCIONAL por marca (estable, la define el equipo)
  voces/                   # TU VOZ personal (la rellenas tú; se carga ENCIMA de la de marca)
ejemplos/                  # una nota y un clip para probar
```

**marcas vs voces:** la marca pone la línea editorial; tu voz pone el toque personal. La skill compone tu voz *sobre* la de marca *sobre* las reglas globales. Tú editas solo tu `voces/tu-nombre.md`.

## Uso

Trabaja con Claude Code en esta carpeta (o instala el conjunto como plugin). Luego:

```
> usa copy-desde-nota con ejemplos/clip-entrevista.md, marca claro-sports, voz tescu
```

Claude carga el contexto editorial, redacta una variante por plataforma y cierra con la auto-verificación (✅/⚠️/❌). Si tu voz está vacía, te avisa y usa solo la de marca. **Nada se publica: es dry-run, tú apruebas.**

## Personaliza tu voz (5 minutos)

1. Copia `contexto-editorial/voces/_plantilla.md` a `voces/tu-nombre.md`.
2. Rellena tus 3–5 rasgos, tus muletillas, lo que nunca haces y **pega 2 copies tuyos** que te enorgullezcan.
3. Vuelve a correr `copy-desde-nota` con `voz tu-nombre` y compara: ahora sale en tu voz.

(Si ya escribiste tu estilo en tu CLAUDE.md personal del Día 3, cópialo aquí: este es el archivo que la skill lee.)

## Integración con métricas (loop)

Si tienes el MCP `keni-metricas` conectado (ver `../mcp-metricas/`), `copy-desde-nota` consulta **antes de redactar** qué plataforma rinde más y qué piezas funcionaron mejor en esa marca (`metricas_resumen` + `mejores_piezas`), y **adapta ángulo, plataforma y tono** a lo que funciona — diciendo en una línea qué aprendió. Si el MCP no está conectado, lo dice y sigue sin métricas (no es obligatorio).
