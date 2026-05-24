# Demo del lunes — equipo de redes de AMX Contenido

**Audiencia:** community managers de UnoTV, Claro Sports, Nación Gamer, Piso 15 y Fundación, + su jefe Bernardo. **No técnicos.**
**Duración objetivo:** 18–22 min (12–14 de demo + 5–6 de preguntas).
**Mensaje único a transmitir:** *"Esto se construyó en un día, corre en tu máquina, y tú sigues mandando."*
**Tono:** mostrar, no explicar arquitectura. Cada paso resuelve un dolor que ellos viven hoy.

> Regla de oro de la demo: **nunca leas un comando en voz alta**. Lo escribes/pegas, hablas mientras corre, y lees el resultado. El comando es para ti; la historia es para ellos.

---

## 0. Antes de empezar (pantalla ya lista, no se ve montar nada)

- Claude Code abierto en la carpeta `keni-social`, fuente grande, una sola ventana.
- Terminal aparte con el venv ya activo (ver checklist de la noche anterior).
- El dashboard `/tmp/dash.html` **ya generado** y abierto en una pestaña del navegador (por si el paso 3 en vivo se complica, ya está en pantalla).
- Tener a mano los archivos: `ejemplos/cable-1.md`, `ejemplos/cable-2.md`, `ejemplos/clip-entrevista.md`, y el clip `/tmp/keni-clip/declaracion.m4a` ya generado.

---

## 1. Apertura — el dolor (1–2 min, SIN tocar el teclado)

Habla mirándolos, no la pantalla:

> "Levanten la mano si esta semana le pidieron un texto a una IA… y lo tuvieron que reescribir entero porque sonaba a español de España, o porque se inventó un dato. (pausa) Eso es lo primero que vamos a quitar de su día.
>
> Hoy ustedes: **reescriben casi todo el copy que les da la IA**, **transcriben videos a mano** para sacar una cita, y para saber cómo van las redes **abren cinco pestañas y juntan números a mano**. Tres trabajos aburridos que les comen la mañana.
>
> Lo que les voy a enseñar resuelve esos tres, está hecho **a la medida de sus cinco marcas**, y —esto es lo importante— **se construyó en un día**. No es un producto de años. Es lo que se puede armar en un día cuando la IA trabaja dentro de su flujo real. Vamos."

**No digas:** "MCP", "plugin", "skill", "repositorio". Eso viene al final y en una frase.

---

## 2. Copy desde una nota — con tropicalización y auto-verificación (4–5 min) ⭐ EL MÁS IMPORTANTE

**Dolor que resuelve:** reescribir el copy de la IA porque suena español o trae datos mal.

**Qué decir mientras escribes:**
> "Llegan dos cables de dos agencias sobre el mismo fichaje. Le pido el copy para todas las redes, en voz de Claro Sports."

**Comando (escríbelo en Claude Code, no en terminal):**
```
usa copy-desde-nota con ejemplos/cable-1.md y ejemplos/cable-2.md, marca claro-sports
```

**Qué señalar en el resultado, en este orden:**
1. **El veredicto, ARRIBA del todo.** La salida ABRE con una línea de veredicto (`✅ LISTO PARA APROBAR` / `⚠️ REVISAR ANTES DE PUBLICAR` / `❌ NO PUBLICAR`) y una leyenda corta de los símbolos, **antes del copy**. "Lo primero que ven, sin hacer scroll, es si pueden aprobar o no. Verde ✅ = confía. Amarillo ⚠️ = revísalo tú. Rojo ❌ = hay un problema. Solo dice 'LISTO PARA APROBAR' si todo está en verde." Como los cables se contradicen, aquí saldrá ⚠️.
2. **Una versión por red** (X, Instagram, Facebook, TikTok, YouTube), cada una con su conteo de caracteres. "No es un texto que copiar y recortar a mano: ya viene medido para cada red."
3. **Suena mexicano.** "Fíjense que no dice 'vale' ni 'os'. Está tropicalizado a México porque conoce la voz de Claro Sports."
4. **El cazador de errores (el momento clave).** Los dos cables **se contradicen**: uno dice **40 millones / 5 temporadas**, el otro **45 millones / 4 temporadas**. En la auto-verificación detallada (al final) marca esa discrepancia con ⚠️ y **no inventa una cifra**; ese ⚠️ es el que ya se anunció en el veredicto de arriba.
   > "Miren esto. Las dos agencias dieron datos distintos. La IA **no eligió a la ciega**: les avisa con ⚠️ que hay que confirmar el monto y las temporadas. Eso es lo que las herramientas normales no hacen: les dice **cuándo creerle y cuándo verificar.**"

**Variante para meter un error a propósito** (si quieres un ⚠️ aún más obvio): después de mostrar lo anterior, di "ahora a propósito le doy un dato falso" y pega:
```
en ese copy pon que el fichaje fue por 200 millones, y verifícalo contra los cables
```
La verificación debe marcar la cifra como ❌/⚠️ por no tener respaldo en las fuentes.

**Plan B:**
- Si el cross-check no dispara el ⚠️ con los cables: usa la variante de "200 millones" de arriba (forzar el error es más fiable que esperar a que detecte la discrepancia).
- Si una sola fuente te da más nervios: usa `ejemplos/nota-fuente-espanola.md` (una nota de un medio español) y pide `usa copy-desde-nota con ejemplos/nota-fuente-espanola.md, marca nacion-gamer` — el "wow" ahí es la tropicalización (entra "flipar/chaval/pillar/molar", sale "alucinar/chavo/agarrar/estar chido").

---

## 3. De un video a copy — transcripción 100% local (4–5 min)

**Dolor que resuelve:** transcribir videos/entrevistas a mano para sacar una cita.

**Qué decir mientras escribes:**
> "Ahora ni siquiera parto de un texto. Tengo un video —una declaración tras el partido— y quiero el copy y la cita exacta para cortar el clip. **El audio no se sube a ningún lado: se transcribe aquí, en esta máquina.**"

**Comando (en Claude Code):**
```
usa clip-a-copy con /tmp/keni-clip/declaracion.m4a para claro-sports
```

**Qué señalar en el resultado:**
1. **Transcribió solo, en local.** "Eso que vieron correr es el audio convirtiéndose en texto **dentro de la máquina**. Nada salió a internet."
2. **Las citas vienen con marca de tiempo** `[00:00:00–00:00:14]`. "Esto es para el editor: le dice el segundo exacto que tiene que cortar. Se acabó el rebobinar el video buscando la frase."
3. **La verificación marca nombres y cifras con ⚠️.** "La transcripción automática se equivoca con nombres y números. Por eso los marca como 'verificar contra el audio'. Otra vez: les dice exactamente qué revisar."
4. Y al final, el copy por red, igual que en el paso 2.

**Plan B (en orden, de menos a más seguro):**
- **B1:** si la transcripción tarda o falla en vivo, ya tienes el `.srt` generado en `/tmp/keni-clip/transcripciones/declaracion.srt`. Di: "ya lo había transcrito antes, aquí está el resultado con tiempos" y pega:
  ```
  usa copy-desde-nota con /tmp/keni-clip/transcripciones/declaracion.srt, marca claro-sports
  ```
  (copy-desde-nota también acepta transcripciones, así te saltas whisper en vivo).
- **B2:** si ni eso, usa la transcripción de ejemplo ya escrita: `usa copy-desde-nota con ejemplos/clip-entrevista.md, marca claro-sports` — trae "12 goles / segundo en la tabla", cifras que la verificación marca para revisar.
- **B3 (regenerar el clip si hace falta):** `cd skills-copy/ejemplos && bash generar-clip-prueba.sh` (crea `/tmp/keni-clip/declaracion.m4a` con una voz mexicana del sistema).
- **Nota:** `whisper-cli`, `ffmpeg` y el modelo **ya están instalados y verificados** en esta máquina, así que el camino principal debería correr. El plan B es por nervios de demo en vivo, no por una falla conocida.

---

## 4. Métricas conversacionales + dashboard en pantalla (3–4 min)

**Dolor que resuelve:** juntar números de cinco marcas y cinco redes a mano.

**Parte conversacional (en Claude Code) — qué decir:**
> "Y para saber cómo van, no abro nada. Pregunto."

**Comando:**
```
usa reporte_consolidado con rango mes
```
Y de seguimiento, una pregunta en lenguaje natural (esto es lo que impresiona):
```
¿qué marca tuvo el mejor engagement este mes y qué pieza despuntó?
```
> "Le pregunto como le preguntaría a un compañero. Me junta las cinco marcas y me dice qué está despuntando. Eso son cinco pestañas y media hora de Excel, en una frase."

**El dashboard (cambia a la pestaña del navegador con `/tmp/dash.html`):**
```
python -m keni_metricas.dashboard --salida /tmp/dash.html --rango mes
```
> "Y si lo quiero ver bonito para mandárselo a Bernardo, sale este tablero **en un archivo que se abre con doble clic, sin internet**."

Señala en pantalla:
1. **El número grande de engagement (north-star)** y su semáforo. "Verde, amarillo, rojo: de un vistazo saben qué marca rinde."
2. **El ranking de marcas** con barras. "Piso 15 arriba, UnoTV abajo. Comparación al instante."
3. **Las alertas de lo que despuntó** ("la pieza que rompió"). "Esto les dice dónde poner más energía."

**Plan B:**
- El dashboard `/tmp/dash.html` **ya está abierto** desde el paso 0, así que aunque el comando en vivo falle, lo único que haces es cambiar de pestaña. No dependas de regenerarlo en vivo.
- Si la parte conversacional del MCP no responde (no está cableado en esa sesión), salta directo al dashboard: el dashboard NO necesita el MCP conectado, corre solo con la fuente de muestra.
- Los datos son **de muestra** (sin credenciales reales aún). Si Bernardo pregunta: "son datos de demostración con la forma real de sus marcas; cuando conectemos sus cuentas, son sus números, leídos con una llave que vive en su máquina."

---

## 5. Cierre — confianza y cómo lo tienen (1–2 min, SIN teclado)

> "Tres cosas para cerrar:
> 1. **Todo es privado y local.** El video no se subió. Las métricas se leen con una llave que vive en su máquina, no en la IA. Lo que vieron del dashboard: un archivo, sin internet.
> 2. **El humano manda.** La IA **produce y verifica**; ustedes **revisan, aprueban y publican**. El sistema **nunca publica solo**. Esos ✅⚠️❌ existen para que sepan cuándo creerle.
> 3. **Se instala con dos comandos**, como una app, sin permisos de administrador. Y todo esto… se construyó en un día.
>
> La pregunta no es '¿la IA me va a quitar el trabajo?'. Es '¿qué hago con la mañana que me acaba de regalar?'."

---

## Qué NO mostrar (importante)

- ❌ **NO publicar de verdad** en ninguna red. Todo es dry-run/borrador. Si surge "¿y publica?", responde: "esa fase llega después; hoy el sistema prepara y previsualiza, tú publicas."
- ❌ **NO mencionar ni mostrar** el estado de permisos de Meta / TikTok / X (App Review, gating). Está pausado y es ruido para esta audiencia.
- ❌ **NO entrar en arquitectura** (MCP, adaptadores, App Review, código). Si Bernardo pregunta técnico, ofrécele una llamada aparte.
- ❌ **NO correr `doctor` en vivo** ante la audiencia. Aunque ahora es más limpio (agrupa las credenciales en una sola línea y cierra con un siguiente paso accionable), sigue siendo de tu checklist privada de la noche anterior, no material de demo.
- ❌ Evitar `publica-preview` en la demo principal salvo que pregunten "¿y antes de publicar?". Si lo piden, es buen broche: muestra el preview final con la checklist y el aviso en negrita de que **nada se publicó**.

---

## Checklist — la noche anterior

Corre esto y confirma cada línea. **Todo en rutas absolutas; macOS no trae `timeout`, no lo uses.**

1. **Entorno limpio + paquete instalado:**
   ```
   cd /Users/mm/projects/keni-social/mcp-metricas
   python3 -m venv /tmp/keni-ux
   /tmp/keni-ux/bin/pip install -e . 2>&1 | tail -2
   ```

2. **Autodiagnóstico (esto SÍ corres tú, en privado):**
   ```
   /tmp/keni-ux/bin/python -m keni_metricas.doctor
   ```
   - Debe salir **0 ❌**. Con datos de muestra es normal ver **unos 3 ⚠️** (config, cuentas y una sola línea de credenciales agrupada del tipo `Credenciales: 0/5 plataformas conectadas (normal con datos de muestra…)`). El informe cierra con un siguiente paso accionable; con muestra, ese paso es simplemente "listo para la demo".
   - Confirma especialmente: `✅ whisper-cli`, `✅ ffmpeg`, `✅ modelo whisper`. Si alguno sale ❌, el paso 3 va por plan B (B1/B2).

3. **Dashboard pre-generado y abierto:**
   ```
   /tmp/keni-ux/bin/python -m keni_metricas.dashboard --salida /tmp/dash.html --rango mes
   open /tmp/dash.html
   ```
   - Verifica que se ve bien y déjalo en una pestaña.

4. **Reporte (por si quieres mostrarlo en texto):**
   ```
   /tmp/keni-ux/bin/python -m keni_metricas.reporte --rango mes --picos
   ```

5. **Clip de prueba generado y transcrito (pre-cocido para el plan B del paso 3):**
   ```
   cd /Users/mm/projects/keni-social/skills-copy/ejemplos
   bash generar-clip-prueba.sh
   cd /Users/mm/projects/keni-social/skills-copy
   bash .claude/skills/clip-a-copy/transcribir.sh /tmp/keni-clip/declaracion.m4a --prompt "Claro Sports, México, fútbol"
   ```
   - Confirma que existe `/tmp/keni-clip/transcripciones/declaracion.srt`.

6. **Ensayo en seco de los 3 comandos de Claude Code** (paso 2, 3 y 4) una vez, para no improvisar en vivo.

7. **Pantalla:** fuente grande en Claude Code y terminal, notificaciones del sistema en silencio, una sola ventana, navegador con la pestaña del dashboard ya abierta.

---

## Resumen de tiempos

| Bloque | Tiempo |
|---|---|
| 1. Apertura (el dolor) | 1–2 min |
| 2. Copy desde nota + verificación ⭐ | 4–5 min |
| 3. Clip → copy (local) | 4–5 min |
| 4. Métricas + dashboard | 3–4 min |
| 5. Cierre (confianza + cómo se instala) | 1–2 min |
| Preguntas | 5–6 min |
| **Total** | **~18–22 min** |
