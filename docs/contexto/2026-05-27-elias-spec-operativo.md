# Especificación operativa — convergencia del rol de Elías (Claro Sports / UnoTV)

- **Fecha:** 2026-05-27 · **Estado:** borrador para revisar **con Elías** antes de abrir issues.
- **Fuente:** `03-entrega/.../transcripciones/elias/elias-convergencia.txt` (consolidado de 4 audios:
  rutina semanal, flujos del equipo, diseño/video/comercial, y lo que le gustaría construir).
- **Para qué:** traducir el día a día y los deseos de Elías en **features precisas y verificables**,
  separando con claridad lo que **construimos** (operativo) de lo que **queda en el equipo** (creativo).

---

## 0. Principio rector (la frontera)

> **keni-social genera, consolida y distribuye el trabajo operativo. El equipo aprueba, decide la
> estrategia y selecciona lo que más le gusta.**

Es la misma filosofía ya escrita en el producto —*"la IA produce y verifica; el humano aprueba"*
(`docs/ux-roadmap.md` §3)— aplicada al rol de Elías. En concreto:

| keni-social SÍ hace (operativo, automatizable) | El equipo decide (creativo, estratégico) |
|---|---|
| Ingesta, transcripción local, primera versión de copy | Aprobar y publicar el contenido final (último clic humano) |
| Consolidar métricas y armar reportes (lunes, mensual, comercial) | Elegir **qué** se cubre y la línea editorial/estrategia |
| Detectar y **señalar** typos, datos sospechosos, salidas de marca | Seleccionar las mejores piezas y qué arte gusta más |
| Proponer la rota de horarios y consolidar pendientes del equipo | Dirección creativa de montajes (la idea original) y asignaciones finales |
| Vigilar tendencias y **surface** lo más viral del momento | Decidir si una tendencia es relevante para el público |

Regla práctica para clasificar cualquier feature nueva: **si la salida necesita gusto, criterio
editorial o responsabilidad legal/comercial, es del equipo; si es recolectar, transformar,
consolidar o distribuir, es nuestra.**

---

## 1. Mapa: necesidad de Elías → clase → estado

Clase: **OP** = operativo (lo construimos) · **CR** = creativo (del equipo) · **MX** = mixto
(construimos el andamiaje, el equipo decide). Estado: ✅ existe · 🟡 parcial · 🔴 nuevo.

| # | Necesidad (bloque del transcript) | Clase | Estado | Dónde vive / feature |
|---|---|---|---|---|
| 1 | Reporte del lunes 10:00 — mejores resultados de los últimos 7 días (incl. domingo), 3 por red, vis+interacciones (B1) | OP | 🟡 | Reporte deportes (`/reporte-deportes`) → **F1** |
| 2 | "Lo que se viene": eventos, transmisiones, cómo se cubre (B1) | MX | 🟡 | Agenda editorial del deck → **F1** |
| 3 | Junta editorial 11:30 — temas relevantes del día + coberturas de reporteros (B1) | OP | 🟡 | skill `brief-matutino` → **F2** |
| 4 | Poner la parrilla en **Magnify** para el clipeo de transmisiones (B1) | OP | 🔴 | sin cubrir → **F8 (spike)** |
| 5 | Revisar copy del community: ortografía, typos, ajuste de marca, datos malos (B2) | OP | 🟡 | veredicto de skills, pero no sobre texto ajeno → **F3** |
| 6 | Revisar diseño: dato mal, fuera de foco, muy oscuro, titulares (B2) | MX | ✅ | skill `revisa-imagen` (dirige el equipo) |
| 7 | Estructura semanal a los community: contenidos y eventos planeados (B2) | OP | ✅/🟡 | `calendario-editorial` + Pendientes → **F5** |
| 8 | **Horarios del equipo en Excel, rotando sábados, ver semana próxima** (B2+B4) | OP | 🔴 | sin cubrir → **F4** |
| 9 | Artes/montajes creativos (p. ej. doble trofeo) (B3) | CR | n/a | dirección del equipo; `diseno-*` solo asiste |
| 10 | Análisis diario de redes: qué números y **por qué**, qué tan rápido salimos (B3) | OP | 🟡 | Métricas + `comparar_periodos` → **F6** |
| 11 | Análisis mensual de Mariana, comparar mes vs. mes, coyuntura (B3) | OP | ✅ | `comparar_periodos` + `tendencia_historica` |
| 12 | Comercial: reporte de impacto para vender + seguimiento de pautas (B3) | OP | ✅ | página Comercial |
| 13 | App de equipo con **pendientes diarios** compartidos (B4) | OP | 🟡 | Pendientes (single-user hoy) → **F5** (dep. #130) |
| 14 | **Rastreo: lo más viral del momento en todas las redes** (B4) | MX | 🟡 | Termómetro/`resumen-tendencia` no lo hacen → **F7** |
| 15 | Creación de copies, incl. "meter un link y que lo genere" (B4) | OP | ✅/🟡 | Generar copy → **F9 (enhance: desde URL)** |
| 16 | Creación de imágenes / "dame el layout" (B4) | MX | ✅ | Imágenes / `estudio-imagen` (equipo aprueba) |
| 17 | Que el equipo vea con anticipación su horario de la próxima semana (B4) | OP | 🔴 | = **F4** (vista del equipo) |

**Conclusión:** lo creativo (#6 dirige, #9, #16) ya está bien encuadrado como asistencia, no
sustitución. Los huecos operativos reales a abrir como issues son **F1–F9** abajo. F4 y F7 son
los más nuevos y de mayor impacto; F1/F2/F6/F9 son mejoras a piezas existentes.

---

## 2. Especificaciones por feature

Cada ficha es contractual: define entrada, salida, **qué queda en el equipo** y **criterios de
aceptación verificables**. El "estado" indica si nace, se amplía o ya existe.

### F1 · Reporte del lunes (consolidación 7 días + agenda + cuentas hermanas)
- **Necesidad (B1):** "Los lunes... presentar a las 10 los mejores resultados de los últimos 7 días,
  incluidos los del domingo... 3 de Instagram, 3 de Facebook y 3 de TikTok... y lo que se viene."
- **Objetivo:** un solo comando/clic produce el deck del lunes sin armarlo a mano en Canva.
- **Keni hace:** consolida vis+interacciones de los últimos 7 días (rango que **incluye el domingo**),
  top-3 por red con link, sección de cuentas hermanas (Claro Sports TV, Csport Golf) y plantilla de
  agenda de la próxima semana.
- **Queda en el equipo:** rellenar/curar la agenda (qué eventos, cómo se cubren) y aprobar el deck.
- **Entrada:** rango `semana` (lun–dom), agenda TOML opcional. **Salida:** `.pptx` (+PDF si hay LibreOffice).
- **Dónde encaja / estado:** `reporte_deck.py` + página "Reporte deportes" — **🟡 ya existe**; falta
  (a) garantizar el rango lun–dom incluyendo domingo, (b) la sección de cuentas hermanas con datos
  reales (hoy muestra), (c) export PDF nativo sin LibreOffice.
- **Aceptación:**
  - [ ] El rango por defecto del lunes cubre lunes→domingo de la semana cerrada.
  - [ ] Cada lámina lista top-3 por red con vis, interacciones y link clicable.
  - [ ] Hay lámina de cuentas hermanas y lámina de agenda (curable a mano).
  - [ ] Genera `.pptx` válido con la línea visual de Claro Sports.
- **Fuera de alcance:** elegir cuáles piezas destacar más allá del criterio vis+interacciones
  (eso lo ajusta el equipo). **Gating:** datos reales dependen de Meta/TikTok (Fase 1).

### F2 · Brief editorial de las 11:30 (temas del día + coberturas)
- **Necesidad (B1):** "junta editorial para ver los temas más relevantes del día, si ya los
  trabajamos o no, y las coberturas de los reporteros... anticiparnos a las entrevistas."
- **Objetivo:** llegar a la junta con un brief ya armado de qué está pasando y qué hay pendiente.
- **Keni hace:** consolida temas relevantes del día (de fuentes RSS + tendencias) y los cruza con
  lo ya publicado para marcar "ya trabajado / pendiente"; lista horarios de coberturas conocidas.
- **Queda en el equipo:** decidir el orden editorial, qué se cubre y a quién se asigna.
- **Entrada:** marca + fecha + fuentes configuradas. **Salida:** brief en pantalla/markdown.
- **Dónde encaja / estado:** skill `brief-matutino` — **🟡 existe**; falta el cruce "ya
  publicado/pendiente" contra el historial de copy y la lista de coberturas por horario.
- **Aceptación:**
  - [ ] El brief separa "temas calientes" de "ya trabajado por nosotros".
  - [ ] Incluye horarios conocidos de coberturas/entrevistas del día.
  - [ ] Corre por marca y respeta la franja de la junta (11:30).
- **Fuera de alcance:** decidir la parrilla del día.

### F3 · QA editorial sobre el texto del community manager
- **Necesidad (B2):** "yo tengo que estar revisando que no haya faltas ortográficas ni typos, y que
  editorialmente se ajuste a lo que hacemos en Claro Sports."
- **Objetivo:** que Elías no sea el corrector manual de cada posteo; el sistema señala, él aprueba.
- **Keni hace:** recibe el copy **ya escrito por el community** y devuelve un veredicto 🟢/🟡/🔴 con
  typos, ortografía, datos sospechosos (fechas/nombres/cifras), reglas legales (bandera con escudo,
  menores) y desviaciones de la voz de marca. **Señala; no reescribe sin permiso.**
- **Queda en el equipo:** aceptar/ignorar cada señalamiento y aprobar el texto final.
- **Entrada:** texto + marca + plataforma. **Salida:** veredicto + lista de hallazgos accionables.
- **Dónde encaja / estado:** reutiliza la auto-verificación de las skills de copy, pero en **modo
  revisión de texto ajeno** (hoy solo verifica lo que ella misma genera) — **🟡 nuevo modo**.
- **Aceptación:**
  - [ ] Abre con semáforo de veredicto + leyenda (consistente con el resto del producto).
  - [ ] Marca cada hallazgo con su tipo (ortografía / dato / legal / voz) y la corrección sugerida.
  - [ ] No publica ni modifica el texto: solo devuelve el informe.
  - [ ] Aplica las reglas legales ya conocidas del piloto.
- **Fuera de alcance:** reescribir el copy por su cuenta (puede ofrecer sugerencia, no imponerla).

### F4 · Parrilla y rota de horarios del equipo  ⭐ nuevo de alto impacto
- **Necesidad (B2+B4):** "los sábados los reparto rotando... todo esto se los dejo en un Excel, con
  los horarios de los partidos y de los eventos" + "que el equipo pueda ver con anticipación su
  horario de la próxima semana."
- **Objetivo:** sustituir el Excel manual por una vista de equipo que **propone** la rota y la hace
  visible con anticipación.
- **Keni hace:** dado el calendario de eventos/transmisiones y el equipo disponible, **propone** una
  rota que rota los sábados (evita repetir a la misma persona dos fines de semana seguidos) y la
  publica como vista de la próxima semana; consolida horarios de partidos/eventos y qué sacar de cada
  transmisión.
- **Queda en el equipo:** Elías ajusta y **aprueba** las asignaciones finales (puede forzar coberturas
  estratégicas que rompen la rotación).
- **Entrada:** lista de eventos con horario + miembros del equipo + restricciones. **Salida:** rota
  semanal editable + vista por persona ("tu próxima semana").
- **Dónde encaja / estado:** **🔴 nuevo**. Página de Consola de equipo; depende de multiusuario.
- **Aceptación:**
  - [ ] Propone rota que no repite sábado a la misma persona salvo override explícito.
  - [ ] Vincula cada turno a su evento/transmisión y a qué contenido sacar.
  - [ ] Cada miembro ve su semana próxima; Elías edita y aprueba antes de publicarla.
  - [ ] Exporta a un formato que el equipo ya usa (al menos `.xlsx`/CSV) durante la transición.
- **Fuera de alcance:** decidir prioridades estratégicas de cobertura (las fija Elías).
- **Dependencias:** **#130** (multiusuario) y se solapa con **#9** (Fase 3, scheduling/equipo).

### F5 · Pendientes compartidos del equipo (multiusuario)
- **Necesidad (B4):** "una app donde podamos trabajar todo el equipo y ver muchos de los pendientes
  que tenemos —tenemos pendientes diarios—."
- **Objetivo:** un tablero de pendientes que **todo el equipo** ve y actualiza, no una lista local.
- **Keni hace:** consolida pendientes por proyecto/marca, con estado, responsable y enlace a la
  acción (abrir en el asistente, generar copy, etc.).
- **Queda en el equipo:** crear, asignar y cerrar sus pendientes.
- **Dónde encaja / estado:** página **Pendientes** ya existe pero es **single-user** — **🟡 ampliar a
  multiusuario** (depende de **#130**).
- **Aceptación:**
  - [ ] Varios usuarios ven y editan los mismos pendientes con identidad propia.
  - [ ] Cada pendiente lleva responsable, estado y, si aplica, enlace a la acción.
  - [ ] Acotado por marca/proyecto según permisos.
- **Dependencias:** **#130** y **#9**.

### F6 · Análisis diario con el "por qué" (narrativa de métricas)
- **Necesidad (B3):** "analizo día a día las redes: qué números tuvimos y por qué... discernir si fue
  positivo o negativo, qué podemos mejorar."
- **Objetivo:** que el análisis no sea solo cifras, sino una lectura corta de qué subió/bajó y qué
  piezas lo explican.
- **Keni hace:** sobre las métricas del día, genera un resumen accionable: variación vs. periodo
  anterior, piezas que explican el pico, y el "siguiente paso" (loop a la acción del roadmap, ola 2).
- **Queda en el equipo:** la interpretación final y la decisión de qué cambiar.
- **Dónde encaja / estado:** `comparar_periodos` + `picos` + `mejores_piezas` ya dan los datos —
  **🟡 falta la capa narrativa** (alineada con UX-roadmap #11 "loop de vuelta a la acción").
- **Aceptación:**
  - [ ] Resume top movimientos del día con la(s) pieza(s) que los explican.
  - [ ] Cierra con una sugerencia accionable ("pide copy/clip de lo que rinde").
  - [ ] Marca explícitamente cuando los datos son muestra y no reales.
- **Fuera de alcance:** atribuir causas de coyuntura externas (las pone el humano).

### F7 · Radar de tendencias / lo más viral del momento  ⭐ nuevo de alto impacto
- **Necesidad (B4):** "ver las noticias y los videos más virales del momento en todas las redes
  sociales, ver de qué se está hablando y por qué, y publicarlo si es relevante."
- **Objetivo:** un radar que **trae y consolida** lo que está reventando ahora, multi-red, para que el
  equipo decida si entra.
- **Keni hace:** recoge y agrupa lo más viral del momento por tema (de las fuentes/APIs disponibles),
  con por qué está subiendo y enlaces; deduplica y prioriza por señal.
- **Queda en el equipo:** **seleccionar** qué es relevante para su público y publicarlo (frontera
  editorial; nosotros surface, ellos eligen).
- **Dónde encaja / estado:** **🟡/🔴 nuevo**. No lo cubre Termómetro (noticias internacionales
  curadas) ni `resumen-tendencia` (resume **una** tendencia dada) ni Verificación (¿es nuevo el
  video?). Es una superficie de **descubrimiento** distinta.
- **Aceptación:**
  - [ ] Lista temas/videos en tendencia ahora, agrupados y deduplicados, con enlace y "por qué sube".
  - [ ] Cubre varias redes según las fuentes disponibles, no una sola.
  - [ ] No publica nada: solo propone; el equipo marca lo relevante.
  - [ ] Degradación honesta: si una fuente no está disponible, lo dice (sin inventar).
- **Fuera de alcance:** decidir relevancia editorial (del equipo). **Gating:** cobertura real por red
  depende de qué APIs/fuentes haya (Fase 1).

### F8 · Hand-off de la parrilla a Magnify / clipeo  (spike)
- **Necesidad (B1):** "poner en Magnify la parrilla que vamos a llevar, para ir haciendo el clipeo de
  nuestras transmisiones."
- **Objetivo:** evitar recapturar a mano la parrilla en Magnify.
- **Keni hace (a investigar):** exportar la parrilla/agenda en el formato que Magnify acepte, o vía su
  API si existe.
- **Dónde encaja / estado:** **🔴 nuevo, investigación primero.** Abrir como *spike*: ¿Magnify tiene
  API/import? ¿qué formato? Sólo entonces decidir build.
- **Aceptación (del spike):**
  - [ ] Documentar si Magnify ofrece API/import y con qué formato.
  - [ ] Recomendar build / no-build con esfuerzo estimado.
- **Gating:** depende de Magnify (externo).

### F9 · Generar copy desde un link (enhance)
- **Necesidad (B4):** "probablemente poder meter un link para que genere un contenido."
- **Objetivo:** pegar una URL (nota/video) y obtener copy por plataforma, sin copiar el texto a mano.
- **Keni hace:** descarga/lee la fuente del link y la pasa a `copy-desde-nota`/`clip-a-copy`, marcando
  lo no verificado.
- **Queda en el equipo:** aprobar el copy resultante.
- **Dónde encaja / estado:** Generar copy ya existe; **🟡 falta el ingreso desde URL** como atajo.
- **Aceptación:**
  - [ ] Acepta una URL y produce las variantes por plataforma con su veredicto.
  - [ ] Trata el contenido extraído como no verificado y lo marca.
- **Fuera de alcance:** publicar; solo genera el borrador.

---

## 3. Issues en GitHub

**Creados el 2026-05-27** (#141–#149). El cuerpo de cada uno = la ficha F# de §2. Quedan en el
tablero para trackear; se ajustan o cierran según la revisión con Elías (§5).

| Ficha | Issue | Título | Labels | Relación |
|---|---|---|---|---|
| F1 | [#141](https://github.com/kenitech-io/keni-social/issues/141) | Reporte del lunes: rango lun–dom + cuentas hermanas reales + PDF nativo | enhancement, fase-1 | amplía `reporte_deck` |
| F2 | [#142](https://github.com/kenitech-io/keni-social/issues/142) | Brief de la junta 11:30: temas del día cruzados con "ya publicado / pendiente" | enhancement, fase-1 | amplía `brief-matutino` |
| F3 | [#143](https://github.com/kenitech-io/keni-social/issues/143) | QA editorial sobre texto del community (sin reescribir) | enhancement, fase-0 | reusa verificación |
| F4 | [#144](https://github.com/kenitech-io/keni-social/issues/144) | Parrilla y rota de horarios del equipo (rotación de sábados + "mi próxima semana") | enhancement, fase-3 | dep. #130, extiende #9 |
| F5 | [#145](https://github.com/kenitech-io/keni-social/issues/145) | Pendientes compartidos del equipo (multiusuario) | enhancement, arquitectura, fase-3 | dep. #130, extiende #9 |
| F6 | [#146](https://github.com/kenitech-io/keni-social/issues/146) | Análisis diario de métricas con narrativa "qué cambió y por qué" | enhancement, fase-1 | UX-roadmap #11 |
| F7 | [#147](https://github.com/kenitech-io/keni-social/issues/147) | Radar de tendencias: lo más viral del momento multi-red (descubrir, no publicar) | enhancement, investigacion, fase-1 | nuevo |
| F8 | [#148](https://github.com/kenitech-io/keni-social/issues/148) | Spike: ¿exportar la parrilla a Magnify? (API/formato de import) | investigacion, bloqueado-externo | externo |
| F9 | [#149](https://github.com/kenitech-io/keni-social/issues/149) | Generar copy desde una URL (link → copy por plataforma) | enhancement, fase-0 | atajo de copy |

---

## 4. Lo que NO construimos (frontera creativa, explícito)

Para revisar con Elías que estamos de acuerdo en dónde para la máquina:

- **Aprobar y publicar** el contenido final — siempre el último clic humano.
- **Definir la estrategia y la parrilla** de qué se cubre y cómo.
- **Seleccionar** las mejores piezas y qué arte/montaje gusta más.
- **Dirección creativa** de los montajes (la idea: doble trofeo, etc.) — `diseno-*` solo da el prompt
  y verifica contra la guía.
- **Asignaciones finales** de la rota — proponemos, Elías ajusta y aprueba.
- **Decidir relevancia editorial** de una tendencia — la surfaceamos, el equipo elige.

---

## 5. Preguntas para validar con Elías

1. **Rota (F4):** ¿qué campos lleva hoy tu Excel (persona, evento, horario, qué sacar)? ¿reglas de
   rotación además de "no dos sábados seguidos"? ¿cuántas personas en el equipo?
2. **QA editorial (F3):** ¿quieres solo el señalamiento, o también una sugerencia de corrección lista
   para aceptar? ¿qué reglas de marca son innegociables?
3. **Radar (F7):** ¿qué redes te importan más para "lo más viral del momento" y de qué cuentas/temas?
4. **Magnify (F8):** ¿cómo metes hoy la parrilla? ¿hay opción de importar archivo o solo a mano?
5. **Reporte lunes (F1):** ¿el deck actual ya te sirve o falta algo de forma/contenido?
6. **Prioridad:** de F1–F9, ¿cuáles tres te ahorrarían más horas esta semana?

---

*Especificación a partir de `elias-convergencia.txt`. Issues #141–#149 ya abiertos (§3); validar la
frontera (§1, §4) y las prioridades (§5) con Elías y ajustar/cerrar los que no sobrevivan.*
