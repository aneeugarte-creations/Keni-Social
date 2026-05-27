# Sistema de diseño — Claro Sports
### La base de marca que aplica el Skill `diseno-clarosports`

> **Cómo se usa esto:** es la fuente única de verdad del look de Claro Sports. El Skill la lee siempre antes de generar o verificar. Los humanos la leen para entender el estándar.
>
> **Cómo se rellena:** los valores marcados `[VERIFICAR]` son **defaults razonados**, no oficiales. Confírmalos contra el manual de marca real de AMX/Claro Sports y sustitúyelos. Mientras no se confirmen, el Skill los usa pero los trata como provisionales.

---

## 1. Esencia de marca

- **Qué es:** la casa deportiva de América Móvil. Cobertura de fútbol, Mundial, ciclismo, automovilismo y más, para toda Latinoamérica.
- **Personalidad visual:** **energía, pasión, velocidad, emoción del directo.** Es ruidosa en el buen sentido: alto contraste, dinamismo, sensación de "está pasando ahora".
- **Lo que NO es:** sobrio, neutro ni informativo-frío. Eso es UnoTV. Aquí el diseño grita el momento deportivo.
- **Momento actual:** rumbo al **Mundial FIFA 26**. La narrativa "Carrera al Mundial" puede teñir portadas y series.

## 2. Audiencia

Aficionado al deporte, mayoritariamente masculino pero ampliando, móvil-primero, consume en vivo y reacciona en caliente (goles, polémicas, fichajes). **Escanea rápido:** la pieza tiene que comunicar el qué en menos de 1 segundo. El engagement vive en la emoción y la inmediatez.

## 3. Color

> Valores extraídos de los **assets públicos de Claro Sports** (Brandfetch, mayo 2026). Indicativos, **no del manual oficial**: confírmalos. La auto-extracción puede colar colores de la web (UI) que no sean de marca — sobre todo los azules.

| Rol | Color | Uso |
|---|---|---|
| Primario | **Rojo Claro** `#CF2E2E` | Marca, barras, "última hora"/gol, acentos, fondos de bloque. El rojo es la firma. |
| Secundario | **Azul claro** `#61C7F8` `[CONFIRMAR]` | Acento deportivo, datos, elementos gráficos, degradados. Aporta el aire "broadcast deportivo". |
| Profundo | **Azul oscuro** `#004A59` `[CONFIRMAR]` | Fondos oscuros de marca (alternativa al negro), bloques, profundidad. |
| Tinta | **Negro** `#0A0A0A` | Texto sobre claro, degradados de legibilidad sobre foto. |
| Base | **Blanco** `#FFFFFF` | Texto sobre oscuro/foto, espacios limpios. |
| Apoyo | **Gris frío** `#9AA0A6` `[VERIFICAR]` | Datos secundarios, líneas, metadatos. |

**Reglas de color:**
- **Rojo = firma, azules = profundidad deportiva.** Una pieza es "de Claro Sports" cuando entra el rojo de marca (+ tipografía); los azules dan el aire de transmisión deportiva sin robarle protagonismo al rojo.
- Texto siempre a **alto contraste**: blanco sobre rojo/azul oscuro/negro, negro sobre blanco. Nunca rojo sobre negro o azul oscuro para texto (ilegible).
- Sobre fotografía deportiva (suele ser saturada): **degradado oscuro** (negro o azul oscuro `#004A59`) detrás del texto para garantizar legibilidad.
- Nota: el **rojo telecom de Claro** clásico ronda Pantone 485 / `#DA291C`; Claro Sports usa un rojo muy próximo (`#CF2E2E`). Si el manual oficial da otro, manda el manual.

## 4. Tipografía `[VERIFICAR]`

> No encontré la tipografía oficial de Claro Sports documentada públicamente. Ojo: existe un font comercial llamado *"Claro"* que **no** es el de la marca (coincidencia de nombre) — no confundir. Los nombres de abajo son **referencias de estilo**, no la fuente oficial.

- **Titular / impacto:** una **sans condensada, pesada, en MAYÚSCULAS** (estilo deportivo, tipo *Druk Wide*, *Anton*, *Tungsten* o la oficial de Claro). Comunica velocidad y fuerza. `[VERIFICAR — fuente oficial]`
- **Texto de apoyo / datos:** sans neutra y legible (la institucional de Claro, o Inter/Roboto como sustituto). `[VERIFICAR]`
- **Jerarquía:** una sola idea dominante por pieza. Titular grande > antetítulo/etiqueta pequeña > dato. Nunca dos titulares compitiendo.
- **MAYÚSCULAS** para titulares cortos de impacto; evitar bloques largos en mayúsculas (cansan).

## 5. Logo `[VERIFICAR]`

- Versión principal y versión monocroma (blanco/negro) para fondos complejos.
- **Posición por defecto:** esquina superior (izquierda o derecha, fija por formato), tamaño discreto pero siempre presente.
- **Margen de respeto:** no pegarlo al borde ni sobre zonas ruidosas de la foto.
- **Archivos:** los aporta el cliente; referenciar aquí su ruta cuando existan → `[RUTA LOGO]`.

## 6. Fotografía / vídeo

- **Acción y emoción:** gesto del jugador, celebración, intensidad. Evitar fotos posadas frías.
- Recortar buscando la cara/el gesto; dejar aire hacia donde va el texto.
- Permitido tratamiento dramático (contraste alto, viñeta, foco en el sujeto). Coherente con "energía".

## 7. Composición por formato

### A) Portada de vídeo vertical (Reels / TikTok / Shorts) — 9:16, 1080×1920
- **Zonas seguras:** deja libres ~**220 px arriba** y ~**420 px abajo** (UI de la plataforma tapa esquinas y barra inferior). El texto clave va en el **tercio central-superior**.
- Foto de acción a sangre + **degradado negro** de abajo hacia arriba.
- **Titular** corto de impacto (3-6 palabras) en mayúsculas, abajo-centro pero por encima de la zona insegura.
- Barra o acento rojo de marca + logo arriba.
- Si es marcador/resultado: bloque rojo con el dato grande y legible.

### B) Post / portada IG-Facebook — 4:5 (1080×1350) o 1:1 (1080×1080)
- 4:5 por defecto (ocupa más en el feed).
- Foco visual claro, titular legible, logo arriba, acento rojo.
- Texto nunca a menos de ~64 px de tamaño para que sobreviva en móvil.

### C) Carrusel IG — varias 4:5
- **Portada (slide 1):** el gancho — titular + foto fuerte. Es la que decide el clic.
- **Slides internas:** misma rejilla, un dato/idea por slide, numeradas si aplica. Consistencia de márgenes y tipografía entre slides.
- **Última slide:** cierre + CTA suave (seguir, comentar el partido).

### D) Vídeo para IG / Facebook (gráficos sobre el vídeo)
- **Primer frame = portada** (aplica reglas A/B según orientación): es lo que se ve parado en el feed.
- **Rótulos:** lower-third con barra roja, nombre/cargo en blanco. Mantener en zona segura.
- **Marcador / ticker:** bloque de marca consistente, esquina superior, no tapar la acción.

## 8. Reglas de legibilidad (no negociables)

1. Todo texto debe leerse en una pantalla de móvil al tamaño real del feed.
2. Contraste suficiente siempre (degradado/sombra si el fondo es ruidoso).
3. Una idea dominante por pieza.
4. Texto fuera de las zonas seguras de cada plataforma.

## 9. No hacer (antipatrones)

- ❌ Usar la **bandera nacional con el escudo** (regla legal del equipo). Bandera sin escudo si hace falta.
- ❌ Rojo de marca como texto sobre negro (ilegible) o como relleno sin intención.
- ❌ Dos titulares compitiendo / saturar de texto.
- ❌ Foto fría o posada cuando hay una de acción disponible.
- ❌ Logo sobre zona ruidosa, pegado al borde o deformado.
- ❌ Texto en la zona insegura (lo tapa la UI de la plataforma).
- ❌ Mezclar la identidad de Claro Sports con la de UnoTV (son marcas distintas).

## 10. Marcadores para rellenar en sesión

- `[VERIFICAR]` — valores de marca a confirmar contra el manual real.
- `[RUTA LOGO]` — ruta a los archivos de logo cuando el cliente los aporte.
- `[EJEMPLO REAL — se rellena con una pieza real del equipo]` — referencias visuales que funcionaron (mejor engagement) para anclar el estilo.
