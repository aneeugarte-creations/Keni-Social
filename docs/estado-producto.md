# Estado del producto — keni-social

Panorama honesto para dirección. Complementa el
[`resumen-para-direccion.md`](resumen-para-direccion.md) con el detalle de qué está construido,
qué está pausado por causas externas, y qué falta para tener un producto vendible a AMX.

> **Marco de honestidad.** keni-social está en **beta**: producto real en uso con AMX Contenido
> (UnoTV, Claro Sports, Nación Gamer, Piso 15, Fundación). Lo que sigue distingue con cuidado lo
> construido y verificado de lo que aún no (bloqueado por aprobaciones externas de plataforma).

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
  picos. **Hoy funciona con datos de muestra** representativos de las cinco marcas.
- **Preview de publicación en dry-run.** Muestra exactamente qué se publicaría en cada red sin
  publicar ni subir media.
- **Instalación como plugin de Claude Code.** Dos comandos, sin permisos de administrador, con
  comandos `/` que envuelven los flujos comunes y un asistente guiado para configurar las métricas.
- **Documentación de dirección, ventas y operación.** Resumen, análisis competitivo, roadmap de
  UX, guía del community manager, manual de operación, flujo de datos / privacidad, despliegue
  local y alojado.
- **Calidad verificada.** **338 pruebas automatizadas** del MCP (más chequeos estáticos de las
  skills) y **CI en verde** en cada cambio.

Arquitectura y hitos al detalle en [`arquitectura.md`](arquitectura.md).

## 2. Qué está PAUSADO (por gating externo)

Lo que falta para *datos reales* y *publicación real* **no depende de nosotros**: depende de
aprobaciones y costes de las plataformas. El **código de los adaptadores ya existe** y degrada
con elegancia cuando no hay credenciales; lo que está bloqueado es el permiso para encenderlos.

| Capacidad | Bloqueo externo | Estado |
|---|---|---|
| Métricas y publicación reales de **Meta** (FB/IG) | App Review / Advanced Access de Meta | En espera de aprobación |
| Métricas reales de **TikTok** | Auditoría de TikTok | En espera de aprobación |
| Métricas reales de **X** | Tier de pago de la API | Decisión de coste pendiente |
| Métricas reales de **YouTube** | Cuota diaria de la API (gestionable) | Ampliable cuando haga falta |

Detalle operativo en [`credenciales.md`](credenciales.md); timelines y riesgos asociados en
[`analisis-competitivo.md`](analisis-competitivo.md) §4. **Importante: la oferta de lo listo
(§1) no depende de ninguno de estos permisos**, así que el piloto genera valor sin esperar a Meta.

## 3. El camino a PRODUCTO vendible a AMX

La estrategia es **complementar, no reemplazar** al incumbente (AMX ya tiene Metricool): entrar
por el hueco diario del community manager, no por la analítica/publicación de primera. Por fases,
alineadas al estado real (detalle en [`analisis-competitivo.md`](analisis-competitivo.md) §3 y §5):

1. **Fase 0 — vender lo listo (hoy).** Copy desde texto, clip→copy local, métricas-insight con
   muestra y preview dry-run. No depende de ninguna aprobación: es lo que se demuestra y se cobra.
2. **Fase 1 — datos reales y modo alojado.** Conforme caen los permisos (§2): métricas reales por
   marca y el modo alojado por Keni con **System User de Meta (tokens que no caducan)**, que ataca
   de frente las desconexiones de Metricool. Cada hito que cae es un upsell natural, no una
   promesa que devalúe la venta inicial.
3. **Fase 2 — publicación y siguientes mejoras de UX.** Publicación real tras App Review y las
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
- **Dependencia de aprobaciones externas** (§2) para datos y publicación reales. *Mitigación:* la
  oferta de Fase 0 no depende de ellas; no prometer fechas de publicación que no controlamos.
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

*Documento de estado. Honesto sobre lo que está construido y verificado frente a lo que aún está
bloqueado por gating externo. Se actualiza conforme caen los hitos de la §2.*
