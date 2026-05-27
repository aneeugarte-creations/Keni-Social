# Primeros pasos (~5 minutos)

Esta guía es para quien **acaba de instalar el plugin** y quiere ver el sistema funcionando hoy, sin tecnicismos. No necesitas saber programar: a Claude le hablas como a un redactor y él responde con el borrador. **Tú siempre apruebas antes de publicar; el sistema nunca publica solo.**

Trabajas dentro de **Claude Code**, en la carpeta del proyecto `keni-social`. Si aún no has instalado el plugin, hazlo primero con los dos comandos del [`README.md`](../README.md#instalación-como-plugin).

> **¿Prefieres una interfaz a teclear comandos?** Hay una **Consola Keni** que corre en tu máquina: una alternativa con botones a escribirle a Claude Code. Arráncala con `python -m keni_consola` y abre `http://127.0.0.1:8765`. Qué es y qué páginas tiene, en la [**guía de la consola**](consola.md).

> **Importante (honestidad por defecto):** las métricas funcionan con **datos de muestra** —números con la forma real de las cinco marcas, pero ficticios— hasta que conectes credenciales reales. Todo lo de esta guía corre **sin conectar ninguna cuenta**.

En los ejemplos de abajo la marca va escrita tal cual hay que teclearla (p. ej. `claro-sports`). La lista completa de marcas está en la [guía para community managers](guia-community-manager.md).

---

## 1. Copy desde una nota (~1 min)

Tienes una nota, un cable o un texto y quieres el copy para cada red.

**Escríbele a Claude:**

```
usa copy-desde-nota con skills-copy/ejemplos/cable-1.md y skills-copy/ejemplos/cable-2.md, marca claro-sports
```

(Cambia los archivos por los tuyos y la `marca` por la que toque. Si tienes tu voz personal cargada, añade `voz tu-nombre`.)

**Qué esperar:**
- Arriba del todo, un **veredicto**: `✅ LISTO PARA APROBAR`, `⚠️ REVISAR ANTES DE PUBLICAR` o `❌ NO PUBLICAR`.
- Una **versión por plataforma** (X, Instagram, Facebook, TikTok, YouTube), cada una con su conteo de caracteres y tropicalizada a México.
- Al final, el **detalle de la auto-verificación** (fechas, nombres, cifras, reglas legales). Los dos cables de ejemplo se contradicen a propósito, así que verás un `⚠️`: el sistema **no inventa** la cifra, te dice que la confirmes.

---

## 2. Copy desde un clip de video (~2 min)

Partes de un video o audio y quieres el copy y la cita exacta para cortar el clip, sin escuchar todo. **El audio se transcribe dentro de tu máquina; no se sube a ningún lado.**

Si no tienes un archivo a la mano, genera uno de prueba (una vez):

```
cd skills-copy/ejemplos && bash generar-clip-prueba.sh
```

Luego, en Claude Code:

```
usa clip-a-copy con /tmp/keni-clip/declaracion.m4a para claro-sports
```

(Sirven `.mp4`, `.mov`, `.m4a`, `.mp3`, `.wav`...)

**Qué esperar:**
- Verás correr la **transcripción local**.
- El copy por plataforma, igual que en el paso 1.
- Las **mejores citas con su marca de tiempo** (p. ej. `[00:02:14–00:02:31]`), para que el editor sepa qué fragmento cortar.
- Como la transcripción automática se equivoca con nombres y cifras, los marca con `⚠️` para que los confirmes contra el audio.

---

## 3. Métricas por conversación + dashboard (~1 min)

Quieres ver cómo van las redes sin abrir cinco pestañas.

**Empieza por ver qué hay disponible (en Claude Code):**

```
usa listar_cuentas
```

**Resumen de una marca (visualizaciones, alcance, engagement y su variación):**

```
usa metricas_resumen con cuenta claro-sports y rango semana
```

**Informe de todas las marcas juntas:**

```
usa reporte_consolidado con rango mes
```

Y puedes preguntarle en lenguaje natural, p. ej.: *"¿qué marca tuvo el mejor engagement este mes y qué pieza despuntó?"*

**Para verlo bonito, genera el dashboard** (un archivo HTML que se abre con doble clic, sin internet). En la terminal:

```
python -m keni_metricas.dashboard --salida dashboard.html --rango mes
```

Ábrelo con doble clic (o `open dashboard.html` en macOS). Verás el número grande de engagement con su semáforo, el ranking de marcas y las alertas de lo que despuntó.

> Recuerda: por defecto son **datos de muestra**. Cuando conectes las cuentas reales, son los números de la marca, leídos con una llave que vive en tu máquina.

---

## 4. Comprueba tu entorno (~30 s)

Si algo no arranca (sobre todo las métricas o la transcripción), corre el **autodiagnóstico** en la terminal:

```
python -m keni_metricas.doctor
```

Revisa el entorno y explica cada `❌` con el paso para arreglarlo. Con datos de muestra es **normal** ver algún `⚠️` (no hay credenciales conectadas todavía); eso no impide nada de esta guía. Para conectar cuentas reales más adelante, el asistente guiado te lleva paso a paso: `python -m keni_metricas.asistente` (ver [`credenciales.md`](credenciales.md)).

---

## Siguiente paso

Para el **día a día** —todas las tareas, qué escribirle a Claude y cómo leer la auto-verificación— ve a la [**guía para community managers**](guia-community-manager.md). Para entender cómo encaja todo, [`arquitectura.md`](arquitectura.md); para el panorama honesto del producto, [`estado-producto.md`](estado-producto.md).
