# Estudio de imagen — keni-social
### Arquitectura y decisión · Keni AI

- **Fecha:** 2026-05-25 · **Estado:** exploración — hipótesis bajo prueba dentro del piloto AMX.
- **Origen:** sugerencia de Tescu (community Claro Sports) en el piloto: *"que yo le suba la foto, que ya tenga precargado meterle nuestro logo + el archivo de breaking, y que nos genere el copy."*
- **Para:** decidir cómo keni-social gestiona tareas de imagen como una herramienta **independiente de Generar copy**, y cómo conviven lo determinista (herramientas) y lo generativo (IA).

---

## 0. TL;DR

1. **Un "Estudio de imagen" propio**, separado de Generar copy: sube imagen(es) → operación → previsualiza → (opcional) encadena copy.
2. **Tres piezas:** un **enrutador** (decide el motor), dos **motores** (determinista = herramientas/scripts; generativo = IA por API) y un **revisor** (Claude *ve* la imagen y la pasa por las reglas legales/editoriales).
3. **Regla de oro determinista:** lo repetible y exacto (logo, pleca, recorte, marca de agua, placas) se hace con **scripts (Pillow/ffmpeg)** — local, gratis, reproducible y **sin "cara de IA"**. La foto de noticia **se respeta, no se reinventa**.
4. **Regla de oro generativa:** crear o alterar (fondos, ilustraciones, limpiar, expandir, mejorar) usa **IA por API**. **Línea editorial dura:** la IA **no altera fotos de noticia reales** (§3); se reserva a ilustraciones/fondos/gráficos.
5. **Decisiones tomadas (2026-05-25):** (a) vive en **ambos, por fases** — primero skills (motor), luego pestaña en la Consola; (b) la IA generativa va **por API**; (c) la IA **no** altera fotos reales.

---

## 1. Principio

Es la misma tesis de keni-social aplicada a la imagen: *la IA diseña el proceso la primera vez y, si es repetible, se vuelve software determinista*. Y, como Claude **ve** imágenes de forma nativa, su papel natural en imagen es **dirigir y verificar**, no renderizar.

| Tipo de tarea | Motor | Por qué |
|---|---|---|
| Logo, marca de agua, pleca/cintillo, recorte a formato, redimensionar, placas/tarjetas de texto, carrusel desde plantilla | **Determinista (script)** | Exacto, idéntico cada vez, local, gratis, sin artefactos de IA |
| Generar una ilustración/fondo, quitar/añadir elementos, expandir (outpaint), limpiar, mejorar resolución | **Generativo (IA por API)** | Requiere creación/alteración real de píxeles |
| Revisar legal/editorial cualquier salida | **Revisor (Claude ve)** | `revisa-imagen`: bandera/escudo, menores, datos personales, derechos, texto |

---

## 2. Arquitectura: enrutador + 2 motores + 1 revisor

```
                 ┌─────────────────────────────────────────┐
   imagen(es) ─▶ │  ENRUTADOR (skill estudio-imagen)         │
   + petición    │  clasifica: ¿determinista o generativo?   │
                 └───────────────┬───────────────┬───────────┘
                                 ▼               ▼
        Motor DETERMINISTA (scripts)     Motor GENERATIVO (IA por API)
        Pillow / ffmpeg                  modelo de imagen (def. Gemini)
        · overlay (breaking + marca       · generar ilustración/fondo
          de agua de la casa)             · alterar/limpiar/expandir
        · recortar a formato              [GUARDRAIL §3: no sobre
        · redimensionar                    fotos de noticia reales]
        · placa / tarjeta de texto
                                 │               │
                                 └───────┬───────┘
                                         ▼
                         REVISOR (Claude ve · revisa-imagen)
                         legal + editorial → ✅/⚠️/❌ → humano aprueba
```

- **Enrutador:** un skill (`estudio-imagen`) que, dada la petición + la(s) imagen(es), decide el motor y los parámetros, llama a la herramienta o a la IA, y siempre cierra con el revisor. Dry-run: no publica.
- **Determinista:** scripts versionados con tokens de marca en JSON (ya existe `breaking-express/componer.py` + `marcas.json`). Operaciones nuevas se añaden como subcomandos/scripts.
- **Generativo:** adaptador de un modelo de imagen por API (§6).
- **Revisor:** `revisa-imagen` (ya existe), aplicado a la salida de cualquier motor.

---

## 3. Línea editorial (guardrail) — decisión

**La IA generativa NO altera fotos de noticia reales.** Para un medio (UnoTV) y un deportivo (Claro Sports), alterar con IA una foto real es una línea roja de credibilidad y ética periodística.

- **Sobre una foto real** solo operan herramientas **deterministas**: recortar, redimensionar, overlay (logo/pleca/marca de agua), ajuste de color/legibilidad. Nada que cambie lo que la foto muestra.
- **La IA generativa** se reserva a contenido **no documental**: ilustraciones, fondos, gráficos, placas decorativas, conceptos.
- El enrutador debe **negarse** (con explicación) a una petición de alterar/recrear con IA una imagen marcada como foto real, y proponer la alternativa determinista o una ilustración claramente etiquetada.
- Coherente con `contexto-editorial/reglas-legales.md` y el "No hacer" visual de `diseno-redes-amx` (sin sensacionalismo, respeto al hecho).

---

## 4. Qué ya existe vs. qué es nuevo

| Pieza | Estado |
|---|---|
| Compositor determinista (`breaking-express/componer.py`, Pillow) | ✅ existe |
| **Modo overlay** (usar el archivo de breaking + marca de agua de la casa) | ✅ añadido (2026-05-25) |
| Director de arte por marca (prompts en marca, `07-innovacion/diseno-redes-amx`) | ✅ existe (para la vía "prompt") |
| Revisor legal/editorial (`revisa-imagen`) | ✅ existe |
| **Enrutador** `estudio-imagen` que une todo | 🆕 Fase 1 |
| Operaciones deterministas extra (recortar, redimensionar, placa de texto) | 🆕 Fase 1 |
| Motor **generativo por API** (§6) + guardrail | 🆕 Fase 1–2 |
| **Pestaña "Imágenes"** en la Consola (subir, operación, preview, assets) | 🆕 Fase 2 |

---

## 5. Plan por fases

- **Fase 1 — el motor (skills en Claude Code).**
  1. Enrutador `estudio-imagen` (clasifica determinista vs generativo, aplica el guardrail §3, cierra con el revisor).
  2. Operaciones deterministas como scripts: `overlay` (hecho), `recortar`, `redimensionar`, `placa` de texto.
  3. Adaptador generativo por API con **modo sin key** (explica el setup) y el guardrail.
  4. Assets de la casa por marca en `marcas.json` (`logo`, `marca_agua`, `overlay_breaking`) — los aporta el cliente.
- **Fase 2 — la Consola (UI).** Pestaña "Imágenes": subir foto, elegir operación (plantillas deterministas) o describir (generativo), preview, y un gestor de assets de marca. Capa de gestión encima de los skills (igual que "Generar copy").
- **Encaje con copy:** opción de **encadenar** la pieza con `copy-desde-nota`/`breaking-express` para sacar imagen + copy juntos, pero el Estudio es su propio espacio.

---

## 6. Motor generativo por API (decisión: por API)

- **Proveedor por defecto:** **Google Gemini (imagen, "Nano Banana")**, ya recomendado en `07-innovacion/diseno-redes-amx`. Adaptador con interfaz simple para poder cambiar/añadir proveedor.
- **Credenciales (estándar keni-social):** API key en **variable de entorno / gestor de credenciales**, **nunca** en el código ni en archivos versionados. Mismo principio que `mcp-metricas` (la llave vive en la máquina, no en la IA).
- **Modo sin key (degradado):** si no hay key, el adaptador **no falla**: explica cómo configurarla y, como alternativa de cero coste, ofrece la vía **"director de arte"** (Claude da el prompt en marca y el usuario genera en su herramienta) — el patrón que ya existe en `diseno-redes-amx`.
- **Coste:** la generación por API tiene **coste por imagen**; conviene reservarla a lo que de verdad la necesita (ilustraciones/fondos) y medir el volumen, como la "última milla" de `07-innovacion/automatizacion-redes-amx`.
- **Guardrail §3** integrado: el adaptador rechaza alterar fotos reales.

---

## 7. Decisiones abiertas / a verificar

1. **Assets reales de la casa:** rutas/archivos de `logo`, `marca_agua` y `overlay_breaking` por marca (los aporta AMX). Mientras falten, el modo sintético y el wordmark de respaldo cubren la demo.
2. **Proveedor generativo definitivo** y su coste por imagen (Gemini por defecto; confirmar).
3. **Operaciones deterministas prioritarias** además de overlay (recortar y placa de texto son las siguientes candidatas).
4. **Catálogo en la Consola:** cómo se listan las operaciones del Estudio (¿reusar el patrón `keni.yaml` de skills, o un catálogo de operaciones propio?).
5. **Multi-formato de salida** desde una sola imagen (9:16 + 4:5 + 1:1 de un tiro).

---

*Documento de exploración. Siguiente paso natural: construir el enrutador `estudio-imagen` (Fase 1) sobre el compositor ya existente, con el guardrail §3, y validar con el equipo el flujo "subo foto → arte de la casa → copy" que pidió Tescu.*
