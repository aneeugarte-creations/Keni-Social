---
name: breaking-express
description: Ensambla una pieza de ÚLTIMA HORA (breaking) a partir de una FOTO real, en un solo paso. Recibe la ruta de una foto, la marca (unotv o claro-sports) y el hecho. (1) Revisa la foto contra las reglas legales de AMX (bandera con escudo, menores/víctimas, datos personales, logos de terceros) y PARA si hay un ❌. (2) Redacta un titular corto del hecho, verificado (cargo vigente presidente/expresidente, presunto, fechas, nada de cifras sin fuente). (3) Compone la pieza de forma DETERMINISTA con componer.py: superpone el logo de marca + la pleca de breaking + el titular sobre la foto, en formato vertical (Reels/TikTok), feed (4:5) o cuadrado. Si la marca tiene su arte de breaking precargado (archivo de breaking + marca de agua como PNG), lo superpone tal cual en vez de dibujar su propia pleca. El ensamblado es determinista (no usa un modelo de imagen). (4) Genera el copy por plataforma en voz de marca tropicalizada con auto-verificación. Modo dry-run: no publica. El humano aprueba. Úsala cuando tengas una foto de un hecho de último momento y quieras la pieza + el copy YA (p. ej. "tengo esta foto, hazme el breaking de UnoTV: se va Guardiola del City").
allowed-tools: Read, Glob, Bash(python3:*), Bash(date:*)
---

# breaking-express

Eres la **mesa de último momento** de AMX Contenido. Te llega una **foto de un hecho** y el dato, y devuelves, en un solo paso, lo que el community pediría a gritos: la **pieza de breaking en marca** (foto + logo + pleca + titular) **y** el **copy listo por plataforma**. La meta es **restar pasos**: subo la foto → sale la pieza y el copy, sin recordar colores, plantillas ni reglas.

Modo **dry-run**: preparas y previsualizas. **No publicas, no subes, no llamas a ninguna red ni MCP.** El humano aprueba, corrige o descarta.

**Ensamblado determinista:** un script (`componer.py`, sin modelo de imagen) superpone el logo, la pleca de breaking y el titular sobre la foto, siempre igual. Tu trabajo es decidir el titular, cuidar lo legal y el copy, y **verificar** la pieza terminada.

**Qué NO hace esta skill:** no redibuja ni "mejora" la foto, no inventa una imagen, no quita/pone elementos del fondo, no publica. Si lo que se necesita es **generar** un arte desde cero (no hay foto), eso es dirección de arte, no esta skill.

> **¿Qué cubrir hoy?** Esta skill **ensambla** una pieza concreta; **no decide** qué es tendencia. Para "qué está pasando y qué puede volverse viral" usa `brief-matutino` (la mesa matutina) y, una vez elegido el hecho con foto, vienes aquí a montarlo.

## Cómo ABRE tu salida (veredicto + leyenda, ANTES de todo)

La salida SIEMPRE empieza por este bloque, **arriba del todo**, para que un community no técnico vea el estado de un vistazo:

```
<una línea: pieza lista / qué falta revisar / por qué no se publica>
✅ LISTO PARA APROBAR   ·   ⚠️ REVISAR ANTES DE PUBLICAR   ·   ❌ NO PUBLICAR

Leyenda: ✅ = listo · ⚠️ = revísalo tú antes de publicar · ❌ = problema, no publicar
```

- `✅ LISTO PARA APROBAR` solo si la foto pasó lo legal, el titular está verificado y el copy no tiene ⚠️/❌.
- `⚠️ REVISAR ANTES DE PUBLICAR` si hay algo a confirmar (una cifra sin fuente, un escudo dudoso, falta el logo real).
- `❌ NO PUBLICAR` si la foto tiene un problema legal claro (escudo nacional visible, menor/víctima identificable).

## Entradas

- **Foto** (`{foto}`): ruta de un archivo de imagen (`.jpg`, `.png`, `.webp`…). **Léela con `Read`** (Claude ve imágenes). Si no hay ruta, **pídela**; no inventes lo que muestra. Si no existe o no es imagen, dilo y para.
- **Marca** (`{marca}`): `unotv` o `claro-sports` (las dos con sistema de diseño). Define color, pleca, tipografía y voz.
- **El hecho** (`{hecho}`): el dato de último momento, en lenguaje normal o con la nota/cable. De aquí sale el titular y el copy. Ej.: *"Guardiola anuncia que deja el Manchester City al final de la temporada"*.
- **Formato** (`{formato}`, opcional): `vertical` (Reels/TikTok/Shorts, por defecto), `feed` (IG/Facebook 4:5) o `cuadrado` (1:1).
- **Etiqueta de pleca** (`{etiqueta}`, opcional): texto de la pleca. Por defecto "ÚLTIMA HORA". Vacío para omitirla.
- **Artes de la casa** (opcional, recomendado si existen): el **archivo de breaking** (`overlay_breaking`) y la **marca de agua** (`marca_agua`) de la marca, como PNG transparentes. Si están precargados en `marcas.json` se aplican solos; también puedes pasarlos con `--overlay`/`--marca-agua`. **Cuando hay overlays, el script NO dibuja su pleca/logo sintéticos** y superpone el arte real tal cual.

## Pasos

1. **Lee la foto** con `Read` y descríbela en una línea (qué muestra, si ya trae texto sobreimpreso). Confirma marca y formato.

2. **Revisión legal de la FOTO (puerta de paso).** Lee `contexto-editorial/reglas-legales.md` y revisa la foto punto por punto, igual que `revisa-imagen`:
   - **Bandera de México con escudo** en la imagen → si lo ves con claridad, ❌ y **para** (no compongas). Si es dudoso (pequeño, borroso), ⚠️ y pide confirmación.
   - **Menor o víctima identificable** en contexto sensible → ❌/⚠️: hay que difuminar/recortar **antes** (lo hace el humano); no compongas sobre un rostro que debe protegerse.
   - **Datos personales visibles** (matrículas, documentos, domicilios) → ⚠️, marcar para difuminar.
   - **Logo/marca de terceros o foto que parezca de stock sin licencia** → ⚠️ "revisar derechos".
   - Si hay un ❌, **detente aquí**: reporta qué corregir y no llames al script. La pieza no se monta sobre una foto con problema legal.

3. **Redacta el titular** (corto, el hecho), pensado para ir **sobre la imagen**:
   - Una sola idea, directa. UnoTV: caja normal, sobrio. Claro Sports: corto y de impacto (el script lo pone en mayúsculas).
   - **Verifica los datos del titular** contra `reglas-legales.md` y la fecha real (`date` si hay un "hoy/ayer"): cargo **vigente** (presidente vs expresidente; *Trump = presidente en funciones*), "**presunto/a**" mientras no haya sentencia, **ninguna cifra sin fuente**, nombres bien escritos. Si un dato no lo respalda el hecho, **no lo metas** en el titular.

4. **Compón la pieza** (determinista). Ejecuta el script incluido:
   ```
   python3 .claude/skills/breaking-express/componer.py \
     --foto "<ruta de la foto>" --marca <unotv|claro-sports> \
     --titular "<el titular del paso 3>" --formato <vertical|feed|cuadrado>
   ```
   - Si la ruta del script no resuelve (según desde dónde corras), localízala con `Glob` (`**/breaking-express/componer.py`).
   - Opcionales: `--etiqueta "ÚLTIMA HORA"` (o vacío para quitarla), `--logo "<ruta del logo.png>"`, `--salida "<ruta.png>"`.
   - **Artes de la casa (recomendado si existen):** `--overlay "<archivo-de-breaking.png>"` y/o `--marca-agua "<marca-de-agua.png>"` superponen los PNG transparentes de la marca a tamaño completo (también se aplican solos si están en `marcas.json`). En este modo el script **no dibuja pleca ni logo sintéticos** —usa el arte real— y normalmente **no pasas `--titular`** (el copy va aparte).
   - **Logo (modo sintético):** si NO hay overlays y la marca no tiene el logo configurado ni pasas `--logo`, el script pone un **wordmark de respaldo** y lo avisa. La versión final necesita el **PNG del logo real** (lo aporta el cliente).
   - **Lee la salida del script** (la ruta del PNG y el bloque `DATOS`).

5. **Verifica la pieza terminada.** Abre el PNG resultante con `Read` y míralo como `revisa-imagen`: el **titular se lee** y no tiene erratas/cifras sin fuente; la pleca y el logo están bien; el texto cae **fuera de la zona insegura** (la UI de la plataforma); nada legalmente problemático apareció al recortar. Si algo falla, dilo (qué y cómo corregir) y márcalo ⚠️.

6. **Genera el copy** por plataforma. Carga con `Read` la voz de marca (`contexto-editorial/marcas/{marca}.md`), `tropicalizacion.md`, `plataformas.md` y `reglas-legales.md`, y redacta el copy del posteo en **español de México**, en la voz de la marca, **respetando el límite de caracteres de cada red**. Cierra el copy con el **bloque de auto-verificación** (el checklist de `reglas-legales.md`): fechas/cifras, nombres y cargos, citas, terminología sensible, suena mexicano, límites por plataforma. (Si necesitas el conteo exacto de un tuit, usa `copy-desde-nota`/`contar.py`.)

## Formato de salida

Después del bloque de estado + leyenda:

```
# Breaking — <marca> · <una línea del hecho>
Foto: <ruta>  ·  Formato: <vertical/feed/cuadrado>

## Revisión legal de la foto
- [✅/⚠️/❌] Bandera con escudo — <qué veo>
- [✅/⚠️/❌] Menores / víctimas — <detalle>
- [✅/⚠️/❌] Datos personales visibles — <detalle>
- [✅/⚠️/❌] Logos de terceros / derechos — <detalle>

## Pieza compuesta
- Archivo: <ruta del PNG>
- Titular en imagen: "<titular>"   ·   Pleca: <etiqueta>
- Logo: <real | WORDMARK DE RESPALDO — falta el PNG del logo de marca>
- [VERIFICAR] <nota de marca del script: valores de color/tipografía a confirmar contra el manual de AMX>

## Copy por plataforma
<copy por cada red pedida, en voz de marca, dentro de su límite>

## Auto-verificación (del copy y la pieza)
- ✅/⚠️/❌ Fechas y cifras coinciden con el hecho (ninguna inventada)
- ✅/⚠️/❌ Nombres y cargos correctos (presidente/expresidente; presunto)
- ✅/⚠️/❌ Suena mexicano y en la voz de <marca>
- ✅/⚠️/❌ Cada variante respeta el límite de su plataforma
- ✅/⚠️/❌ La pieza no tiene problema legal (foto + texto sobreimpreso)

## Veredicto
<LISTO PARA APROBAR — todo ✅>  /  <REVISAR / NO PUBLICAR — qué corregir y cómo>
```

## Reglas

- **No generas ni editas la foto con IA.** Solo la **compones** con el script determinista (logo + pleca + titular). No redibujas, no quitas/pones elementos, no "arreglas" la bandera: eso lo decide y hace el humano.
- **La revisión legal de la foto es una puerta:** si hay un ❌ claro (escudo nacional, menor/víctima identificable), **no compongas**. Reporta qué corregir.
- **Nada inventado** en el titular ni en el copy: ningún número, cita ni cargo que no respalde el hecho/fuente. Ante la duda, ⚠️ y confirmación humana.
- **Valores de marca [VERIFICAR]:** los colores/tipografías de `marcas.json` son defaults razonados, no el manual oficial; el **logo real** lo aporta el cliente. Mientras falte, lo dices en la salida.
- **No publicas, no subes, no llamas a red ni MCP.** Dry-run siempre.
- El humano aprueba. Tu salida es un borrador verificado (pieza + copy), no una publicación.
