# Go-to-market y pricing — keni-social

Documento de estrategia comercial para `keni-social`. Cliente de entrada: **AMX Contenido**
(UnoTV = noticias, Claro Sports = deporte, Nación Gamer, Piso 15, Fundación).

> **Nota sobre los precios.** Las cifras de pricing de este documento son una **propuesta**,
> no una lista de precios cerrada. Están ancladas a los precios de la categoría (mayo 2026) y
> al coste real de los insumos (asiento de Claude for Teams ≈ $30/mes). Marco los supuestos
> donde los hay. Antes de cotizar formalmente hay que validar volumen de puestos, marcas y modo
> de despliegue con el comprador.

---

## 1. Posicionamiento

**keni-social es la capa premium de copy + inteligencia editorial, privada y de verdad
mexicana, que se monta encima de lo que el equipo ya usa.** No entra a pelear la analítica ni
la publicación de primera; entra por donde la herramienta actual no llega.

El cliente ya tiene **Metricool**: fuerte en analítica, pero débil en copy con IA y sin español
de México real. Ahí está el hueco.

Estrategia de entrada en una frase: **complementar Metricool, no reemplazarlo.** Lideramos con
lo que Metricool no puede hacer —copy es-MX confiable a partir del propio video del equipo, con
verificación honesta, procesado en local— y, en métricas, nos **apoyamos** en Metricool: leemos
sus datos vía su API (plan Advanced) y añadimos encima la capa de insight, narrativa y reporte
es-MX. Metricool sigue siendo el tablero de métricas mientras nosotros demostramos valor. La
publicación llega después, por fases, cuando ya tenemos confianza ganada y los permisos externos
resueltos.

Qué decimos y qué no:

- **Sí decimos:** "Tu copy en español de México, en la voz de cada marca, sacado de tu propio
  video sin que el audio salga de tu máquina, y con una verificación que te dice cuándo creerle."
- **No decimos (todavía):** "Cámbiate de Metricool." Eso llega cuando publiquemos y programemos.

Por qué este orden importa comercialmente: pedirle al equipo que abandone su tablero de métricas
el día uno crea fricción de migración y resistencia. Pedirle que añada una capa de copy que les
quita el peor dolor diario (retropicalizar y sacar copy de videos) no le quita nada a nadie. Es
una venta aditiva, no una sustitución.

---

## 2. Comprador y cuña de entrada

### El comprador

**El departamento de Bernardo (Contenido Digital).** Tiene presupuesto propio y decide sobre su
gasto; **no es IT corporativo ni Compras**. Esto es deliberado y es lo que hace viable el piloto:
una compra departamental, acotada, sin pasar por el ciclo largo de procurement corporativo.

Dos perfiles de usuario/decisor a tener en cuenta:

- **Community managers (CM):** usuarios diarios. Su dolor es operativo y universal: retropicalizar
  copy y sacar piezas de video. Son quienes sienten el valor cada día.
- **Mariana y Bernardo:** consumen reportes y miden resultado. Mariana ha señalado el
  **engagement como métrica norte**. Para ellos el valor es visibilidad consolidada y decisión.

### La cuña (el dolor de entrada)

Entramos por el dolor que es **universal entre todos los CM** y que la herramienta actual no
resuelve:

1. **Copy + tropicalización es-MX.** El material llega con giros de España; hoy el CM lo rehace a
   mano. La skill lo tropicaliza en la voz de la marca, listo para revisar, no para reescribir.
2. **Video/audio → copy.** De una entrevista o declaración: copy por plataforma **más las mejores
   citas con marca de tiempo** (punto de corte exacto para el clip). El audio se transcribe en
   local y nunca sale de la máquina. Esto elimina el "escúchate la hora de podcast a ver qué sirve".
3. **Reportes para Mariana/Bernardo.** El MCP de métricas lee de Metricool (vía su API, plan
   Advanced) y consolida todas las marcas y plataformas en un informe con narrativa es-MX, avisa de
   picos/anomalías y marca la cobertura de los datos. Esto le da al nivel decisor una razón para
   querer la herramienta aunque no la toque a diario.

La cuña es deliberadamente lo más portátil del producto: estos dolores existen en **cualquier**
equipo de contenido, así que lo que validemos con AMX es replicable con el siguiente cliente.

---

## 3. Moat (por qué es difícil de copiar)

El moat **no es la tecnología** (Claude + MCP + whisper.cpp es plomería replicable) sino lo
**editorial**: corpus es-MX por marca + disciplina de verificación honesta + privacidad por
diseño, que se acumulan con cada cliente y son propios e intransferibles.

> **Fuente única:** el moat, el wedge y los diferenciadores defendibles viven en
> [`analisis-competitivo.md`](analisis-competitivo.md) §3 (con la tabla competidor × capacidad).
> No se repiten aquí para no divergir. Este documento usa el moat solo como **argumento de
> precio** (§4): vendemos la capa editorial, no el stack.

---

## 4. Pricing (propuesta)

> Recordatorio: **propuesta, no precio fijo.** Cifras en USD/mes. Hay que validar puestos y modo
> de despliegue antes de cotizar.

### Anclas de la categoría (mayo 2026)

| Referencia | Precio aprox. | Lectura |
|---|---|---|
| SMB (Buffer, Vista Social entrada) | $20–50/mes | Suelo de la categoría. |
| Agencia (Hootsuite ~$99/asiento, Sprout $199–399, Vista Social hasta $304) | $100–300/mes | Donde vive el comprador serio. |
| Enterprise / por asiento | $300–400+/asiento | Techo. |
| Jasper (IA copy, sin fact-check) | $39–59/asiento | Competidor directo en copy IA, **sin** verificación ni es-MX. |
| **Insumo: asiento Claude for Teams** | **≈ $30/asiento/mes** | Coste base que pasamos. El cliente lo necesita para correr las skills. |

### Estructura de coste (supuesto clave)

`keni-social` corre **dentro de Claude Code** del cliente. Eso significa que el cliente necesita
asientos de **Claude for Teams (≈ $30/asiento/mes)** como insumo. El cobro de Keni va **encima** de
ese coste, como margen por el producto editorial (corpus es-MX + verificación + skills + soporte +
el MCP).

> **Supuesto a confirmar:** quién paga los asientos de Claude. Dos caminos:
> (a) el cliente contrata Claude for Teams directo y Keni cobra solo su capa; o
> (b) Keni revende el asiento empaquetado. La propuesta de abajo asume **(a)** (precio Keni = capa
> editorial, asiento Claude aparte y a cargo del cliente) y, en paralelo, ofrece un precio
> "todo incluido" para quien prefiera no gestionar la suscripción de Claude.

### Modelo propuesto: por puesto + add-on de equipo/marca

Dos componentes:

- **Por puesto (CM):** cubre acceso a las skills de copy (texto + video→copy), tropicalización,
  voz personal, verificación y preview. Es el valor diario del operador.
- **Add-on de equipo/marca:** cubre el MCP de métricas consolidado (reporte multi-marca, picos,
  cobertura) y, en su fase, el despliegue alojado. Es el valor para Mariana/Bernardo y escala con
  el número de marcas, no de personas.

#### Opción de entrada — "Copy es-MX"

| Concepto | Precio Keni (capa) | + Insumo Claude | Total al cliente |
|---|---|---|---|
| **Por puesto CM** | **$45/puesto/mes** | + ~$30 (Claude for Teams) | **≈ $75/puesto/mes** |

- Incluye: las skills de copy (desde texto y desde video/audio), tropicalización es-MX, voz por
  marca + voz personal, verificación, `clip-a-copy` (video→copy local), preview en dry-run.
- No incluye: MCP de métricas alojado ni publicación (esta última no existe aún).
- **Lectura de ancla:** la capa Keni ($45) se sitúa cerca de Jasper ($39–59) pero entregando lo que
  Jasper no tiene (es-MX real + fact-check + local). El total al cliente (~$75) queda **por debajo
  del asiento de agencia** (Hootsuite/Sprout) y se justifica porque sustituye horas de reescritura.

#### Opción suite — "Contenido + Inteligencia"

| Concepto | Precio Keni (capa) | Nota |
|---|---|---|
| **Por puesto CM** | **$45/puesto/mes** | igual que entrada (+ asiento Claude). |
| **Add-on métricas/marca** | **$60/marca/mes** | MCP consolidado, picos, cobertura; modo alojado. |
| **Plataforma base (por equipo)** | **$300/mes** | soporte, mantenimiento del corpus editorial, MCP alojado (lectura de métricas vía Metricool API; publicación hosted con tokens System User), onboarding. |

**Ejemplo numérico para AMX** (5 CM, 5 marcas, suite, supuesto ilustrativo):

```
5 puestos CM      × $45  = $225  (capa Keni)
5 add-ons marca   × $60  = $300
plataforma base          = $300
                          ------
capa Keni / mes          = $825/mes
+ 5 asientos Claude × $30 = $150  (a cargo del cliente)
                          ------
total cliente            ≈ $975/mes
```

- **Lectura de ancla:** ~$975/mes para 5 marcas y 5 puestos cae dentro del rango de agencia
  ($100–300/asiento) bien posicionado (≈ $195/puesto-equivalente) y muy por debajo de un enterprise
  por asiento. Para un comprador departamental con presupuesto propio es una cifra defendible sin
  pasar por Compras corporativo.
- **Por qué add-on por marca y no por puesto en métricas:** el valor de métricas escala con el
  número de marcas que se consolidan, no con cuánta gente las mira. Cobrar por marca alinea precio
  con valor y evita penalizar que más gente vea el reporte.

### Variante "todo incluido" (supuesto (b))

Si el cliente prefiere no gestionar la suscripción de Claude, Keni empaqueta el asiento:
**$75/puesto/mes** (capa + asiento), manteniendo los add-ons igual. El margen baja un poco pero la
venta es de un solo número y una sola factura. **Supuesto:** sujeto a que los términos de reventa de
Claude for Teams lo permitan; validar antes de ofrecerlo.

---

## 5. Propuesta por fases (alineada con el roadmap)

La oferta sigue el estado real del producto. No vendemos humo: lo que aún no existe se nombra como
hito, con su dependencia. (El **estado** de cada capacidad —listo vs. pausado por gating externo—
es el que define [`estado-producto.md`](estado-producto.md); aquí se le pone **precio y orden de
venta**, no se redefine.)

### Fase 0 — Lo que se vende YA (piloto)

Listo y sin dependencias externas:

- **Copy desde texto** (`copy-desde-nota`, `nota-a-formato`, `resumen-tendencia`): tropicalización
  es-MX, voz por marca + voz personal, formato por plataforma, verificación.
- **Copy desde video/audio** (`clip-a-copy`): transcripción **en local** + citas con marca de
  tiempo. (Requiere whisper.cpp + ffmpeg en un Mac Apple Silicon designado; todo gratis, sin nube.)
- **Métricas-insight** (MCP): reporte consolidado multi-marca, mejores piezas, comparación de
  periodos, picos/anomalías, surfacing de cobertura. **Lee datos reales de Metricool vía su API**
  (AMX está en plan Advanced → token de API disponible) y añade encima la capa de insight y
  narrativa es-MX; no reemplaza la analítica de Metricool, se apoya en ella.
- **Preview de publicación en dry-run** (`publica-meta` / pre-vuelo beta): prepara y previsualiza la
  publicación con gate humano. **No publica de verdad** — es el ensayo previo a la publicación real.

Esta fase ya justifica la **opción de entrada** y la **suite sin publicación**.

### Fase 1 — Datos reales de métricas (semanas)

- Adaptadores reales por plataforma (Meta FB/IG, YouTube, X, TikTok) — el código ya está; se
  habilita por red conforme caen los bloqueos: **Meta App Review (3–6 semanas realistas)**,
  auditoría de TikTok, decisión de coste de X.
- Modo **alojado por Keni** con **tokens System User de Meta (no caducan)** → propiedad del camino
  de publicación hosted (ver Fase 2): la conexión que publica no requiere reautenticación periódica.

### Fase 2 — Publicación (tras App Review aprobada)

- **Publicación real** a Meta (FB/IG) desde el preview, con gate humano. Es el siguiente paso
  natural del dry-run que ya existe. **Dependencia dura: App Review + Advanced Access de Meta**
  (3–6 semanas, y cada rechazo reinicia el ciclo). Aquí es donde empezamos a **entrar en el terreno
  de Metricool**, ya con confianza ganada.

### Fase 3 — Scheduling y dashboard

- **Programación de publicaciones** (cola/calendario): hoy no existe.
- **Dashboard** con pantalla visual: hoy todo es conversacional. Un tablero para Mariana/Bernardo
  cierra la sustitución del tablero de Metricool.

**Mensaje comercial de las fases:** se cobra por lo que está listo (Fase 0 desde ya); cada hito que
cae es una conversación de upsell natural (más valor → más alcance del producto → ampliar la suite),
no una promesa pendiente que devalúe la venta inicial.

---

## 6. Riesgos comerciales

El catálogo completo de riesgos (comoditización del MCP/copy, dependencia de aprobaciones
externas, dependencia del incumbente en el histórico, coste de insumo, dependencia de Anthropic)
y sus mitigaciones es **único** y vive en [`analisis-competitivo.md`](analisis-competitivo.md) §4.
Aquí solo el riesgo **propiamente comercial** que ese doc no cubre:

- **Legal/IT corporativo si la compra escala más allá de Bernardo.** Mientras viva en su
  departamento (presupuesto propio), se evita procurement. En cuanto el despliegue alojado maneje
  tokens de las marcas a nivel corporativo, o el gasto suba de cierto umbral, entra **Legal/IT
  corporativo de AMX** (revisión de privacidad, contrato de subprocesador con Anthropic, manejo de
  datos). *Mitigación:* [`flujo-de-datos-privacidad.md`](flujo-de-datos-privacidad.md) ya está
  escrito para esa revisión; el diseño local/privacy-first es el argumento más fuerte. Anticiparlo,
  no esperar a que lo pidan.

Los riesgos de mercado (Fase 0 no depende de aprobaciones; vender el moat editorial y no la
plomería; complemento aditivo para invertir la dependencia del histórico) ya están en §3 y en el
análisis competitivo: no se repiten para no divergir.

---

## 7. Métricas de éxito (piloto → producto)

**Métrica norte: engagement** (señalada por Mariana). Si la herramienta no mueve el engagement, no
importa cuánto copy produzca.

Métricas del piloto, en tres capas:

**Resultado (la que importa al decisor):**
- **Engagement** de las piezas hechas con keni-social vs. las hechas a mano (por marca; medible con
  el propio MCP de métricas / Metricool). Objetivo del piloto: demostrar mejora medible y atribuible.

**Adopción (señal de que la cuña funciona):**
- Nº de CM activos / semana y nº de piezas generadas (copy desde texto + copy desde video).
- % de copy aprobado con verificación en verde a la primera (calidad del borrador → menos retrabajo).
- Tiempo de "video → copy publicable" antes y después (la promesa de "no escuchar la hora de podcast").

**Comerciales (señal de que hay producto, no solo piloto):**
- Conversión piloto → contrato pagado en el departamento de Bernardo.
- Expansión: nº de marcas y de puestos añadidos tras el arranque (valida el modelo por puesto +
  add-on por marca).
- Disposición a pagar por los hitos al caer (¿el upsell de publicación/scheduling tiene demanda?).

**Criterio de "el piloto fue un éxito" (propuesta):** engagement medible a favor en al menos una
marca + adopción sostenida de al menos los CM del equipo de Bernardo + conversión a un contrato
pagado. Con eso se justifica empaquetar como producto y salir al cliente nº2.
