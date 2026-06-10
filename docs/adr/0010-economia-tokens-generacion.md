# ADR 0010 — Economía de tokens de la generación (presupuesto, corte automático y kill switch)

- **Estado:** Aceptado
- **Fecha:** 2026-06-10
- **Decisores:** equipo keni-social
- **Componente:** `keni-consola` (`presupuesto_ia.py`, `cola.py`, `worker.py`, `db_jobs.py` —tabla `gasto_ia` y columna `jobs.intentos`—, `generaciones/_almacen.py` —hook de cierre—, `ajustes_catalogo.py`, `/api/actividad/cola*`)
- **Relación:** extiende la cola de jobs de ADR 0002 Fase B (#130 Fase 2) y el endurecimiento #137. La generación sigue siendo `claude -p` con OAuth de suscripción (ADR 0001).

---

## Contexto

La generación corre `claude -p` con la **misma suscripción** que el equipo usa a diario
(ADR 0001). El pipeline de noticias es una máquina de encolar trabajo de fondo: un día de
avalancha informativa puede saturar la cola y **agotar los tokens de todos** —humanos
incluidos— sin que nadie lo vea venir. Antes de este ADR existían topes *de capacidad*
(`KENI_MAX_JOBS`, `KENI_MAX_COLA`, prioridad manual>pipeline, backpressure de admisión),
pero ninguno *de consumo*: nada medía cuántos tokens gastaba el sistema por día ni cortaba
al llegar a un límite, no había freno de mano global, y un job huérfano podía re-reclamarse
para siempre quemando tokens en cada vuelta.

## Decisión

Gobernar el consumo en **tres capas**, todas visibles y editables en caliente:

1. **Ledger `gasto_ia` (Postgres).** Una fila por generación **cerrada** (estado terminal),
   con tokens in/out, coste estimado, `prompt_chars` y el día UTC del cierre. La escribe un
   hook en el **embudo único** por el que todos los caminos fijan el terminal
   (`generaciones._almacen.actualizar`), así no depende de cada lanzador (claude, imagen,
   procesos, fakes de tests). Es **UPSERT por `gen_id`**: re-cerrar (reintento, re-encolado
   tras deploy) actualiza la fila, nunca duplica gasto. Los jobs sin consumo medible
   (imagen/procesos) no dejan fila.

2. **Corte automático con dos escalones** (`presupuesto_ia.nivel()`), comparando el SUM del
   día contra `KENI_PRESUPUESTO_TOKENS_DIA` (0 = sin límite, el defecto):
   - `solo_manual`: gastado ≥ presupuesto → el **fondo** (pipeline/autogen) deja de
     encolarse **y de reclamarse** (la avalancha ya encolada también se corta: queda
     `pendiente`, no se pierde). Lo manual del equipo sigue.
   - `agotado`: gastado ≥ presupuesto × (1 + `KENI_PRESUPUESTO_MARGEN_MANUAL`/100, def 20%)
     → corte **total** (tampoco manual). Los jobs de PROCESO (render ffmpeg/ASR) quedan
     exentos del corte por presupuesto: no gastan tokens.
   El gate vive en **dos puntos**: admisión (`cola.encolar`, excepciones subclase de
   `ColaLlenaError` → 429 claro y backpressure normal del pipeline) y reclamo
   (`worker._bucle` → `reclamar(prioridad_minima=...)`).

3. **Kill switch humano** `KENI_GENERACION_PAUSADA` (`pausado`, manda sobre todo): no se
   encola nada y el worker no reclama nada; lo que corre termina y lo encolado espera. Es
   un ajuste **no peligroso** del grupo `maquina_global`: el Monitor pinta su toggle y el
   store compartido (`/data/ajustes.toml`) lo propaga en caliente a back/worker/daemons.

Complementos de la misma capa de economía:

- **Tope de intentos** (`jobs.intentos`, `KENI_JOBS_MAX_INTENTOS`, def 3): un huérfano que
  agotó sus intentos se **descarta** con error claro (`motivo=interrumpido`) en vez de
  re-reclamarse para siempre. `reencolar_job` (decisión humana) y la resurrección de
  `encolar_job` (trabajo nuevo) resetean el contador.
- **Economía de contexto**: tope duro `KENI_PROMPT_MAX_CHARS` (def 200k chars ≈ 50k tokens;
  rechazo ANTES de gastar, con remedio en el mensaje) + umbral de aviso
  `KENI_PROMPT_AVISO_CHARS` (warning correlacionado) + medición `prompt_chars` por
  generación y por día en el ledger.
- **Visibilidad** (contrato para el Monitor y el agente de observabilidad):
  `/api/actividad/cola` expone `presupuesto` (nivel, pausada, gastado, restante, pct) e
  `intentos` por job; `/api/actividad/cola/series` expone `gasto` por día (tokens, coste,
  `prompt_chars`, generaciones).

## Decisiones de detalle (y porqués)

- **Tokens (in+out), no USD, como moneda del presupuesto.** Con OAuth de suscripción no hay
  factura por run; lo que se agota es el cupo de la suscripción, y eso se aproxima mejor
  por tokens. El coste estimado se guarda igualmente para correlación.
- **El día del gasto es el del CIERRE (UTC).** Es cuando los tokens ya se consumieron; el
  encolado puede ser de ayer.
- **Excepciones subclase de `ColaLlenaError`.** El manejador central 429 y el tratamiento
  de backpressure del pipeline ya existen; subclasear evita cablear handlers nuevos en
  ~20 llamantes y degrada con mensajes específicos (`str(exc)`).
- **Ante un blip de la BD, NO cortar.** El presupuesto es un guardián de economía, no un
  cinturón funcional: `presupuesto_ia` cachea ~3 s, sirve el último valor ante fallo de
  lectura y el worker sigue sin corte si el gate revienta. Un falso corte pararía la
  máquina entera por un parpadeo.
- **El corte de reclamo filtra por prioridad, no por kind.** En `agotado`/`pausado` el
  worker no reclama nada (también frena procesos sin coste de tokens): inspeccionar el
  `spec` en SQL para eximirlos no compensa la complejidad; un render esperando durante un
  corte total es aceptable y el kill switch DEBE frenar toda la maquinaria.

## Alternativas consideradas

- **Contador en memoria / por proceso**: roto en hosted (back/worker/daemons son procesos
  distintos); ya se descartó para el backpressure en #130 Fase 2. El ledger en Postgres es
  la única cuenta compartida y se autolibera al rotar el día.
- **Presupuesto por marca**: prematuro con 2 marcas piloto; el ledger ya guarda `marca`,
  así que el desglose (y un eventual cupo por marca) es una consulta, no una migración.
- **`--max-budget-usd` por run como único control**: topa el run individual
  (`KENI_CLAUDE_MAX_USD`, sigue existiendo) pero no la SUMA del día, que es donde muere la
  avalancha.

## Consecuencias

- Con los defectos (presupuesto 0) el comportamiento de un deploy existente **no cambia**;
  la economía se enciende fijando `KENI_PRESUPUESTO_TOKENS_DIA` desde el Monitor.
- El equipo tiene un freno de mano de un clic y el sistema un techo de gasto diario con
  degradación ordenada (primero la máquina, luego todo) y reanudación sola al rotar el día.
- Tests nuevos en `consola/tests/test_presupuesto_ia.py` y `test_worker_cola.py`; tabla
  `gasto_ia` en el allowlist de truncado (`tests/_postgres.py`).
