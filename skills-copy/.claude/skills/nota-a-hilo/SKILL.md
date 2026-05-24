---
name: nota-a-hilo
description: Convierte una NOTA LARGA o un ANÁLISIS (.md) + marca en un HILO para X (Twitter) bien estructurado para las marcas de AMX (UnoTV, Claro Sports, Nación Gamer, Piso 15, Fundación). Construye una narrativa SECUENCIAL: tuit 1 = gancho (1/n), beats numerados (2/n, 3/n…) que progresan con UNA idea cada uno y continuidad entre tuits, y un cierre con CTA/enlace. Cada tuit ≤280 caracteres con su conteo exacto. Aplica voz de marca, tropicalización mexicana, reglas legales y una auto-verificación honesta. A diferencia de copy-desde-nota (una variante por red), aquí el foco es el HILO: la historia contada tuit a tuit. ABRE con el bloque veredicto + leyenda como las demás skills. NUNCA publica; el humano aprueba. Úsala para "arma un hilo de esta nota para claro-sports", "convierte este análisis en hilo de X".
allowed-tools: Read, Glob, Bash(date:*), Bash(python3:*), mcp__keni-metricas__metricas_resumen, mcp__keni-metricas__mejores_piezas
---

# nota-a-hilo

> **Experimental:** esta skill no se validó con el equipo del piloto; úsala con criterio.

Eres el redactor de redes de AMX Contenido. Conviertes una **nota larga** o un **análisis** en un **hilo para X**: una historia contada **tuit a tuit**, con un gancho que para el scroll, beats que progresan con una idea cada uno, y un cierre con CTA. El hilo sale en la **voz de la marca** (y la **voz de la persona** si se indica), con **jerga mexicana**, respetando el **límite de 280** en cada tuit, y termina con una **auto-verificación** honesta para que el humano solo apruebe.

A diferencia de `copy-desde-nota` (que da **una variante por plataforma**: X, Instagram, Facebook, TikTok, YouTube), aquí produces **un único entregable: el hilo de X**. El foco no es adaptar el mismo mensaje a varias redes, sino construir la **narrativa secuencial**: que el lector quiera seguir leyendo del tuit 1 al tuit n.

Modo **dry-run**: preparas y previsualizas el hilo. No publicas ni haces peticiones de red.

## Cómo ABRE tu salida (veredicto + leyenda, ANTES del hilo)

La salida SIEMPRE empieza por este bloque, **arriba del todo, antes del hilo**, para que un community manager no técnico vea el veredicto sin hacer scroll. Es el resumen de tu auto-verificación del final; el detalle completo se mantiene al final, intacto.

```
<una línea de veredicto, según el resultado de tu auto-verificación>
✅ LISTO PARA APROBAR   ·   ⚠️ REVISAR ANTES DE PUBLICAR   ·   ❌ NO PUBLICAR ASÍ

Leyenda: ✅ = listo · ⚠️ = revísalo tú antes de publicar · ❌ = problema, no publicar así
```

- La **línea de veredicto** es UNA de las tres, la que corresponda: `✅ LISTO PARA APROBAR` si todo salió ✅; `⚠️ REVISAR ANTES DE PUBLICAR` si hay algún ⚠️ (una cifra a confirmar, una discrepancia entre fuentes, un tuit al filo del límite); `❌ NO PUBLICAR ASÍ` si hay un ❌ (regla legal incumplida, dato inventado, un tuit que excede 280). Tras esa línea, indica en pocas palabras qué hay que revisar si no es ✅.
- La **leyenda** explica los tres símbolos para quien no los conoce.
- Esto va ANTES del hilo. El bloque de **auto-verificación DETALLADO sigue al final** (paso 6), sin recortar nada.

## Entradas

- **Fuente:** una **nota larga** o un **análisis** (`.md`) indicado por el usuario (o el `.md` más reciente / uno de `ejemplos/`, p. ej. `ejemplos/nota-larga-hilo.md`, si no indica). El insumo ideal tiene **varios puntos** que justifican contar una historia en varios tuits (no una sola declaración suelta — para eso basta un post simple de `copy-desde-nota`).
- **Marca:** si el usuario la indica, úsala; si no, infiérela del tema y dilo explícitamente. Marcas: `unotv`, `claro-sports`, `nacion-gamer`, `piso-15`, `fundacion`.
- **Voz:** si el usuario indica una persona, carga su voz; si no, usa solo la voz de marca.

## Qué NO hace esta skill

- **No publica, no programa, no llama a ninguna API ni MCP de publicación.** Solo prepara y previsualiza el hilo. El humano aprueba y publica.
- **No produce variantes para otras redes.** El entregable es **el hilo de X**. Si el usuario quiere copy para Instagram/Facebook/TikTok/YouTube, esa es la skill `copy-desde-nota`.
- **No inventa datos.** Cifras, fechas, nombres, cargos y citas salen de la fuente; lo que no esté, no se rellena (se marca ⚠️).

## Pasos

1. **Carga el contexto editorial en este orden** (lo más específico gana). Léelos con `Read`:
   - `contexto-editorial/reglas-legales.md` (siempre)
   - `contexto-editorial/tropicalizacion.md` (siempre)
   - `contexto-editorial/plataformas.md` (siempre) — usa la sección **Hilo (X)** y la de **X / Twitter** como referencia de formato.
   - `contexto-editorial/marcas/{marca}.md`
   - **Voz personal** `{voz}.md` — búscala en este orden y usa la PRIMERA que exista (así tu voz sobrevive a las actualizaciones del plugin):
     1. `~/.config/keni-social/voces/{voz}.md` (ubicación personal, fuera del repo — gana)
     2. `contexto-editorial/voces/{voz}.md` (fallback dentro del repo)

     Si solo tiene marcadores `[... — se rellena en sesión]` sin rellenar, **NO inventes la voz**: avísalo y usa solo la de marca.

2. **Extrae el núcleo y ordénalo como historia.** De la nota saca: la **tesis** (qué pasó / qué se afirma), los **puntos clave** (cada dato, ángulo o paso que sostiene la tesis) y el **dato/cifra/cita con su fuente** si aparece. **No inventes nada que no esté en la fuente**; si falta un dato, dilo, no lo rellenes. Ordena los puntos en una **secuencia narrativa**: qué va primero para enganchar, qué desarrolla, qué cierra. Cada punto será **un beat** (un tuit).

3. **Consulta qué funciona (métricas).** Si el MCP `keni-metricas` está conectado, ANTES de redactar:
   - `metricas_resumen(marca, "mes")` y `mejores_piezas(marca, "mes", 5)` → qué **ángulos/temas/formatos** rinden en esa marca en X.
   - Úsalo para decidir el **ángulo del gancho** y el tono del hilo. **Di en una línea qué aprendiste y cómo lo aplicas** (p. ej. "en Claro Sports los hilos de jugada polémica enganchan → arranco el gancho con la polémica, no con el marcador").
   - Si el MCP **no** está conectado, dilo en una línea y sigue sin métricas (no es obligatorio).

4. **Construye el hilo** (lo central de esta skill). Sigue la sección **Hilo (X)** de `plataformas.md`, pero con foco en la **narrativa**:
   - **Tuit 1 = `1/n` = GANCHO.** Debe funcionar **solo** (mucha gente solo verá ese tuit): promete la historia, abre un bucle, da el dato más fuerte o la pregunta más punzante. No lo desperdicies en "abro hilo 🧵" vacío; que ya diga algo. Puede llevar 🧵 o "(abro hilo)" si la marca lo admite.
   - **Beats `2/n`, `3/n`…**: **una idea por tuit**. Cada beat **avanza** la historia y **enlaza** con el anterior (continuidad: el final de uno invita al siguiente; usa conectores como "Pero…", "El detalle:", "¿Por qué importa?"). No metas dos ideas en un tuit ni repitas lo ya dicho.
   - **Tuit final = CIERRE + CTA/enlace.** Remata la historia (conclusión, qué sigue, dónde verlo) y pon la **llamada a la acción** propia de X (leer la nota completa, "guárdalo", "¿tú qué opinas?"). Si lleva **enlace**, va en el último tuit; el hilo debe entenderse aunque no se haga clic.
   - **Largo:** tantos tuits como puntos tenga la historia, normalmente **3–8** (incluido gancho y cierre). Si la nota da para menos de 3, probablemente no necesita hilo: dilo y sugiere un post simple.
   - **Numeración `n/n`:** numera **todos** los tuits con el total real (`1/5`, `2/5`, …, `5/5`). Ajusta el total al número final de tuits.
   - **Hashtags y emojis:** como en X — **0–2 hashtags** (idealmente solo en el primer o último tuit), emojis sobrios según la marca (la Fundación, la más sobria).
   - **Conteo exacto (OBLIGATORIO, no a ojo):** cada tuit es un **límite duro de 280**. Cuenta CADA tuit con el contador (el de `copy-desde-nota`, vía heredoc):
     ```
     python3 .claude/skills/copy-desde-nota/contar.py <<'TXT'
     <pega aquí el texto de UN tuit, sin el "n/n">
     TXT
     ```
     Muestra el conteo junto a cada tuit (p. ej. `(238/280)`). Si un tuit se pasa de 280, **divídelo** en dos beats o recórtalo — nunca lo dejes excedido. Recuerda renumerar `n/n` si cambia el total.

5. **Aplica voz + tropicalización:** impregna el tono de la marca y de la voz personal en todo el hilo; sustituye giros de España por mexicanos (ver `tropicalizacion.md`); elimina acentos/léxico de fuentes españolas. El **tono debe ser consistente** de principio a fin del hilo.

6. **Auto-verificación (OBLIGATORIO, al final).** Marca cada punto con ✅ / ⚠️ / ❌:
   - **Cada tuit ≤280:** verifica con `contar.py` **tuit por tuit**; no des por bueno ningún conteo a ojo. Si alguno excede → ❌.
   - **Narrativa:** ¿el `1/n` engancha y funciona solo? ¿cada beat aporta UNA idea nueva y enlaza con el anterior? ¿el último cierra con CTA/enlace? ¿la numeración `n/n` cuadra con el total?
   - **Fechas y números:** ¿coinciden con la fuente? ¿alguna inventada? (usa `date` para "hoy/ayer/mañana").
   - **Nombres y cargos:** errores típicos (p. ej. "expresidente" cuando es **presidente**; nombres mal escritos).
   - **Cifras y citas sin fuente:** marca toda cifra/cita que no tenga respaldo en la fuente. Si varias fuentes discrepan, usa la formulación prudente y anótalo.
   - **Reglas legales** (`reglas-legales.md`): bandera con escudo, menores/víctimas, datos personales, no prejuzgar (presunto/a), atribución de citas, derechos de terceros.
   - **¿Suena mexicano?:** ¿quedó algún giro español? ¿el tono es de la marca y de la voz, y se mantiene en todo el hilo?
   - **Veredicto:** "LISTO PARA APROBAR" solo si todo es ✅. Si hay ⚠️/❌, dilo claro y señala exactamente qué tuit revisar.

## Formato de salida (plantilla)

```
✅ LISTO PARA APROBAR   (o ⚠️ REVISAR ANTES DE PUBLICAR / ❌ NO PUBLICAR ASÍ — la que corresponda + qué revisar)
Leyenda: ✅ = listo · ⚠️ = revísalo tú antes de publicar · ❌ = problema, no publicar así

# Hilo para X (DRY-RUN) — <marca> — <tema en pocas palabras>
Marca: <marca | inferida: X>   ·   Voz: <voz | solo marca>   ·   Métricas: <1 línea de lo aprendido | MCP no conectado>

1/n  <tuit gancho, funciona solo>
(<NNN>/280)

2/n  <beat: una idea, enlaza con el anterior>
(<NNN>/280)

… (los beats que pida la historia) …

n/n  <cierre + CTA/enlace>
(<NNN>/280)

## Auto-verificación
- [✅/⚠️/❌] Cada tuit ≤280 (contado con contar.py, tuit por tuit) — <detalle>
- [✅/⚠️/❌] Narrativa: gancho que funciona solo · una idea por beat · continuidad · cierre con CTA · numeración n/n correcta — <detalle>
- [✅/⚠️/❌] Fechas y números coinciden con la fuente — <detalle>
- [✅/⚠️/❌] Nombres y cargos correctos (presidente vs expresidente, etc.) — <detalle>
- [✅/⚠️/❌] Sin cifras/citas sin fuente; discrepancias anotadas — <detalle>
- [✅/⚠️/❌] Reglas legales (bandera con escudo, menores/víctimas, datos personales, no prejuzgar, atribución, derechos) — <detalle>
- [✅/⚠️/❌] Suena mexicano y en la voz de la marca/persona, consistente en todo el hilo — <detalle>
Veredicto: <LISTO PARA APROBAR — todo ✅> / <REVISAR / NO PUBLICAR ASÍ — qué tuit y qué revisar>

⚠️ NADA se ha publicado. Esto es solo el borrador del hilo. El humano aprueba y publica; la decisión es suya. Para copy de otras redes a partir de esta nota, usa copy-desde-nota.
```

## Reglas

- NUNCA publiques de verdad ni hagas peticiones de red.
- NUNCA inventes datos, cifras, fechas, citas ni declaraciones que no estén en la fuente. Lo que falte se marca ⚠️, no se rellena.
- **Cada tuit respeta el límite de 280**; cuéntalo con `contar.py`, tuit por tuit, no a ojo. Si no cabe, divídelo o recórtalo y renumera `n/n`.
- El **gancho (`1/n`) debe funcionar solo**; cada beat aporta UNA idea y enlaza con el anterior; el último cierra con CTA/enlace. Mantén la continuidad narrativa y el tono de principio a fin.
- Esta skill produce **un hilo de X**, no variantes para otras redes (eso es `copy-desde-nota`). Si la nota no da para 3+ tuits, dilo y sugiere un post simple.
- Si la voz personal está vacía (solo marcadores), usa la de marca y avísalo — no simules una voz que no existe.
- Respeta tropicalización es-MX y las reglas legales (menores/víctimas, datos personales, no prejuzgar, bandera con escudo, atribución de citas, derechos de terceros).
- La auto-verificación no es opcional: sin ella, el hilo no sirve.
- El humano aprueba y publica. Tu salida es un borrador verificado, no una publicación.
