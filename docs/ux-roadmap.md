# Roadmap de UX/UI de keni-social

*Evaluación heurística read-only de toda la experiencia (skills de copy, CLIs de métricas,
onboarding, dashboard y guía). Sirve de insumo para una próxima ola de rediseño.*

**Audiencia del producto:** community managers NO técnicos de AMX (UnoTV, Claro Sports,
Nación Gamer, Piso 15, Fundación) + su jefe Bernardo.
**Filosofía:** la IA produce y verifica; el humano aprueba.

Este documento NO toca código. Recorre cada superficie, lista fricciones para un usuario no
técnico, prioriza mejoras por impacto/esfuerzo y propone un "norte" de experiencia. Todo lo
que se afirma del producto se contrastó leyendo el código y ejecutando las CLIs/dashboard con
la fuente `muestra`.

---

## 1. Hallazgos por superficie

### 1.1 Skills de copy (`skills-copy/.claude/skills/*/SKILL.md`)

Las seis skills (`copy-desde-nota`, `clip-a-copy`, `nota-a-formato`, `resumen-tendencia`,
`publica-preview`, `revisa-imagen`) son sólidas, consistentes y comparten la disciplina
dry-run + auto-verificación. Lo que un CM recibe es coherente entre skills.

**Lo que funciona bien**
- El **bloque de auto-verificación ✅/⚠️/❌** está bien definido y es uniforme: cada skill
  cierra con un checklist y un veredicto explícito ("LISTO PARA APROBAR" solo si todo ✅,
  "LISTO TRAS VERIFICAR: <lista>" cuando hay ⚠️). Esto materializa el "cuándo creerle a la IA".
- El **formato por plataforma** está bien acotado en `contexto-editorial/plataformas.md`
  (límites duros de X=280 y título YouTube=70, hashtags por red, carrusel/hilo opcionales),
  y las skills exigen `contar.py` para los conteos estrictos — no se cuenta a ojo.
- La separación marca/voz/tropicalización y el orden de precedencia ("lo más específico gana")
  es clara, y la regla "si la voz está vacía, no la inventes" protege al usuario.

**Fricciones para un CM no técnico**
- **El veredicto y el checklist viven al FINAL de una salida larga.** Tras 5 variantes por
  plataforma (+ posible hilo y carrusel), el CM tiene que hacer scroll hasta abajo para saber
  si puede aprobar. El dato más accionable ("✅ puedes publicar" vs. "⚠️ revisa esto") debería
  estar también arriba, como un semáforo de una línea.
- **La leyenda ✅/⚠️/❌ no aparece en la salida de la skill**, solo en la guía. Un CM que abre
  Claude Code sin haber leído `docs/guia-community-manager.md` ve símbolos sin clave. Falta una
  línea recurrente del tipo "⚠️ = te toca confirmarlo tú, no es que esté mal".
- **La invocación es texto memorizado**: `usa copy-desde-nota con <archivo>, marca <id>, voz <voz>`.
  El CM tiene que recordar los **ids exactos de marca** (`claro-sports`, no "Claro Sports") y la
  sintaxis. No hay autocompletado ni una forma de "elegir de una lista". Los comandos `/` ayudan a
  descubrir flujos, pero las skills de copy se siguen invocando con prosa.
- **Las marcas se escriben con guion en la guía/skills (`claro-sports`) pero con guion_bajo en
  las métricas/config (`claro_sports`).** El reporte imprime `claro_sports`, `claro_sports_golf`;
  la guía dice `claro-sports`. Para un no técnico esto es un choque silencioso: el mismo nombre
  con dos ortografías según la superficie.
- **El conteo de caracteres se muestra como número crudo** (p. ej. "241/280"). Bien, pero no hay
  un indicador visual de "cabe / no cabe" salvo el ✅/❌ que la skill debe añadir; depende de que
  el modelo lo formatee. Es un punto donde la consistencia depende del LLM, no del producto.

### 1.2 CLIs de métricas (`reporte`, `doctor`, `notificaciones`, `asistente`)

Toda la salida está en **español** y con tono pensado para no técnicos (sobre todo el doctor).
La arquitectura "funciones puras + render" es limpia. Pero el render para humanos tiene roces.

**`reporte.py` / `picos`**
- **El listado de alertas/picos se vuelca PLANO y sin tope.** Con la fuente de muestra el reporte
  `--picos` imprime **24 alertas** seguidas (la notificación semanal, 29). El dashboard ya
  aprende a colapsar a 6 + "ver todas", pero la **CLI y el digest de notificaciones NO** lo
  hacen: el CM recibe un muro de 🔼 difícil de escanear. La señal ("qué miro hoy") se pierde
  en el ruido.
- Las alertas son **todas "pieza que despunta"** y casi idénticas en redacción; no hay jerarquía
  (top 3 que importan vs. el resto). Para Bernardo, "lo que rompió esta semana" debería ser 1–3
  líneas, no 24.
- El encabezado del reporte muestra la marca de tiempo **ISO cruda** (`*Generado
  2026-05-24T17:36:49+00:00*`). El dashboard ya la convierte a "24 may 2026" (es-MX); la CLI no.
- Los **totales mezclan marcas de naturaleza muy distinta** (UnoTV noticias vs. Nación Gamer)
  en un solo "Engagement 1.8%". Es correcto pero puede malinterpretarse; falta una nota de
  contexto ("el engagement global mezcla noticias y entretenimiento; mira el ranking por marca").

**`doctor.py`**
- Bien orientado a no técnicos: cabecera tranquilizadora, ✅/⚠️/❌, resumen final con conteos.
- **Friccion:** con la fuente de muestra arroja **7 ⚠️** (config + 5 credenciales + cuentas). La
  cabecera dice "✅ Todo listo para la demo… los avisos son normales", lo cual está bien, pero la
  lista de 7 avisos amarillos puede asustar igual a alguien no técnico. Faltaría **agrupar los 5
  avisos de credenciales en una sola línea** ("Credenciales: 0/5 plataformas conectadas — normal
  con datos de muestra").
- **No hay un "siguiente paso" accionable.** El doctor diagnostica, pero no cierra con "para usar
  datos reales, corre `python -m keni_metricas.asistente`". Un CM que ve todo en ⚠️ no sabe qué
  hacer después.

**`notificaciones.py`**
- Es seguro (safe-by-default, cero red sin `--enviar`). Pero la **salida de preview es confusa
  de leer**: por orden de stdout/stderr, la línea "# Para enviar de verdad…" aparece **antes** del
  encabezado "# PREVIEW notificacion", y luego vuelca un **JSON gigante** (el digest entero con
  `picos.alertas` repetido). Para un humano, el preview debería ser el **texto legible** del
  digest, no el JSON crudo; el JSON sirve para máquinas, no para que el CM "vea qué se enviaría".

**`asistente.py`**
- El flujo guiado es la pieza clave para usuarios no técnicos y está bien pensado (enmascarado de
  tokens, placeholders, merge no destructivo, escritura atómica 0600, guía de credenciales por
  plataforma con enlaces a docs).
- **Fricciones:**
  - **Sin sentido de progreso:** no dice "paso 1 de 4". El CM no sabe cuánto falta.
  - **No hay recap final tras escribir:** confirma "Escrito <ruta>" pero no dice "qué hago ahora"
    (ej. "corre `python -m keni_metricas.doctor` para verificar" o "ya puedes pedir métricas a
    Claude"). El asistente termina en seco.
  - **Las marcas de la fuente `muestra` y las que declara el CM no se reconcilian.** Si el CM
    declara `claro_sports` pero sigue en fuente `muestra`, sus handles no se usan (la muestra trae
    sus propias marcas). No se le advierte de esa desconexión.
  - La guía de credenciales es **densa y técnica** ("System User de Business Manager",
    "scope yt-analytics.readonly", "tier de pago"). Necesario, pero para un CM es jerga; convendría
    un "no lo tengo a la mano → déjalo vacío y pídeselo a tu admin" más explícito en cada bloque
    (hoy solo se dice una vez al inicio de la sección de credenciales).

### 1.3 Onboarding (asistente + instalación del plugin)

- **Instalación del plugin (`README.md`):** clara, "dos comandos", sin admin. Bien. Pero asume que
  el CM ya tiene **Claude Code instalado y `gh auth login` hecho** y que el repo privado le da
  acceso. Para un no técnico, "estar autenticado con GitHub" es un muro potencial sin captura de
  pantalla ni "cómo sé si ya estoy autenticado".
- El README distingue bien que "las skills funcionan solas" y que las métricas necesitan `uv`/`uvx`
  + credenciales. Pero el **camino feliz del primer día** está repartido entre tres archivos
  (`README.md`, `mcp-metricas/README.md`, `docs/guia-community-manager.md`). No hay un único
  "Empieza aquí en 10 minutos" para el CM.
- **No hay verificación post-instalación guiada:** tras instalar el plugin, el camino natural sería
  "corre `/keni-social:keni-doctor` para confirmar que todo está listo", pero el README no lo
  enlaza como primer paso.

### 1.4 Dashboard HTML (`dashboard.py`)

**Recién pulido y es la superficie más fuerte del producto.** Verificado generándolo y
renderizándolo (Chrome headless) con la fuente `muestra`:

- Branding Keni (eyebrow "KENI AI · AMX Contenido", borde de acento naranja), KPIs en tarjetas,
  hero de engagement north-star con leyenda de chips de color, ranking por marca con barras y
  nivel (alto/ok/bajo), sparklines de tendencia inline, fecha es-MX ("24 may 2026"), callout
  "🔥 Lo que más rompió este mes", picos colapsados (6 + "ver todas"), aviso de cobertura.
  Todo autocontenido, sin JS/CDN/red, escapado contra inyección. Excelente base.

**Fricciones / oportunidades (no bugs)**
- **El callout "Lo que más rompió" elige por engagement % absoluto**, lo que favorece a marcas
  pequeñas (en la muestra gana Piso 15 con 11.3% por encima de UnoTV). Para Bernardo, "lo que
  rompió" probablemente debería ponderar también el volumen (vis/alcance), o al menos aclarar
  "mayor engagement %" para no sugerir que Piso 15 fue lo más importante del mes en absoluto.
- **No hay forma de exportar/compartir** más allá de "abre el HTML". Para llevarlo a una junta o a
  Bernardo, falta un botón "imprimir/PDF" (CSS `@media print`) o un encabezado pensado para PDF.
- **El dashboard no enlaza de vuelta a la acción.** Muestra qué rinde, pero no sugiere "y ahora
  pídele a Claude copy para TikTok de Claro Sports, que es lo que funciona". El loop
  métricas→copy existe en las skills pero el dashboard no lo insinúa.
- **Sin estado vacío real:** con `muestra` siempre hay datos. Falta diseñar qué se ve cuando una
  marca no tiene datos en el periodo o cuando la cobertura es 0 (hoy el aviso es texto, pero la
  tarjeta podría quedar confusa).
- El modo `--presentacion` existe (sube escala tipográfica) pero **no está documentado para el CM**
  (solo en el `--help`); es justo lo que Bernardo querría en una sala proyectada.

### 1.5 Guía para community managers (`docs/guia-community-manager.md`)

- **Es la mejor pieza de onboarding del repo.** Lenguaje sin jerga, por tareas ("Lo que escribes /
  Lo que recibes"), explica la auto-verificación y un "Qué NO hace todavía" honesto. Modelo a
  seguir para el resto de la documentación.
- **Fricciones:**
  - Usa `claro-sports` (guion) mientras el reporte/dashboard muestran `claro_sports` (guion_bajo):
    el CM verá dos ortografías de la misma marca según la superficie (ver 1.1).
  - **No cubre las métricas como CLI/dashboard** ni el doctor/asistente: solo cubre las tools MCP
    por conversación. Un CM que prefiera el dashboard HTML no encuentra aquí cómo generarlo.
  - No incluye la leyenda ✅/⚠️/❌ como tarjeta de referencia rápida imprimible (está en prosa).

---

## 2. Tabla priorizada

Esfuerzo: **S** (≤ medio día) · **M** (1–2 días) · **L** (3+ días o requiere diseño).
Impacto: en el usuario no técnico (CM) y en Bernardo.

| # | Mejora | Superficie / archivo | Impacto | Esfuerzo | Ola |
|---|---|---|---|---|---|
| 1 | Semáforo de veredicto + leyenda ✅/⚠️/❌ **al inicio** de la salida de cada skill | `skills-copy/.claude/skills/*/SKILL.md` | Alto | S | 1 |
| 2 | Unificar ortografía de marcas (`claro-sports` vs `claro_sports`) en TODAS las superficies | guía, skills, reporte, dashboard, config | Alto | M | 1 |
| 3 | Resumen de picos: top 3 + colapsar el resto en CLI y notificaciones (como ya hace el dashboard) | `reporte.py`, `notificaciones.py`, `picos.py` | Alto | M | 1 |
| 4 | Preview de notificación legible (texto, no JSON) y arreglar orden stdout/stderr | `notificaciones.py` | Medio | S | 1 |
| 5 | Doctor: agrupar credenciales en 1 línea + cerrar con "siguiente paso" accionable | `doctor.py` | Alto | S | 1 |
| 6 | Asistente: indicador de progreso ("paso X de 4") + recap final con próximo paso | `asistente.py` | Alto | M | 1 |
| 7 | Fecha es-MX en el encabezado del reporte CLI (reusar la lógica del dashboard) | `reporte.py` | Bajo | S | 1 |
| 8 | "Empieza aquí en 10 min": un único quick-start para el CM que enlaza doctor como paso 1 | `README.md`, `docs/` | Alto | M | 2 |
| 9 | Dashboard: exportable a PDF/impresión (`@media print`) + documentar `--presentacion` | `dashboard.py`, guía | Medio | M | 2 |
| 10 | Callout "lo que rompió": aclarar criterio (engagement %) o ponderar por volumen | `dashboard.py` | Medio | M | 2 |
| 11 | Loop de vuelta a la acción: dashboard/reporte sugieren "pide copy para X que es lo que rinde" | `dashboard.py`, `reporte.py` | Medio | M | 2 |
| 12 | Tarjeta de referencia ✅/⚠️/❌ + sección de métricas (dashboard/doctor) en la guía del CM | `docs/guia-community-manager.md` | Medio | S | 2 |
| 13 | Guía de credenciales menos técnica: "no lo tengo → vacío y pídeselo a tu admin" por bloque | `asistente.py` | Medio | S | 2 |
| 14 | Conteo de caracteres con indicador visual estandarizado (cabe/no cabe) garantizado por producto | `plataformas.md`, `contar.py` | Bajo | M | 3 |
| 15 | Estados vacíos del dashboard (marca sin datos / cobertura 0) diseñados explícitamente | `dashboard.py` | Bajo | M | 3 |
| 16 | Selección de marca asistida (lista en vez de id memorizado) para invocar skills | comandos `/`, skills | Alto | L | 3 |
| 17 | Reconciliar marcas declaradas en el asistente con la fuente activa (avisar si `muestra`) | `asistente.py`, `doctor.py` | Medio | M | 3 |

---

## 3. El "norte" de experiencia (principios UX del producto)

Estos principios deben guiar cualquier decisión de rediseño. Derivan de la filosofía
"la IA produce y verifica, el humano aprueba" y de la audiencia (CM no técnico + Bernardo).

1. **El veredicto primero.** Lo más accionable —¿puedo aprobar esto? ¿qué miro hoy?— va arriba
   y en una línea. El detalle viene después, para quien quiera profundizar. Nadie debería hacer
   scroll para saber si una pieza está lista.

2. **Confianza calibrada y visible.** Todo lo que la IA produce dice **cuándo creerle**:
   ✅ confía, ⚠️ confírmalo tú, ❌ hay un problema. La leyenda viaja con la salida, no vive solo
   en un doc. El producto enseña al CM a ser el aprobador, no a delegar a ciegas.

3. **Una sola voz, una sola ortografía.** Una marca se escribe igual en todas las superficies.
   El mismo concepto (engagement, alcance, "lo que rompió") se nombra y formatea igual en skill,
   CLI, dashboard y guía. La consistencia es lo que hace que un no técnico confíe en el sistema.

4. **Español de México, siempre.** Fechas (24 may 2026), separadores de miles, tono. Cero ISO
   crudo, cero jerga de prensa española, cero inglés técnico filtrándose a la cara del usuario.

5. **Señal sobre ruido.** Lo importante es poco y destaca; lo demás se colapsa o se resume.
   24 alertas iguales no son información: 3 que importan + "ver todas" sí lo son.

6. **Seguro por defecto, y que se note.** Dry-run y "nada se ha publicado/enviado" no son letra
   pequeña: son una promesa visible que reduce el miedo del CM a "romper algo". El humano siempre
   tiene el último clic.

7. **Cada pantalla termina con el siguiente paso.** Diagnosticar sin decir qué hacer es dejar al
   no técnico a medias. El doctor, el asistente y el dashboard cierran señalando la acción
   siguiente, cerrando el loop hacia "produce → verifica → aprueba → publica → mide → vuelve a producir".

8. **Onboarding por tareas, no por arquitectura.** El CM aprende "cómo saco copy de una nota",
   no "qué es un MCP". La `guia-community-manager.md` es el patrón: replicarlo en todo el
   material de cara al usuario.

---

## 4. Las 5 mejoras top para la próxima ola

Selección priorizada por impacto/esfuerzo para el usuario no técnico. Detalle suficiente para
implementarlas sin re-investigar.

### Top 1 — Semáforo de veredicto + leyenda al inicio de cada skill (Esfuerzo S, Impacto Alto)

**Problema.** El veredicto (`LISTO PARA APROBAR` / `LISTO TRAS VERIFICAR`) y el checklist
✅/⚠️/❌ viven al **final** de una salida larga (5 variantes + posible hilo/carrusel). El CM debe
hacer scroll para saber si puede aprobar, y los símbolos no traen leyenda en la propia salida.

**Qué hacer.** Editar las plantillas de las skills que producen copy
(`copy-desde-nota`, `clip-a-copy`, `publica-preview`, `revisa-imagen`) para que **empiecen** la
salida con un bloque de cabecera de una/dos líneas:
- Un **semáforo de veredicto** anticipado: `🟢 Listo para aprobar` / `🟡 Listo tras verificar: <lista corta>` / `🔴 No publicar todavía: <motivo>`.
- Una **mini-leyenda** recurrente: `✅ confía · ⚠️ confírmalo tú (no es que esté mal) · ❌ problema`.
El checklist detallado se mantiene al final (no se elimina): la cabecera es un resumen, el pie
es la evidencia.

**Dónde.** Sección de pasos / formato de salida de cada `SKILL.md`. Añadir una instrucción
explícita "abre SIEMPRE con el semáforo y la leyenda; cierra con el checklist completo".

**Criterio de éxito.** Un CM ve en la primera línea si puede publicar y qué significan los
símbolos, sin leer la guía ni hacer scroll.

### Top 2 — Unificar la ortografía de las marcas en todas las superficies (Esfuerzo M, Impacto Alto)

**Problema.** La guía y las skills usan `claro-sports` (guion); el reporte, el dashboard y la
config usan `claro_sports` (guion_bajo). El mismo CM ve dos nombres para la misma marca según la
pantalla, lo que erosiona la confianza y provoca errores al invocar skills.

**Qué hacer.** Decidir **una** convención canónica de cara al usuario (recomendado: el guion
`claro-sports`, más legible y ya usado en la guía y en los ejemplos de invocación) y:
- Mantener internamente el id técnico que use el código (`normalizar_id_marca` produce
  guion_bajo), pero **mostrar siempre el nombre legible de la marca** (`nombre`, no `id`) en toda
  salida de cara al usuario: reporte CLI, encabezados, alertas y guía. El dashboard ya usa
  `nombres.get(cuenta_id, cuenta_id)` — el reporte CLI y las alertas no (imprimen `r['cuenta']`,
  el id crudo). Alinear el reporte/picos para que muestren el nombre legible como hace el dashboard.
- Donde el id deba aparecer (invocar skills), documentar **un único formato** y que coincida en
  guía, README y ejemplos.

**Dónde.** `reporte.py` (`render_markdown`, `_render_alerta`), `picos.py` (texto de alertas),
`docs/guia-community-manager.md`, `README.md`. Verificar contra los ejemplos de las skills.

**Criterio de éxito.** Buscar "claro_sports" y "claro-sports" en lo que ve el usuario y que solo
aparezca la forma canónica (o el nombre legible "Claro Sports").

### Top 3 — Resumen de picos: top 3 + colapsar el resto (CLI y notificaciones) (Esfuerzo M, Impacto Alto)

**Problema.** El reporte CLI con `--picos` vuelca **24 alertas** planas; la notificación semanal,
**29**, además como **JSON crudo**. Es un muro ilegible. El dashboard ya resuelve esto colapsando
a 6 + "ver todas", pero esa mejora no llegó a la CLI ni al digest.

**Qué hacer.**
- En `picos.render_markdown` (o en quien renderiza para CLI), **encabezar con las 3 alertas más
  fuertes** ("Lo que más rompió: …") y colapsar el resto bajo un "y N alertas más" (en CLI, una
  línea-resumen; el detalle completo solo con un flag `--todas` o en el JSON).
- En `notificaciones._texto_digest`, que el **preview legible** muestre el resumen (totales + top
  3 picos en texto), no el JSON completo. El JSON queda para el `--enviar`/consumo de máquina.

**Dónde.** `picos.py` (render), `reporte.py` (`--picos` append), `notificaciones.py`
(`_texto_digest`, y el `main` de preview).

**Criterio de éxito.** Un CM/Bernardo lee "lo que importa esta semana" en ≤ 5 líneas; el detalle
exhaustivo sigue disponible bajo demanda.

### Top 4 — Doctor: agrupar credenciales + cerrar con el siguiente paso (Esfuerzo S, Impacto Alto)

**Problema.** Con la fuente de muestra el doctor muestra **7 ⚠️** (incluyendo 5 líneas de
credenciales casi idénticas), lo que puede asustar a un no técnico pese a la cabecera
tranquilizadora. Y **no dice qué hacer después**: diagnostica y termina.

**Qué hacer.**
- En `renderizar`/`comprobar_credenciales`, **colapsar las 5 líneas de credenciales en UNA**:
  `⚠️ Credenciales: 0/5 plataformas conectadas (normal con datos de muestra)`, con el detalle por
  plataforma solo en `extra`/modo verboso.
- Añadir al cierre de `resumen_humano`/`renderizar` un **siguiente paso accionable** según el
  estado: si hay ❌, qué arreglar (ya existe parcialmente); si todo ⚠️ con muestra, "Para usar
  datos reales corre `python -m keni_metricas.asistente`"; si todo ✅ real, "Listo, pídele
  métricas a Claude o genera el dashboard con `/keni-social:keni-dashboard`".

**Dónde.** `doctor.py` (`comprobar_credenciales`, `renderizar`, `resumen_humano`).

**Criterio de éxito.** El doctor cabe en una pantalla, no asusta, y el CM sabe exactamente cuál es
su próximo movimiento.

### Top 5 — Asistente: progreso + recap final con el siguiente paso (Esfuerzo M, Impacto Alto)

**Problema.** El asistente es la puerta de entrada para el no técnico, pero no da **sensación de
progreso** ("paso X de Y") ni cierra con un **recap accionable**: tras "Escrito <ruta>" el CM se
queda sin saber qué sigue. Tampoco advierte si declaró marcas pero sigue en fuente `muestra`
(sus handles no se usarán).

**Qué hacer.**
- En `flujo_interactivo`, prefijar cada sección con un indicador `Paso 1/4 · Fuente`,
  `Paso 2/4 · Marcas`, etc. (la capa interactiva ya está separada de la lógica pura, así que es
  cosméticamente seguro).
- Tras `escribir_config_atomico`, imprimir un **recap final**: qué se guardó (resumen ya existe),
  **dónde**, y el **próximo paso**: "Verifica con `python -m keni_metricas.doctor`" y, si la fuente
  quedó en `muestra` pero declaró credenciales/handles reales, avisar "estás en datos de muestra:
  cambia a fuente real cuando tengas los tokens".
- En cada bloque de credenciales, reforzar el "no lo tengo → déjalo vacío y pídeselo a tu admin"
  (hoy se dice una vez al inicio de la sección).

**Dónde.** `asistente.py` (`flujo_interactivo`, `main`).

**Criterio de éxito.** Un CM completa el asistente sin perderse, sabe que terminó, y sale con una
instrucción clara de verificación.

---

*Generado como evaluación heurística read-only. Ninguna mejora se implementó en este pase: este
documento alimenta la planificación de la ola de rediseño. Las olas 2 y 3 (tabla §2) recogen el
resto de oportunidades por orden de impacto/esfuerzo.*
