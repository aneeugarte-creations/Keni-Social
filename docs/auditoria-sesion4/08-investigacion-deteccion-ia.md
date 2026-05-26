# Investigación A-05: Detección de vídeo generado con IA en `verifica-video`

> **Tipo:** Investigación de viabilidad · Issue #111  
> **Fecha:** 2026-05-25  
> **Investigador:** Claude Code (claude-sonnet-4-6)  
> **Recomendación final:** **HACER un subconjunto mínimo** — lectura pasiva de metadatos C2PA/EXIF y señales heurísticas de bajo riesgo, integrada como un paso adicional en el script `analiza-video.py` existente. No integrar APIs de detección de terceros en esta fase.

---

## 1. El problema: por qué importa para el equipo de redes

### El riesgo concreto

El equipo de AMX Contenido (UnoTV, Claro Sports, Nación Gamer…) cubre eventos en tiempo real: goles, accidentes, terremotos, protestas. En ese entorno, un clip que "llega por WhatsApp" o "está reventando en X" puede ser:

1. **Reciclado** — material viejo re-viralizado como si fuera de hoy. `verifica-video` ya detecta esto.
2. **Generado con IA** — un vídeo sintético fabricado desde cero por una herramienta como Sora, Veo, Kling o Runway, presentado como real.
3. **Deepfake / manipulado** — vídeo real con rostros o voces sustituidos (caso límite entre los dos anteriores).
4. **Upscaled / restaurado con IA** — vídeo real mejorado por IA; raramente engañoso pero técnicamente alterado.

Publicar contenido de tipo (2) o (3) como real es un **riesgo editorial grave**: desinformación, daño reputacional al medio y al piloto, y pérdida de confianza del equipo en la herramienta.

La diferencia con la recirculación es importante: un vídeo reciclado *ocurrió*, solo que antes. Un vídeo generado con IA *no ocurrió nunca*. Son fallos de verificación de distinta naturaleza.

### Qué se entiende por "vídeo generado con IA"

Para esta investigación, tres categorías con implicaciones diferentes:

| Categoría | Descripción | Riesgo editorial |
|---|---|---|
| **Full sintético** | 100% generado por modelo (Sora, Veo, Kling, Runway, Pika). Nunca ocurrió. | Muy alto |
| **Deepfake / face-swap** | Vídeo real con rostro o voz sustituidos. Ocurrió, pero el actor es falso. | Alto |
| **Upscaled / restaurado** | Vídeo real mejorado con IA (resolución, color). El hecho ocurrió. | Bajo-medio |

`verifica-video` hoy no distingue ninguna de estas tres del vídeo auténtico. La prioridad es la categoría (1): **vídeo full sintético que se hace pasar por noticia real**.

---

## 2. Enfoques posibles

### 2.1 Metadatos C2PA / Content Credentials

**Qué es.** C2PA (Coalition for Content Provenance and Authenticity, ISO/IEC 22144) es un estándar abierto que incrusta en el archivo un manifiesto firmado criptográficamente con la cadena de procedencia: qué herramienta lo generó, qué ediciones se aplicaron, y quién firmó cada paso. Si el vídeo viene de Veo, Sora, Runway u otro generador compatible, el manifiesto **lo declara explícitamente**.

**Cómo leerlo.** Hay dos herramientas sin dependencias de red:
- `exiftool` (ya en el entorno del usuario si tiene macOS + brew) — lee el bloque JUMBF/C2PA de archivos MP4/MOV/JPEG/WebP.
- `c2patool` (CLI oficial de la CAI, instalable con `brew install c2patool`) — salida JSON estructurada con el manifiesto completo.
- `c2pa-python` en PyPI — biblioteca Python que devuelve el manifiesto como dict.

**Fiabilidad.** Aquí está el límite más importante: C2PA solo detecta lo que el generador declara. Si el generador es compatible (Veo/Google, Adobe Firefly, Leica cameras, Microsoft Designer…) y el archivo no fue manipulado para borrar los metadatos, la detección es **determinista** — no hay falsos positivos ni negativos: o el manifiesto dice "generado por IA" o no dice nada. El problema es la cobertura:

- ✅ Detecta: Veo 2/3 (Google, compatible desde 2024), Adobe Firefly Video, contenido de plataformas que implementan C2PA, vídeos de cámaras modernas con C2PA (Leica M11-P).
- ❌ No detecta: Sora (OpenAI no implementa C2PA en vídeo a 2026-05), Kling, Runway, Pika, cualquier modelo local (Stable Video Diffusion, AnimateDiff), vídeo del que se borraron los metadatos con `ffmpeg -map_metadata -1` o `exiftool -all=`.

**Coste.** Cero. Local. Sin credenciales. Sin red.

**Falsos positivos.** Imposibles si solo se reporta lo que el manifiesto dice. El riesgo es el contrario: silencio cuando no hay manifiesto, que NO significa que el vídeo sea auténtico.

**Recomendación de implementación.** Leer C2PA es una señal pasiva de coste cero: si está presente, es información valiosa; si no está, se informa honestamente que la ausencia no es prueba de autenticidad. Integrar como paso 5.5 en `analiza-video.py` usando `exiftool -j` o `c2patool --json`.

---

### 2.2 Metadatos EXIF/XMP de software generador

**Qué es.** Independientemente de C2PA, algunos generadores dejan rastros en campos de metadatos estándar: `Software`, `CreatedBy`, `XMP:CreatorTool`, `Comment`, o el campo `Encoder` del contenedor MP4. Por ejemplo:

- Runway suele escribir en el campo `Software` su versión.
- Vídeos descargados de plataformas como TikTok o Instagram incluyen marcas del encoder (`vid:1080P_FHD` en TikTok) que en combinación con la ausencia de `creation_time` real son indicios.
- Herramientas de upscaling (Topaz Video AI, DaVinci Resolve Enhance) a veces dejan su huella en `Software`.

**Fiabilidad.** Baja-media como señal de IA generativa. Es una pista, no una prueba: cualquiera puede escribir cualquier cosa en esos campos, y muchos generadores no los rellenan. Sirve como señal adicional cuando está presente. Falsos positivos moderados (un editor de vídeo legítimo también escribe en `Software`).

**Coste.** Cero. Ya se usa `ffprobe` en `analiza-video.py`; añadir la lectura de `format_tags` adicionales es trivial.

**Recomendación.** Añadir la lectura de campos `Software`, `CreatedBy`, `comment`, `encoder` en el paso de metadatos existente y reportarlos en el JSON. Claude (la skill) los interpreta en contexto.

---

### 2.3 Watermarks invisibles — SynthID (Google DeepMind)

**Qué es.** SynthID incrusta en los píxeles una huella perceptualmente invisible que sobrevive a la compresión y re-encodificación. Aplicado a vídeos generados por Veo desde 2024. Google DeepMind anunció en Google I/O 2025 un portal de verificación (`SynthID Detector`) con carga de archivo.

**Disponibilidad para keni-social.** El detector oficial de SynthID es un portal web con acceso limitado (lista de espera a 2026-05). No hay API pública estable. El código de SynthID para texto está en open source, pero el detector de vídeo no.

**Coste.** Sin precio publicado. Requiere crear cuenta y estar en la lista de espera. No es local.

**Falsos positivos/negativos.** Google no publica métricas para vídeo. El sistema usa un enfoque bayesiano que devuelve tres estados: marcado / no marcado / incierto.

**Recomendación para keni-social.** Mencionar como enlace manual en el reporte (el usuario puede subir el vídeo al portal de SynthID si tiene acceso), pero NO integrar como paso automático: no hay API estable, no es local, requiere credenciales.

---

### 2.4 Heurísticas visuales y de artefactos

**Qué son.** Los vídeos generados con IA tienen patrones característicos que un modelo multimodal (o un ojo entrenado) puede detectar:

- **Blur de movimiento anormal** — demasiado uniforme o demasiado perfecto.
- **Fondos inconsistentes** — objetos que aparecen/desaparecen, distorsiones en bordes de personas.
- **Física irreal** — agua que fluye mal, fuego sin calor, multitudes con movimiento sincronizado.
- **Resolución alta + ruido periódico** — los modelos de difusión producen ruido de alta frecuencia no natural.
- **Audio fuera de sync** — en vídeos con voz, los labios no siempre sincronizan.
- **Sin metadatos de cámara** — ausencia completa de `Make`, `Model`, `FocalLength`, `ISO` en el contenedor.

**Limitación crítica.** Estas heurísticas las aplica Claude leyendo los fotogramas. Claude ya lee fotogramas en el paso 2 de `verifica-video` (detecta logos, timestamps, watermarks). Añadir instrucciones de detección de artefactos de IA en el SKILL.md es **gratis y sin código nuevo**. El problema: la generación de IA mejora continuamente. Lo que hoy parece artefacto, mañana no. **Esta es la señal más frágil y la que más falsos positivos generará** con modelos modernos de alta calidad.

**Coste.** Cero (es parte de la instrucción a Claude). Pero fiabilidad limitada contra modelos modernos.

---

### 2.5 APIs de detección de terceros

Las principales opciones del mercado a 2026-05:

| Servicio | Qué detecta | Precisión declarada | Coste | Dependencias |
|---|---|---|---|---|
| **Sightengine** | Vídeo full sintético (Veo, Sora, Runway, Pika, Kling, MidJourney) | ~91% en imágenes; vídeo no publicado | $0.002/op, mín. $29/mes | API key, red |
| **Reality Defender** | Deepfakes, video sintético | 90-95% declarado | Enterprise, precio no público | API key, red, registro |
| **Sensity AI** | Deepfakes, sintéticos | 95-98% declarado | Enterprise | API key, red, NDA |
| **Hive Moderation** | IA generativa (imagen + vídeo) | ~85-90% | $25/mes starter | API key, red |
| **Intel FakeCatcher** | Deepfakes (señales fisiológicas) | 96% declarado | Sin API pública estable | — |

**Problema fundamental con todas ellas:**

1. **Requieren clave API y red**: rompen el modelo de `verifica-video` que es local, gratis y sin credenciales pesadas.
2. **Suben el archivo o envían frames a un servidor externo**: conflicto con la política de privacidad del equipo AMX (material de clientes, vídeos sensibles antes de publicar).
3. **Las métricas de precisión son autodeclaradas o de benchmarks de imagen**: para vídeo real, los datos son escasos y los benchmarks están desactualizados respecto a los modelos más recientes (Veo 3, Kling 2.5, Runway Gen-4).
4. **Falsos positivos problemáticos para un equipo de redes**: un 5-10% de falsos positivos sobre vídeos reales haría que el equipo ignorara la señal, o peor, que descartara material legítimo.
5. **Adversarial**: cualquier equipo que sepa que se usa Sightengine puede re-encodificar el vídeo para evadir el detector. La carrera armamentista entre generadores y detectores favorece a los generadores.

**Recomendación para keni-social.** No integrar APIs de terceros en esta fase. La arquitectura actual es explícitamente "local por persona, sin credenciales pesadas". Mencionar las opciones disponibles en el reporte para que el humano decida si quiere consultarlas manualmente.

---

### 2.6 Marcas de agua visibles de plataformas generadoras

Algunos generadores añaden watermarks visibles en la versión gratuita:

- **Runway** (free tier): marca de agua en la esquina inferior derecha.
- **Pika** (free): marca de agua.
- **Kling** (free): marca de agua visible.
- **Sora** (discontinuado, era API): sin watermark visible por defecto.
- **Veo** (acceso limitado): sin watermark visible por defecto.

El OCR de `tesseract` ya corre sobre los fotogramas. **Buscar patrones de texto de watermarks conocidos** ("Runway", "Pika", "Made with Kling", etc.) en el texto del OCR es una extensión trivial de la señal de reciclaje existente.

**Fiabilidad.** Alta para versiones free de las herramientas (si el watermark no fue recortado). Inútil para versiones de pago o vídeos recortados.

**Coste.** Cero. Extensión del OCR ya existente.

---

## 3. Viabilidad en el contexto keni-social

### Arquitectura actual de `verifica-video`

```
analiza-video.py
  ├── [1] metadatos_url / metadatos_archivo  → yt-dlp / ffprobe
  ├── [2] descargar                          → yt-dlp (<=720p)
  ├── [3] extraer_fotogramas                 → ffmpeg
  ├── [4] ocr_fotogramas                     → tesseract
  ├── [5] enlaces_busqueda_inversa           → construye URLs, sin red
  └── [5] fact_check                         → Google API (opcional, si hay key)
```

La función `construir_senales()` clasifica las pistas en alto/medio/bajo/info y las añade al `reporte.json` que la skill (Claude) lee.

**Encaje arquitectónico de la detección de IA:**

- **Lectura C2PA/EXIF extendida**: encaja en el paso [1] (metadatos). `ffprobe -show_entries format_tags` ya corre; añadir lectura de `Software`, `Comment`, `encoder` es una línea de código. `exiftool -j` como paso opcional si está instalado añade la lectura de JUMBF/C2PA. Bajo riesgo.
- **Señales de watermark en OCR**: encaja en el paso [4]. La función `ocr_fotogramas` ya extrae texto. Añadir detección de patrones de watermarks de IA en `construir_senales()` es una extensión directa. Bajo riesgo.
- **Instrucciones a Claude en SKILL.md**: añadir un paso de "mira los fotogramas buscando artefactos de IA" en el paso 2 del SKILL.md. Sin código nuevo. Bajo riesgo.
- **APIs de terceros**: NO encaja. Rompe los principios de "local por persona" y "sin credenciales pesadas".
- **SynthID**: NO encaja. Sin API estable, no local.

### Principios de la arquitectura que se deben respetar

- **Solo lectura / dry-run**: cumplido — la detección es pasiva.
- **Local por persona**: cumplido si usamos exiftool y la extensión OCR.
- **Sin credenciales pesadas**: cumplido si evitamos APIs de terceros.
- **No subir material a ningún servicio**: cumplido — exiftool y ffprobe operan sobre el archivo local.
- **El humano decide**: el reporte añade señales, no veredictos automáticos de IA. La skill explica los límites.

---

## 4. Recomendación

### Hacer: subconjunto mínimo de bajo riesgo

**No** integrar APIs de detección de terceros. **Sí** añadir cuatro señales pasivas al script y una instrucción al SKILL.md:

#### Cambio A — Metadatos extendidos en `analiza-video.py` (paso 1)

En `metadatos_archivo` y como paso post-procesado de `metadatos_url`, leer campos adicionales con `ffprobe`:
- `format_tags.comment`, `format_tags.description`, `format_tags.software`, `format_tags.encoder`

Si alguno contiene el nombre de un generador conocido (Sora, Veo, Kling, Runway, Pika, MidJourney, HeyGen, etc.) → señal de nivel **alto** en `construir_senales()`.

Si `exiftool` está disponible (`shutil.which("exiftool")`), correrlo con `-j -XMP:all -C2PA:all` y leer el campo `c2pa:claim` o `XMP:CreatorTool`. Si contiene referencia a generador de IA → señal **alto**. Si contiene C2PA sin generador de IA → señal **info** (el archivo tiene cadena de procedencia verificable).

#### Cambio B — Watermarks de IA en OCR (paso 4)

En `construir_senales()`, buscar en `ocr["texto"]` patrones de watermarks de generadores conocidos:

```python
WATERMARKS_IA = [
    "runway", "runwayml", "pika", "made with kling", "kling ai",
    "created with ai", "generated by ai", "sora", "midjourney",
    "stable diffusion", "generated with veo",
]
```

Si se encuentra alguno → señal **alto** con el texto hallado.

#### Cambio C — Ausencia de metadatos de cámara (heurística de riesgo bajo)

Si los metadatos no contienen `Make`, `Model`, `FocalLength` ni ningún campo EXIF de dispositivo físico → señal **bajo** / info: "Sin metadatos de cámara física. Puede ser vídeo generado con IA, grabado en pantalla, o un archivo del que se eliminaron los metadatos."

#### Cambio D — Instrucción adicional en SKILL.md (sin código nuevo)

Añadir en el paso 2 de `verifica-video/SKILL.md` una instrucción explícita: al leer los fotogramas, buscar también artefactos típicos de IA generativa (fondos inconsistentes, física irreal, blur excesivamente uniforme, ausencia de ruido de sensor, sincronización labial deficiente). Reportarlo en la auto-verificación con ⚠️ como señal heurística no concluyente.

### Plan de implementación

1. Rama `wave8/investigacion-ia` desde `origin/main`.
2. Modificar `skills-copy/.claude/skills/verifica-video/analiza-video.py`:
   - Función `leer_metadatos_extendidos(meta, video_path)` que lee campos adicionales con `ffprobe` y, si está disponible, `exiftool`.
   - Ampliar `construir_senales()` con los patrones de watermarks en OCR y la lógica de metadatos extendidos.
3. Modificar `skills-copy/.claude/skills/verifica-video/SKILL.md`:
   - Añadir el paso de artefactos de IA en el paso 2.
   - Actualizar la sección "Qué NO hace esta skill" para ser honesta sobre los límites de la detección.
4. Chequeos estáticos (`python3 skills-copy/evals/test_static.py`) en verde.
5. Commit, merge fast-forward, push.

**Tiempo estimado:** 2-3 horas de implementación.

---

## 5. Riesgos y límites honestos

### La detección de IA es intrínsecamente poco fiable. Siempre.

Esto no es una advertencia burocrática: es el estado del arte. Los modelos de generación de vídeo mejoran más rápido que los detectores. Lo que hoy es un artefacto detectable (blur periódico de Sora 1) ya no lo es en Sora 2 o Veo 3. Un benchmark publicado hoy es obsoleto en seis meses.

**Tabla de honestidad:**

| Señal | Fiabilidad real | Falsos positivos | Falsos negativos |
|---|---|---|---|
| Manifiesto C2PA presente con marca de IA | Alta (determinista) | Imposibles (si el manifiesto es válido) | Muy altos (la mayoría de generadores no implementan C2PA) |
| Metadatos EXIF/Software con nombre de generador | Media | Bajos (si el nombre aparece, es indicativo) | Altos (la mayoría no los rellenan) |
| Watermark visible en OCR | Alta si está presente | Muy bajos | Altos (versiones de pago no tienen watermark) |
| Ausencia de metadatos de cámara | Baja | Altos (vídeos de pantalla, WhatsApp, procesados) | Medios (generadores que añaden metadatos falsos) |
| Artefactos visuales (heurística Claude) | Media-baja contra modelos modernos | Medios (vídeo UHD puede confundir) | Muy altos contra Veo 3 / Kling 2.5 calidad alta |
| APIs de terceros (Sightengine, Reality Defender) | 85-95% en benchmarks | 5-15% en campo real | Variables, peores con modelos nuevos |

### Lo que el equipo DEBE entender

1. **Un reporte limpio NO confirma que el vídeo es auténtico.** La ausencia de señales de IA solo significa que no encontramos señales de IA con las herramientas disponibles. El humano sigue siendo el último filtro.

2. **Las señales de IA en el reporte son INDICIOS, no veredictos.** Un vídeo puede tener el `Software` de Runway en sus metadatos porque alguien usó Runway para editar una grabación real. Un vídeo puede tener el watermark "Pika" porque alguien lo añadió manualmente.

3. **El mejor detector de IA a corto plazo sigue siendo el criterio editorial**: ¿tiene sentido que exista este vídeo? ¿Dónde está el fotógrafo/camarógrafo que lo grabó? ¿Hay otras fuentes? `verifica-video` es una herramienta de primer filtro, no de verdad final.

4. **La cadena de evidencia importa**: C2PA es la única señal con base criptográfica. El resto son heurísticas probabilísticas. Comunicar esto al equipo evita que confíen en el resultado como sentencia.

### Riesgos específicos de la implementación propuesta

- **`exiftool` no está en el entorno del usuario**: el paso C2PA falla silenciosamente (mismo patrón que ffmpeg/tesseract hoy — informa y continúa sin bloquearse).
- **Lista de watermarks desactualizada**: los generadores cambian sus marcas de agua. La lista necesita mantenimiento periódico.
- **False sense of security**: el cambio más peligroso es que el equipo interprete "sin señales de IA" como "vídeo auténtico confirmado". El SKILL.md debe ser explícito en esto.

---

## 6. Decisión sobre el issue #111

La investigación concluye que:

- **No es viable** añadir detección robusta de IA generativa (>90% precisión, sin falsos positivos materiales) sin APIs de terceros de pago y con conexión a red.
- **Sí es viable y útil** añadir señales pasivas (C2PA, metadatos extendidos, watermarks en OCR, instrucción de artefactos) que mejoran la información disponible sin romper los principios de arquitectura ni introducir costes.
- **El subconjunto recomendado** es de bajo riesgo técnico, no requiere dependencias nuevas obligatorias (exiftool es opcional), y es honesto con sus límites.

El issue queda como **implementación pendiente** (el subconjunto propuesto) o **cerrado por diseño** (si el equipo decide que las señales pasivas no justifican el esfuerzo y prefieren delegar en el criterio editorial). La recomendación es implementar el subconjunto.

---

*Investigación completada el 2026-05-25. No ejecuta el modelo ni APIs en vivo; basada en análisis de código + investigación de fuentes públicas.*
