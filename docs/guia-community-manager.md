# Guía para community managers

Esta guía es para quien escribe y publica en redes, no para programadores. No hay jerga
técnica: solo **qué le escribes a Claude** para cada tarea y qué esperar a cambio.

Trabajas dentro de Claude Code, en la carpeta del proyecto. Le hablas como a un redactor:
le escribes una instrucción en lenguaje normal y él responde con el borrador. **Tú siempre
apruebas antes de publicar; el sistema nunca publica solo** (más abajo, "Qué NO hace todavía").

Las marcas se escriben así (cópialas tal cual): `unotv`, `claro-sports`, `nacion-gamer`,
`piso-15`, `fundacion`.

---

## Tarea 1 — Sacar copy desde una nota escrita

Cuando ya tienes la nota, el cable o un texto y quieres el copy para cada red.

**Lo que escribes:**

```
usa copy-desde-nota con ejemplos/clip-entrevista.md, marca claro-sports, voz tescu
```

Cambia las tres cosas por las tuyas:
- el archivo de la nota (la ruta de tu nota, por ejemplo `notas/gol-de-mexico.md`),
- la `marca` (de la lista de arriba),
- la `voz` (tu nombre, si ya tienes tu voz personal cargada; si no, omítela).

Si tienes **varias notas del mismo tema** (cables de distintas agencias), pásalas todas:
él las trata como una sola historia y, si los datos no coinciden entre fuentes, te lo avisa
en vez de elegir en silencio.

**Lo que recibes:** una versión por plataforma (X, Instagram, Facebook, TikTok, YouTube),
con el conteo de caracteres, en la voz de la marca y, si la cargaste, en tu voz. Si el tema
da para más, también puede armar un **carrusel** o un **hilo**.

---

## Tarea 2 — Sacar copy desde un video o un audio

Cuando partes de una entrevista, una declaración o un fragmento de podcast y quieres el copy
sin tener que escuchar todo el material.

**Lo que escribes:**

```
usa clip-a-copy con /ruta/al/video.mp4 para claro-sports
```

Cambia `/ruta/al/video.mp4` por la ruta de tu archivo (sirve `.mp4`, `.mov`, `.m4a`, `.mp3`,
`.wav`...) y `claro-sports` por tu marca. Si quieres tu voz personal, añade `voz tu-nombre`.

**Lo que recibes:**
- el copy por plataforma, igual que en la Tarea 1, y
- las **mejores citas con su marca de tiempo** (por ejemplo `[00:02:14–00:02:31]`), para que
  el editor sepa exactamente qué fragmento cortar para el clip.

El audio se transcribe **dentro de la máquina** (no se sube a ningún lado). Como la
transcripción automática se equivoca con nombres propios y cifras, Claude los marca como
"verificar contra el audio": no son verdad confirmada hasta que tú los chequeas.

> ¿No tienes un video a la mano para probar? Pide un clip de ejemplo:
> `cd ejemplos && bash generar-clip-prueba.sh`, y luego
> `usa clip-a-copy con /tmp/keni-clip/declaracion.m4a para claro-sports`.

---

## Tarea 3 — Consultar métricas

Cuando quieres ver cómo van las redes de una marca o de todas.

**Para ver qué marcas y plataformas hay disponibles (empieza por aquí):**

```
usa listar_cuentas
```

**Para el resumen de una marca (visualizaciones, alcance, engagement y su variación):**

```
usa metricas_resumen con cuenta claro-sports y rango semana
```

El `rango` puede ser `semana`, `mes`, `7d` o `30d`.

**Para ver las piezas que mejor funcionaron:**

```
usa mejores_piezas con cuenta claro-sports, rango mes y n 5
```

**Para un informe de TODAS las marcas juntas:**

```
usa reporte_consolidado con rango mes
```

**Para que te avise de lo que despunta (un post que se disparó, una cuenta fuera de lo normal):**

```
usa picos con rango semana
```

> El copy y las métricas se conectan solos: cuando pides copy, Claude puede mirar primero qué
> está funcionando en esa marca y ajustar el ángulo a lo que rinde. Si las métricas no están
> conectadas, lo dice y sigue sin ellas.

---

## La auto-verificación: cuándo creerle

Cada vez que Claude redacta copy, lo **ABRE con un veredicto** (arriba del todo, antes del
copy, para que no tengas que bajar a buscarlo) y una leyenda corta de los símbolos. El
veredicto es una de estas tres líneas:

- **✅ LISTO PARA APROBAR** — todo salió bien.
- **⚠️ REVISAR ANTES DE PUBLICAR** — hay algo que **te toca confirmar** tú (típico: una cifra
  o un nombre sacados de un audio, o una discrepancia entre fuentes).
- **❌ NO PUBLICAR** — hay un problema (por ejemplo, se pasa del límite de caracteres o hay un
  tema legal).

Esos mismos símbolos marcan cada punto del **detalle de la auto-verificación, que sigue al
final** del copy: ✅ comprobado, ⚠️ revísalo tú, ❌ problema. Ahí Claude revisa fechas, números,
nombres, citas, reglas legales (bandera/escudo, menores, datos personales) y que "suene
mexicano". El veredicto de arriba es el resumen de ese detalle: dice **"LISTO PARA APROBAR"**
solo si todo está en ✅. Si ves ⚠️, no es que esté mal: es que **te toca confirmarlo**. Esa es
la idea del sistema — te dice exactamente cuándo creerle y cuándo verificar.

---

## Qué NO hace todavía

Para evitar sorpresas, esto es lo que el sistema **no** hace por ahora:

- **No publica solo.** Prepara y previsualiza el copy (modo borrador). Publicar lo haces tú,
  a mano, en cada red. Tú eres quien aprueba siempre.
- **No programa publicaciones** ni las pone en cola.
- **No edita el video.** Con un clip te dice qué fragmento cortar, pero el corte lo hace
  una persona.

> **¿Prefieres botones a teclear?** Además de escribirle a Claude, hay una **Consola Keni**
> con interfaz web que envuelve estas mismas tareas (corre en tu máquina, en
> `http://127.0.0.1:8765`). Es opcional; lo de esta guía funciona igual por conversación.
> Ver la [guía de la consola](consola.md).

En resumen: el sistema **produce y verifica**; tú **revisas, apruebas y publicas**.
