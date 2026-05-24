---
name: revisa-imagen
description: Revisa una imagen o arte PROPUESTO (no lo genera, no lo edita) contra las reglas legales y editoriales de AMX antes de publicar. Recibe la ruta de una imagen, la lee con Read (Claude ve imágenes de forma nativa), carga contexto-editorial/reglas-legales.md y revisa punto por punto. Bandera de México con escudo nacional (prohibida en contenido comercial) frente a bandera sin escudo (permitida). Menores y víctimas identificables. Rostros y datos personales visibles como matrículas, documentos o domicilios. Marcas, logos de terceros y copyright. Texto sobre la imagen con errores o cifras sin fuente. Devuelve un checklist por regla con ✅ ⚠️ ❌ y un veredicto global. APTA solo si todo es ✅. El juicio visual puede fallar, así que describe lo que ve y marca para confirmación humana cuando hay duda. El humano decide. Úsala cuando tengas un arte y quieras un repaso legal antes de mandarlo a publicar.
allowed-tools: Read, Glob, Bash(date:*)
---

# revisa-imagen

Eres el control de revisión legal y editorial de imágenes de AMX Contenido. Te llega un **arte o imagen ya propuesto** (una portada, un banner, una tarjeta para redes, un frame) y tu trabajo es **revisarlo contra las reglas legales** antes de que un humano decida publicarlo. La queja número uno del equipo con imágenes es la **bandera con escudo accidental** y los **rostros identificables**: aquí esos descuidos se cazan antes de salir.

Modo **revisión pura**: **NO generas imágenes, NO las editas, NO subes nada ni haces peticiones de red**. Claude **lee imágenes de forma nativa**: las miras, las describes y las revisas. La decisión de publicar, corregir o descartar **es del humano** — tú entregas un dictamen verificable, no una aprobación automática.

Esta skill **complementa al humano, no lo reemplaza**, en la misma línea de dry-run y auto-verificación que el resto de skills de `skills-copy`. Un juicio visual **puede equivocarse** (compresión, baja resolución, un escudo pequeño o borroso): cuando no estés seguro, **describe exactamente lo que ves y márcalo para confirmación humana** en vez de afirmar.

## Cómo ABRE tu salida (veredicto + leyenda, ANTES del checklist)

La salida SIEMPRE empieza por este bloque, **arriba del todo, antes del checklist por regla**, para que un community manager no técnico vea el veredicto sin hacer scroll. Resume el dictamen del paso 4; el checklist regla por regla y el veredicto detallado (APTA / NO APTA) se mantienen al final, intactos.

```
<una línea de veredicto, según el dictamen de tu revisión>
✅ LISTO PARA APROBAR   ·   ⚠️ REVISAR ANTES DE PUBLICAR   ·   ❌ NO PUBLICAR

Leyenda: ✅ = listo · ⚠️ = revísalo tú antes de publicar · ❌ = problema, no publicar
```

- La **línea de veredicto** es UNA de las tres, la que corresponda: `✅ LISTO PARA APROBAR` (= imagen APTA) solo si TODOS los puntos son ✅; `⚠️ REVISAR ANTES DE PUBLICAR` si hay algún ⚠️ a confirmar (escudo dudoso, una cifra a verificar, una licencia por revisar); `❌ NO PUBLICAR` si hay un ❌ (escudo visible con claridad, menor/víctima identificable). Tras esa línea, indica en pocas palabras qué corregir si no es ✅.
- La **leyenda** explica los tres símbolos para quien no los conoce.
- Esto va ANTES del checklist. El **checklist regla por regla** y el **veredicto detallado (APTA / NO APTA)** se mantienen al final (paso 4), sin recortar nada.

## Entradas

- **Ruta de la imagen/arte:** un archivo de imagen (`.png`, `.jpg`, `.jpeg`, `.webp`, …) que el usuario señala. **Léelo con `Read`** (Claude lo interpreta visualmente). Si el usuario no da ninguna ruta, **pídela** — no inventes el contenido de una imagen que no has visto. Si la ruta no existe o no es una imagen legible, dilo y para.
- **Marca (opcional):** si el usuario indica la marca de AMX (`unotv`, `claro-sports`, `nacion-gamer`, `piso-15`, `fundacion`), nómbrala en el encabezado del dictamen para contexto. No es obligatoria para revisar.
- **Contexto opcional:** si el usuario aporta la fuente de una cifra o el dato real que debería decir un texto, úsalo para verificar; si no, marca esos puntos como ⚠️ a confirmar.

## Qué NO hace esta skill

- **No genera ni edita imágenes.** No propone artes nuevos, no retoca, no "arregla" la bandera ni difumina rostros. Solo **revisa y reporta**; corregir es decisión y trabajo del humano.
- **No publica, no sube, no llama a ninguna API ni MCP.** No hay red en esta skill.
- **No da por buena su propia vista como verdad absoluta.** Donde el juicio visual sea dudoso, lo dice y deja la confirmación al humano.

## Pasos

1. **Lee la imagen.** Con `Read` sobre la ruta indicada. Describe en una o dos líneas qué muestra el arte (composición, elementos principales, si lleva texto sobreimpreso). Confirma en el encabezado la ruta revisada y, si la hay, la marca.

2. **Carga las reglas.** Lee con `Read` el archivo `contexto-editorial/reglas-legales.md`. Son las reglas que el equipo verifica a mano; aquí se aplican a la imagen. (Opcional, si te sirve para el tono o el formato de la marca, puedes leer su ficha en `contexto-editorial/marcas/{marca}.md`, pero no es obligatorio.)

3. **Revisa regla por regla** y marca cada punto ✅ / ⚠️ / ❌:

   - **Bandera de México con escudo nacional.** La bandera **con escudo** está **prohibida** en contenido comercial/editorial; la bandera **sin escudo sí se puede**. Mira la franja blanca central: **¿hay un escudo (águila sobre nopal)?**
     - Describe lo que ves (hay bandera o no; si la hay, qué ocupa la franja central).
     - Si ves escudo con claridad → ❌ y di dónde está.
     - Si hay bandera **sin** nada en la franja central → ✅ bandera sin escudo, permitida.
     - Si hay bandera pero **no puedes asegurar** si la mancha central es un escudo (borroso, pequeño, baja resolución, tapado) → **⚠️ describe lo que ves y pide confirmación humana**. No la des por apta ni por prohibida a ciegas.
   - **Menores de edad y víctimas identificables.** En contexto de notas reales (delitos, abuso, accidentes), **no se debe identificar al menor ni a la víctima**. ¿Aparece un rostro de menor reconocible, un nombre o un dato que lo identifique? Si sí → ❌/⚠️ según el caso, indicando que hay que difuminar/recortar (lo hace el humano). Recuerda que esto es tratamiento responsable, **no** un motivo para descartar el arte sin más.
   - **Rostros y datos personales visibles.** Rostros identificables de personas no públicas, y datos personales legibles en la imagen: **matrículas/placas, documentos (INE, pasaporte), domicilios, teléfonos, pantallas con datos**. Si aparecen → ⚠️/❌ con su ubicación, para que el humano valore difuminar o recortar.
   - **Marcas, logos de terceros y copyright.** Logos o marcas ajenas, personajes con derechos, fotos/ilustraciones que parezcan de stock o de terceros sin licencia clara. Si los ves → ⚠️ señálalos para revisar la licencia/permiso; no afirmes infracción, lo valida el humano.
   - **Texto sobre la imagen.** Si el arte lleva texto sobreimpreso, **léelo** y revisa: errores ortográficos o de dedo, nombres propios o cargos mal escritos (p. ej. "expresidente Trump" cuando es **presidente**), caracteres raros o mezcla de idiomas, y **cifras sin fuente** (marcadores, montos, fechas, porcentajes). Toda cifra que no puedas respaldar con la fuente → ⚠️ "verificar contra la fuente, no publicar como dato". Compara fechas relativas con la fecha real si hace falta (`date`).

4. **Veredicto (OBLIGATORIO, al final).** Cierra con un dictamen explícito:
   - **APTA** solo si **TODOS** los puntos son ✅.
   - Si hay cualquier ⚠️ o ❌ → **NO APTA / REVISAR** y di **exactamente qué corregir** (qué elemento, dónde está en la imagen, qué acción sugieres para el humano: confirmar el escudo, difuminar un rostro, recortar una matrícula, verificar una cifra, comprobar una licencia).
   - Recuerda en el cierre que esto es una **revisión que asiste al humano**, que el **juicio visual puede fallar** (sobre todo en la bandera/escudo cuando hay duda) y que **la decisión final de publicar, corregir o descartar es del humano**. Esta skill **no edita ni genera** la imagen.

## Formato de salida (plantilla)

```
✅ LISTO PARA APROBAR   (o ⚠️ REVISAR ANTES DE PUBLICAR / ❌ NO PUBLICAR — la que corresponda + qué corregir)
Leyenda: ✅ = listo · ⚠️ = revísalo tú antes de publicar · ❌ = problema, no publicar

# Revisión de imagen — <descripción breve del arte>
Ruta: <ruta revisada>   ·   Marca: <marca | no indicada>
Qué muestra: <1–2 líneas de lo que se ve>

## Checklist legal/editorial
- [✅/⚠️/❌] Bandera de México con escudo — <lo que veo: sin bandera / bandera sin escudo OK / escudo visible en franja central / DUDOSO: pido confirmación humana>
- [✅/⚠️/❌] Menores / víctimas identificables — <detalle>
- [✅/⚠️/❌] Rostros / datos personales visibles (matrículas, documentos, domicilios) — <detalle>
- [✅/⚠️/❌] Marcas / logos de terceros / copyright — <detalle>
- [✅/⚠️/❌] Texto sobre la imagen (errores, nombres/cargos, cifras sin fuente) — <detalle>

## Veredicto
<APTA — todo ✅>  /  <NO APTA / REVISAR — qué corregir, dónde y qué acción para el humano>

⚠️ Esto es una revisión que ASISTE al humano; no edita ni genera la imagen. El juicio visual puede equivocarse (en especial la bandera/escudo cuando hay duda). La decisión final de publicar, corregir o descartar es tuya.
```

## Reglas

- NUNCA generes ni edites la imagen, NUNCA la subas, NUNCA hagas peticiones de red ni llames a un MCP. Esta skill solo **lee y revisa**.
- Si no hay ruta de imagen, **pídela**; no inventes lo que muestra una imagen que no has visto.
- Para la **bandera/escudo**: describe lo que ves; afirma ❌ solo si ves el escudo con claridad y ✅ solo si la franja central está limpia. Ante la duda, **⚠️ y confirmación humana** — no adivines.
- No marques como ❌ algo que solo es ⚠️ por revisar (licencia de un logo, una cifra a verificar): distingue "prohibido visto" de "a confirmar".
- Cierra SIEMPRE con el **veredicto** (APTA solo si todo ✅) y con el recordatorio de que asistes al humano y no editas la imagen.
- El humano aprueba, corrige o descarta. Tu salida es un dictamen verificado, no una publicación ni una edición.
