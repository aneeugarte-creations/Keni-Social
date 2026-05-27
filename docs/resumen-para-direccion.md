# keni-social — resumen para dirección

Una página, sin tecnicismos. Estado: **beta — en uso con AMX** (ver
[`estado-producto.md`](estado-producto.md) para el panorama honesto de qué está listo y qué no).

## Qué es

Un sistema para el equipo de redes que convierte el material de cada día —una nota, varios
cables, una entrevista en video— en el copy listo para publicar en cada plataforma (X,
Instagram, Facebook, TikTok, YouTube), en la voz de cada marca y con español de México. El
equipo trabaja hablándole en lenguaje normal dentro de Claude Code; no hay que aprender una
herramienta nueva con menús.

Pensado primero para AMX Contenido (UnoTV, Claro Sports, Nación Gamer, Piso 15, Fundación) y
reutilizable con el siguiente cliente.

## Qué dolores resuelve

- **Reescribir todo a español de México.** El material llega con giros de España; el sistema lo
  tropicaliza solo, en el tono de cada marca, en vez de dejar un borrador que el community tenga
  que rehacer. No es un traductor genérico: aplica la línea editorial de cada una de las cinco
  marcas y, encima, la voz personal de quien escribe.
- **Sacar copy de un video sin verlo entero.** De una entrevista o declaración, entrega el copy
  por plataforma **más las mejores citas con su minuto y segundo**, para que el editor sepa
  exactamente qué cortar. Se acabó el "escúchate la hora de podcast a ver qué sirve". El audio
  **se transcribe dentro de la máquina del equipo** (whisper.cpp), sin subirse a ninguna nube.
- **Consolidar métricas dispersas.** Reúne en un solo informe las cifras de todas las marcas y
  plataformas (alcance, engagement, qué piezas funcionaron mejor), avisa de lo que despunta, y lo
  presenta en un **tablero (dashboard) que se abre con doble clic, sin internet**, listo para
  llevar a una junta con Bernardo.

## Por qué es distinto (lo que la competencia no hace)

Tres cosas que ninguna herramienta del mercado ofrece junta (ver
[`analisis-competitivo.md`](analisis-competitivo.md)):

- **Voz mexicana real, por marca.** No un prompt de "escribe en mexicano": corpus editorial
  versionado por marca + voz personal + reglas de tropicalización + reglas legales (bandera y
  escudo, menores, datos personales). Resuelve el "español global" que los LLMs no localizan bien.
- **Te dice cuándo creerle.** Cada copy **abre con un semáforo de veredicto y su leyenda, antes
  del texto**: 🟢 listo para aprobar · 🟡 revísalo tú · 🔴 no publicar. Marca lo dudoso —sobre
  todo nombres y cifras sacados de un audio— para que la revisión humana sea rápida. La IA no se
  cuelga la medalla de un dato que no confirmó. Para un medio de noticias como UnoTV, esto es la
  diferencia entre una herramienta usable y una que mete errores publicables.
- **Privacidad por diseño, no por promesa.** Los videos y audios se transcriben en local; las
  llaves de acceso a las redes viven en la máquina de cada persona, no en el sistema. A servicios
  externos solo viaja texto de copy y números agregados. (Detalle en
  [`flujo-de-datos-privacidad.md`](flujo-de-datos-privacidad.md).) En el modo alojado por Keni,
  los tokens de Meta son **System User: no caducan**, lo que elimina las desconexiones cada ~60
  días que sufren las herramientas tipo Metricool.

## Qué NO hace (todavía)

No publica solo, no programa publicaciones y no genera imágenes ni edita video. Produce y
verifica el copy; **una persona del equipo revisa, aprueba y publica**. Es por diseño: el humano
tiene siempre la última palabra. Hoy la publicación es **dry-run** (previsualiza qué se
publicaría, sin publicar).

## Cómo se entrega y se confía

- **Se instala como un plugin de Claude Code, en dos comandos, sin permisos de administrador.**
  Enseñar al equipo del cliente a trabajar con agentes dentro de su flujo real **es** el producto
  y **es** la capacitación: no se vende una suscripción opaca, se deja capacidad instalada. Es la
  encarnación del "lo que vendemos lo aplicamos primero" de Keni.
- **Construido y verificado de verdad.** El sistema corre con una amplia batería de pruebas
  automatizadas (más chequeos estáticos de las skills) y un **CI en GitHub Actions** que en cada
  cambio (push y pull request) corre esas pruebas, los evals estáticos de las skills y la
  construcción del bundle del frontend. No es una maqueta: lo que está listo, está probado.

## Valor para AMX y para Keni

- **Para AMX:** recupera la mañana del community manager (no reescribir, no transcribir a mano, no
  juntar números a mano), con español de México de verdad y sin que su material sensible salga de
  sus máquinas. El moat es editorial y crece con el uso.
- **Para Keni:** un producto-capacitación replicable. La cuña (es-MX + video→copy + reportes) es
  portátil a cualquier equipo de contenido en español de México, así que lo validado con AMX es la
  plantilla del cliente nº2. El corpus de cada cliente es propio e intransferible.

## Estado

En **beta, en uso con AMX**: el producto es real y opera en el flujo del equipo. El copy desde
texto y desde video ya funciona hoy, y las métricas funcionan con datos de muestra. Los datos reales de cada plataforma se van encendiendo conforme
caen los permisos externos de cada red (revisiones de Meta, auditoría de TikTok, coste de X). El
panorama completo —qué está listo, qué está pausado y el camino a producto vendible— está en
[`estado-producto.md`](estado-producto.md).
