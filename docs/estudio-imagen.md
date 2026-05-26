# Estudio de imagen — keni-social
### Arquitectura y decisión · Keni AI

- **Fecha:** 2026-05-25 · **Estado:** exploración — hipótesis bajo prueba dentro del piloto AMX.
- **Origen:** sugerencia de Tescu (community Claro Sports) en el piloto: *"que yo le suba la foto, que ya tenga precargado meterle nuestro logo + el archivo de breaking, y que nos genere el copy."*
- **Para:** decidir cómo keni-social gestiona tareas de imagen como una herramienta **independiente de Generar copy**, y cómo conviven lo determinista (herramientas) y lo generativo (IA).

---

## 0. TL;DR

1. **Un "Estudio de imagen" propio**, separado de Generar copy: sube imagen(es) → operación → previsualiza → (opcional) encadena copy.
2. **Tres piezas:** un **enrutador** (decide el motor), dos **motores** (determinista = herramientas/scripts; generativo = IA por API) y un **revisor** (Claude *ve* la imagen y la pasa por las reglas legales/editoriales).
3. **Regla de oro determinista:** lo repetible y exacto (logo, pleca, recorte, marca de agua, placas, extender fondo uniforme) se hace con **scripts (Pillow/ffmpeg)** — local, gratis, reproducible y **sin "cara de IA"**.
4. **Regla de oro generativa:** crear o rellenar píxeles (fondos, ilustraciones, extender el fondo de una foto) usa **IA por API**.
5. **Decisiones tomadas (2026-05-25):** (a) vive en **ambos, por fases** — primero skills (motor), luego pestaña en la Consola; (b) la IA generativa va **por API**.

---

## 1. Principio

Es la misma tesis de keni-social aplicada a la imagen: *la IA diseña el proceso la primera vez y, si es repetible, se vuelve software determinista*. Y, como Claude **ve** imágenes de forma nativa, su papel natural en imagen es **dirigir y verificar**, no renderizar.

| Tipo de tarea | Motor | Por qué |
|---|---|---|
| Logo, marca de agua, pleca/cintillo, recorte a formato, redimensionar, comprimir a un peso, placas, extender fondo uniforme | **Determinista (script)** | Exacto, idéntico cada vez, local, gratis, sin artefactos de IA |
| Generar una ilustración/fondo, extender (outpaint) el fondo de una foto, limpiar, mejorar resolución | **Generativo (IA por API)** | Requiere creación/relleno real de píxeles |
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
          de agua de la casa)             · extender (outpaint) el fondo
        · recortar / redimensionar          de una foto (expandir.py)
        · comprimir / extender fondo
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

## 3. Determinista vs. generativo (cuándo cada uno)

Es una cuestión de **coste y calidad**:

- **Determinista (gratis, sin pérdida, idéntico cada vez):** todo lo exacto y repetible — recorte, redimensionar, comprimir, overlay (logo/pleca/marca de agua), placas y **extender un fondo uniforme** (cielo/negro) estirando el borde.
- **Generativo (IA por API, con coste):** crear o rellenar píxeles — ilustraciones, fondos, gráficos y **extender el fondo de una foto** cuando NO es uniforme (`expandir.py`, que rellena solo la banda y re-compone el sujeto intacto).

Regla práctica: si la vía determinista resuelve el caso, úsala; la IA es para lo que esa no puede. Toda salida cierra con el revisor (`revisa-imagen`) y la aprueba un humano antes de publicar.

---

## 4. Qué ya existe vs. qué es nuevo

| Pieza | Estado |
|---|---|
| Compositor determinista (`breaking-express/componer.py`, Pillow) | ✅ existe |
| **Modo overlay** (usar el archivo de breaking + marca de agua de la casa) | ✅ añadido (2026-05-25) |
| Director de arte por marca (prompts en marca, `07-innovacion/diseno-redes-amx`) | ✅ existe (para la vía "prompt") |
| Revisor legal/editorial (`revisa-imagen`) | ✅ existe |
| **Enrutador** `estudio-imagen` que une todo | ✅ Fase 1 |
| Operaciones deterministas (recortar, redimensionar, comprimir, extender, placa) | ✅ Fase 1 |
| Motor **generativo por API** (§6): `generar.py` (ilustración) y `expandir.py` (outpaint de fondo) | ✅ Fase 1 |
| **Pestaña "Imágenes"** en la Consola (subir, operación, preview, assets) | ✅ Fase 2 |

---

## 5. Plan por fases

- **Fase 1 — el motor (skills en Claude Code).**
  1. Enrutador `estudio-imagen` (clasifica determinista vs generativo, cierra con el revisor).
  2. Operaciones deterministas como scripts: `overlay`, `recortar`, `redimensionar`, `comprimir`, `extender`, `placa`.
  3. Adaptador generativo por API con **modo sin key** (explica el setup): `generar.py`, `expandir.py`.
  4. Assets de la casa por marca en `marcas.json` (`logo`, `marca_agua`, `overlay_breaking`) — los aporta el cliente.
- **Fase 2 — la Consola (UI).** Pestaña "Imágenes": subir foto, elegir operación (plantillas deterministas) o describir (generativo), preview, y un gestor de assets de marca. Capa de gestión encima de los skills (igual que "Generar copy").
- **Encaje con copy:** opción de **encadenar** la pieza con `copy-desde-nota`/`breaking-express` para sacar imagen + copy juntos, pero el Estudio es su propio espacio.

---

## 6. Motor generativo por API (decisión: por API)

- **Proveedor por defecto:** **Google Gemini (imagen, "Nano Banana")**, ya recomendado en `07-innovacion/diseno-redes-amx`. Adaptador con interfaz simple para poder cambiar/añadir proveedor. `expandir.py` admite además OpenAI (`gpt-image-1`, edición con máscara) y elige según la clave disponible.
- **Credenciales (estándar keni-social):** API key en **variable de entorno / gestor de credenciales**, **nunca** en el código ni en archivos versionados. Mismo principio que `mcp-metricas` (la llave vive en la máquina, no en la IA).
- **Modo sin key (degradado):** si no hay key, el adaptador **no falla**: explica cómo configurarla y, como alternativa de cero coste, ofrece la vía **"director de arte"** (Claude da el prompt en marca y el usuario genera en su herramienta) — el patrón que ya existe en `diseno-redes-amx`.
- **Coste:** la generación por API tiene **coste por imagen**; conviene reservarla a lo que de verdad la necesita (ilustraciones/fondos, outpaint de fondo no uniforme) y medir el volumen.

---

## 7. Decisiones abiertas / a verificar

1. **Assets reales de la casa:** rutas/archivos de `logo`, `marca_agua` y `overlay_breaking` por marca (los aporta AMX). Mientras falten, el modo sintético y el wordmark de respaldo cubren la demo.
2. **Proveedor generativo definitivo** y su coste por imagen (Gemini por defecto; confirmar).
3. **Catálogo en la Consola:** cómo se listan las operaciones del Estudio (¿reusar el patrón `keni.yaml` de skills, o un catálogo de operaciones propio?).
4. **Multi-formato de salida** desde una sola imagen (9:16 + 4:5 + 1:1 de un tiro).

---

## 8. Estado (2026-05-25): formatos de entrega del fotógrafo — full + 4:5

Sugerencia del fotógrafo del equipo de redes AMX: entregar cada foto en dos formatos.
**(1) "Full"** = casi el original, con un resize pequeño, pero ajustando el **peso** del
archivo porque en eventos masivos el internet rudimentario no sube el original.
**(2) 4:5** para Instagram, donde a veces el sujeto no cabe y, si lo que falta es solo
cielo o el negro del fondo, se quiere **extender ese fondo** sin tocar a los jugadores.

Decisiones (sesión 2026-05-25): extensión **híbrida** (determinista para fondo uniforme, IA
para el resto); peso = **dropdown seleccionable** (no valor fijo); 4:5 = **automático con
vista previa** (detecta cuando el recorte cortaría al sujeto y propone el encaje; el humano
aprueba antes de publicar). Contexto en
`07-innovacion/keni-social/notas/2026-05-25-formatos-entrega-foto-full-y-4-5.md`.

Hecho en el repo:
- `editar.py comprimir`: baja el peso a un objetivo (`--peso-max-mb`) conservando el tamaño
  (resize pequeño opcional con `--max`); si ni la calidad mínima cabe, reduce el tamaño y lo
  anota. Salida jpg/webp.
- `editar.py extender`: encaja en un formato extendiendo **solo el borde uniforme**
  (cielo/negro) estirando el borde — no inventa contenido. Reparte el lienzo añadido solo por
  el lado uniforme (p. ej. solo arriba = cielo). Si ningún borde es uniforme o haría falta
  extender más de `--max-ext` (25%), cae al recorte cubriente y marca
  `extension_segura: false`: ahí pasa a `expandir.py`.
- `expandir.py` (motor generativo): **outpainting de fondo** cuando el fondo NO es uniforme.
  Proveedor **intercambiable** (`auto|openai|gemini`, elige según la clave del entorno):
  OpenAI por edición con máscara (gpt-image-1) o Gemini por imagen+instrucción. Pase lo que
  pase el proveedor, al final se **RE-COMPONE** la foto original sobre su región exacta → el
  sujeto queda intacto pixel a pixel; la IA solo aporta la banda. Modo sin key = dirección de
  arte (no falla).
- `SKILL.md`: enrutado de las tres vías (recortar / extender / expandir) + flujo auto/vista
  previa.
- `keni.yaml`: dropdowns en la Consola — **Peso** (≤1/2/3 MB) y **Ajuste** (recortar /
  extender fondo / extender fondo con IA). Declarativos: no requieren tocar el frontend.
- Tests Pillow en `estudio-imagen/test_editar.py` y `test_expandir.py` (locales, con el
  proveedor de IA mockeado; el CI estático de skills no instala Pillow).
- **Credenciales: un solo almacén.** La clave de imagen vive SOLO en `secretos.toml`
  (gestionado por la UI, `0600`). Las skills son un plugin independiente y solo leen
  variables de entorno, así que al lanzar la skill la Consola **exporta** esa clave del
  almacén al entorno del subproceso (`generaciones._entorno_skill`: mapea proveedor →
  `OPENAI_API_KEY` / `GEMINI_API_KEY`, sin pisar una variable ya puesta). No hay segundo
  almacén: `secretos.toml` es la única fuente y solo se transporta al subproceso.

Pendiente:
1. Detección del sujeto para automatizar al 100% el disparador "el recorte cortaría al sujeto"
   (hoy el heurístico es la uniformidad del borde + el ratio).

---

*Documento de exploración. Siguiente paso natural: construir el enrutador `estudio-imagen` (Fase 1) sobre el compositor ya existente, y validar con el equipo el flujo "subo foto → arte de la casa → copy" que pidió Tescu.*
