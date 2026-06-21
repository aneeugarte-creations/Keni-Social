# ADR 0010 — Economía de la generación

La generación corre `claude -p` con la MISMA suscripción que el equipo usa a diario (OAuth,
ADR 0001). El riesgo real es que una ráfaga de trabajo de fondo (pipeline/autogen) agote la
cuota compartida sin que nadie lo vea venir y deje al equipo —humanos incluidos— sin poder
generar. La economía de la generación existe para acotar ese riesgo.

## Principio invariante

Lo que NO debería cambiar aunque cambie la implementación:

- **Un guardián contra las ráfagas de fondo.** El trabajo automático comparte la misma
  cuota/suscripción que las personas. Debe existir una forma de que ese fondo ceda antes
  que el trabajo manual del equipo, para que una ráfaga no consuma lo que necesitan los
  humanos. La granularidad de ese corte (escalonado, por margen, global/por motor/por
  marca) es implementación, no principio.

- **El humano siempre puede cortar.** Un kill switch manual manda sobre todo: nada se
  encola ni se reclama; lo que corre termina y lo encolado espera. Es el freno de mano de
  un clic y no depende de ningún cap automático.

- **El ledger es contabilidad y observabilidad, no facturación.** Cada generación cerrada
  deja su consumo (tokens in/out, coste estimado, prompt) en una cuenta única en Postgres,
  idempotente por generación. Sirve para ver y entender el gasto, no para liquidar nada.

- **El guardián no es un cinturón funcional.** Ante un fallo de lectura de la BD se sirve
  el último valor conocido y la máquina sigue: un falso corte por un parpadeo pararía todo.

## Mecanismo y estado actual

La implementación contempla varias capas, pero en el piloto la mayoría están **dormidas**.
Lo que hoy está activo por defecto:

- **Kill switch humano** (`KENI_GENERACION_PAUSADA`, toggle del Monitor): el corte manual,
  siempre disponible.
- **Tope de tamaño del prompt** (`KENI_PROMPT_MAX_CHARS`, def 200000; aviso a 80000): un
  tope duro que rechaza antes de gastar, con remedio en el mensaje.
- **Tope de intentos** (`KENI_JOBS_MAX_INTENTOS`, def 3): un job que agota sus intentos se
  descarta con error claro en vez de re-reclamarse para siempre quemando tokens.

Lo que existe pero está **en 0 = apagado** hasta confirmar el consumo real del piloto:

- **Cap de coste en USD/día UTC** (`KENI_PRESUPUESTO_USD_DIA`, def 0.0) y su **margen
  manual** (`KENI_PRESUPUESTO_MARGEN_MANUAL`, def 20%), que definirían el corte global en
  dos escalones (`solo_manual` al rebasar el cap; `agotado` al rebasar cap + margen).
- **Topes de tokens por motor** (investigación/producción, entrada/salida; def 0) y sus
  equivalentes **por marca**, que cortarían solo su ámbito tomando el más restrictivo.

Cuando todos esos caps están en 0 el corte automático no actúa: el sistema solo conoce
`normal` y `pausado`. Los escalones, el margen y los ejes global/motor/marca son la forma
concreta del guardián, no el principio; pueden encenderse, simplificarse o retirarse según
lo que muestre el piloto.

## Sobre la unidad: el cap en USD es un proxy, no una factura

El modelo de auth es **suscripción/OAuth** (ADR 0001) y **NO factura por token**: la cuenta
no se cobra por consumo, se rige por una **cuota por ventana móvil** (sesión / semana). El
cap "USD por día UTC" del diseño **no es una verdad de facturación**: es un **proxy** —el
mejor disponible hoy— de un recurso que la cuenta mide en otra unidad (cuota, no dólares) y
en otra ventana (móvil, no día UTC). Las cifras de coste del ledger son estimaciones de
referencia, útiles para observar tendencias, no importes reales a pagar.

Esta es la principal razón por la que los caps en USD nacen dormidos: encenderlos como si
fueran un presupuesto monetario daría una falsa sensación de exactitud sobre un recurso que
no se mide así.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- Se confirme el patrón de consumo real del piloto (decidir si los caps dormidos se encienden, se simplifican o se retiran).
- Cambie el modelo de auth (a API key con saldo) → el ledger en USD pasaría a ser veraz y el diseño debería reorientarse a esa unidad.
