# Estado del producto — keni-social

Panorama honesto para dirección. Complementa el
[`resumen-para-direccion.md`](resumen-para-direccion.md) con el detalle de qué está construido,
qué está pausado por causas externas, y qué falta para tener un producto vendible a AMX.

> **Marco de honestidad.** keni-social está en **beta**: producto real en uso con AMX Contenido
> (UnoTV, Claro Sports, Nación Gamer, Piso 15, Fundación). Lo que sigue distingue con cuidado lo
> construido y verificado de lo que aún queda por cablear (la publicación real vía Metricool).

---

## 1. Qué está LISTO hoy

Construido, probado y en uso, sin depender de ninguna aprobación externa.

- **Copy desde texto con tropicalización es-MX y auto-verificación.** A partir de una nota o
  varios cables, una variante por plataforma (X, Instagram, Facebook, TikTok, YouTube) con conteo
  de caracteres, en la voz de cada marca. La salida **abre con el semáforo de veredicto y su
  leyenda** (🟢 listo / 🟡 revísalo tú / 🔴 no publicar) antes del copy, y cierra con la
  auto-verificación detallada que marca fechas, nombres, cifras y reglas legales.
- **Clip → copy 100% local.** De un video o audio a copy por plataforma **más las mejores citas
  con marca de tiempo** (punto de corte exacto). La transcripción corre en la máquina con
  whisper.cpp; el audio no sale. El texto de transcripción se trata como **no verificado** y se
  marca para confirmar contra el audio.
- **Corpus editorial versionado.** Cinco marcas con su línea editorial + voz personal por persona
  + reglas de tropicalización + reglas legales. Es el moat (ver §4) y crece con el uso.
- **MCP de métricas multi-marca / multi-plataforma con dashboard.** Consolida marcas y plataformas
  (alcance, engagement, mejores piezas, comparación de periodos, tendencia histórica, picos), con
  histórico propio en SQLite local. Genera un **dashboard HTML autocontenido** (sin JS, sin CDN,
  sin red; se abre con doble clic y funciona offline) con KPIs, ranking por marca, sparklines y
  picos. Lee dato real **vía Metricool** (`FuenteMetricol`, API REST; AMX en plan Advanced) como
  una fuente más detrás de `FuenteMetricas`; sin token configurado **degrada a datos de muestra**
  representativos de las cinco marcas (nunca inventa cifras).
- **Catálogo de apps con fronteras verificadas (separación A/B/C + shell).** La Consola está
  organizada como catálogo de apps de producto (Producción · Métricas · Operación) + un shell
  transversal, cada una activable por flag, con un **lint de fronteras en CI** que impide que una
  app importe las tripas de otra (los cruces legítimos van por contratos explícitos). El sidebar se
  genera de los manifests y los tests corren con *scoping* por app. Decisión en
  [ADR 0005](adr/0005-agrupamiento-catalogo-por-unidad-de-producto.md); detalle en
  [`arquitectura.md`](arquitectura.md) §3.
- **Preview de publicación en dry-run.** Muestra exactamente qué se publicaría en cada red sin
  publicar ni subir media.
- **Lista viva multi-fuente (tablero + Panel-9am).** El tablero de contenidos es una lista
  priorizada que se alimenta de varias fuentes y deja el trabajo operativo adelantado hasta el
  punto de validación humana. Ya construido y probado (ver
  [`contexto/2026-05-31-lista-viva-angel.md`](contexto/2026-05-31-lista-viva-angel.md)): el
  **importador de calendario Excel/CSV** (H1) que sube los temas al tablero con prioridad, fecha y
  etiqueta de compromiso; la **auto-generación de copy** al entrar un tema de una fuente (H2, por
  el mismo pipeline que el botón manual, dejando el borrador en la cola de revisión; gated por
  `KENI_AUTOGEN`, **OFF por defecto**); el **score de prioridad dinámico** que re-ordena la vista
  del día sin alterar el orden del kanban compartido (H3); y el **Panel-9am**, la lista curada del
  día (`GET /api/panel/dia` + sección "Lista del día" en el panel) que reúne tablero ordenado por
  score con contadores por fuente y estado (H5). El humano sigue validando los checkpoints
  (aprobar copy, autorizar publicación). Queda como follow-up: auto-arte, anidar el borrador bajo
  el tema origen y "green"/"compromiso" como conceptos de primera clase.
- **Instalación como plugin de Claude Code.** Dos comandos, sin permisos de administrador, con
  comandos `/` que envuelven los flujos comunes y un asistente guiado para configurar las métricas.
- **Documentación de dirección, ventas y operación.** Resumen, análisis competitivo, roadmap de
  UX, guía del community manager, manual de operación, flujo de datos / privacidad, despliegue
  local y alojado.
- **Calidad verificada.** Amplia batería de pruebas automatizadas (MCP + Consola), con **CI
  self-hosted en Woodpecker** (`.woodpecker/`) que en cada push y pull request corre los tests de
  los tres paquetes Python y la construcción del bundle del frontend. No es una maqueta: lo que está
  listo, está probado. (El número exacto de pruebas vive en CI, no aquí, para no quedar desfasado.)

Arquitectura y hitos al detalle en [`arquitectura.md`](arquitectura.md).

## 2. Publicación real: construida y gateada (falta validar en producción)

**Ni las métricas ni la publicación reales dependen ya de aprobaciones externas.** Ambas llegan
**vía Metricool** (AMX en plan **Advanced**): una sola integración cubre Facebook, Instagram, X,
TikTok y YouTube, así que **Meta App Review, la verificación de negocio, la auditoría de TikTok y
el tier de pago de X dejan de ser bloqueantes**. Las métricas reales se leen con `FuenteMetricol`
(adapter detrás de `FuenteMetricas`; no construimos ingesta propia por plataforma, ver
[ADR 0005](adr/0005-agrupamiento-catalogo-por-unidad-de-producto.md) §B). La publicación real sale
por el **scheduler de Metricool**: el camino **ya está construido** en el programador de la Consola
(`programador.py`) y **gateado por `KENI_PUBLICAR_REAL` (OFF por defecto)**. Lo que queda no es
cablearlo, sino **validarlo en producción** con credenciales reales.

| Capacidad | Camino | Estado |
|---|---|---|
| Métricas reales (todas las redes) | Metricool API (plan Advanced) | Disponible vía Metricool (configurar token) |
| Publicación real (todas las redes) | Scheduler de Metricool, flag `KENI_PUBLICAR_REAL` | Construida y gateada OFF (dry-run por defecto); pendiente de validar en producción |

Detalle del camino de publicación en
[`plataformas/publicacion-metricool.md`](plataformas/publicacion-metricool.md); configuración de
tokens en [`credenciales.md`](credenciales.md). **La oferta de lo listo (§1) no depende de nada de
esto**: el piloto genera valor desde ya.

## 3. El camino a PRODUCTO vendible a AMX

La estrategia es **complementar, no reemplazar** al incumbente (AMX ya tiene Metricool): entrar
por el hueco diario del community manager, no por la analítica/publicación de primera. Por fases,
alineadas al estado real (detalle en [`analisis-competitivo.md`](analisis-competitivo.md) §3 y §5):

1. **Fase 0 — vender lo listo (hoy).** Copy desde texto, clip→copy local, **métricas-insight con
   dato real vía Metricool (Advanced)**, preview dry-run y la **lista viva multi-fuente**
   (tablero priorizado + importador de calendario H1 + auto-generación de copy H2 gated OFF +
   score dinámico H3 + Panel-9am H5; ver §1). No depende de aprobaciones externas: es lo que se
   demuestra y se cobra. Lo único que sigue pendiente es **validar en producción** la
   **publicación real** vía Metricool (ya construida y gateada OFF, Fase 1/2), no la lista ni la
   generación del borrador.
2. **Fase 1 — publicación real y modo alojado.** Las métricas reales por marca ya llegan vía
   Metricool (§1). Lo que entra aquí es **encender y validar en producción** la **publicación real**
   vía Metricool (ya construida y gateada OFF en el programador, sin espera externa) y el modo
   alojado por Keni con **System User de Meta (tokens que no caducan)**. Cada hito que cae es un
   upsell natural, no una promesa que devalúe la venta inicial.
3. **Fase 2 — publicación y siguientes mejoras de UX.** Publicación real vía Metricool y las
   mejoras priorizadas en [`ux-roadmap.md`](ux-roadmap.md) (olas 2 y 3): quick-start "empieza aquí
   en 10 min", dashboard exportable a PDF, loop de vuelta a la acción (el dashboard sugiere "pide
   copy para lo que rinde"), selección de marca asistida y estados vacíos. La ola 1 del roadmap
   (semáforo de veredicto al inicio, nombres de marca legibles, picos top-N, doctor y asistente
   accionables) **ya está implementada**.

**El moat que sostiene la venta** no es la tecnología (Claude + MCP + whisper.cpp es plomería
replicable), sino lo editorial: **corpus es-MX por marca + disciplina de verificación honesta +
privacidad verificable**. Eso crece con cada cliente y es propio e intransferible.

## 4. Riesgos y supuestos

- **Comoditización del MCP y del copy IA.** El mercado ya tiene MCP servers (incluido el de
  Metricool) y asistentes de copy en cada herramienta. *Mitigación:* vender el moat editorial, no
  la plomería.
- **Dependencia de Metricool** para datos y publicación reales (§2): si el cliente deja Metricool o
  cambia de plan, esa vía se corta. *Mitigación:* la oferta de Fase 0 no depende de ella; es una
  dependencia asumida, alineada con "complementar, no reemplazar", y el MCP construye histórico
  propio en SQLite local.
- **Dependencia del incumbente en el histórico.** Mientras Metricool tenga el histórico, el
  cliente no migra del todo. *Mitigación:* posicionarse como complemento aditivo y construir
  histórico propio (el MCP ya lo guarda en SQLite local).
- **Dependencia de plataforma (Anthropic).** El producto vive en Claude Code. *Mitigación:* el
  corpus y las voces son texto portable; el método no está atado al modelo.
- **Supuesto central a validar en el piloto:** que el copy es-MX + la verificación honesta + la
  privacidad local resuelven un dolor por el que AMX paga, y que la cuña es portátil al cliente
  nº2. Esto es justo lo que el piloto pone a prueba. (Riesgos al detalle en
  [`analisis-competitivo.md`](analisis-competitivo.md) §4.)

## 5. Métrica de éxito del piloto

La métrica norte del piloto es el **engagement** de las marcas de AMX (señalada por Mariana):
demostrar que el copy producido y verificado por el sistema sostiene o mejora el engagement frente
al flujo actual, mientras le devuelve horas al community manager (no reescribir copy, no
transcribir a mano, no consolidar métricas a mano). El piloto se considera validado si AMX adopta
el flujo en su día a día y el método queda documentado para replicarlo con el siguiente cliente.

---

*Documento de estado. Honesto sobre lo que está construido y verificado frente a lo que aún queda
por cablear (publicación real vía Metricool, §2). Se actualiza conforme caen los hitos.*
