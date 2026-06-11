# ADR 0011 — Dos procesos: Investigación y Producción

- **Estado:** Propuesto
- **Fecha:** 2026-06-11
- **Decisores:** equipo keni-social
- **Componente:** `keni-consola` (`ingesta_daemon.py`, `pipeline_contenido/` —`_barrido.py`, `_ingesta.py`, `_qa.py`, `_copy.py`, `_avance.py`—, `config_noticias.py` / `_config_comun.py` / `ajustes_catalogo.py`, frontend `pages/noticias/*` y `pages/Produccion.tsx`/`Monitor.tsx`)
- **Relación:** organiza el motor de noticias y la máquina de contenido que viven sobre la cola de ADR 0002 Fase B y la economía de tokens de ADR 0010; respeta las fronteras entre apps de ADR 0005 y el runtime `claude -p` de ADR 0001.

---

## Contexto

El flujo noticia → publicación creció como un solo "pipeline" con muchas etapas. Hoy el
trabajo está repartido en dos daemons, pero la frontera conceptual no coincide con la
operativa y la UI lo refleja a medias:

- **`ingesta_daemon`** (tick ~30 s, gate `KENI_PIPELINE_SELECCION`): sondeo RSS, agencias,
  clustering, merge léxico, **fusión semántica** (Haiku), traducción, re-score, caducidad y
  **clasificación de marca** (Haiku). Escribe el pool (`noticias_items`, `noticias_clusters`).
- **`pipeline_contenido/_barrido._ejecutar_barrido`** (cadencia `KENI_INVESTIGADOR_INTERVALO_HORAS`,
  gate `KENI_MAQUINA`): en una sola pasada hace **CI (admisión: `crear_tema_de_cluster`)**,
  **QA (validación de fuente, `lanzar_qa_fuente`)**, **CD (copy)**, **ARTE** y **AVANCE** a
  revisión. Escribe `contenido` y `contenido_plataforma`.

Problemas:

1. **Frontera mal puesta.** La admisión y la **validación (QA)** —que son trabajo de
   *investigar* si una noticia merece y es fiable— viven en el mismo barrido que el copy y el
   arte (*producir* la pieza). La verificación corre, además, *después* de cruzar a `contenido`,
   o sea ya del lado producción del modelo de datos.
2. **UI dispersa.** Producción es una página clara (`Produccion.tsx`: feed de runs, etapas
   explícitas, Monitor con cola y toggles). Investigación está repartida: el pool en
   `Cobertura`/`MesaNoticias`, la fusión como un badge, el score en un modal, el QA como un
   badge y **la marca asignada no se ve**. No hay una vista del *proceso* de investigación.
3. **Toggles cruzados.** Los interruptores del motor —incluidos los de investigación
   (`SELECCION`, `FUSION`, perfil editorial)— viven en el **Monitor de Producción**. El
   interruptor virtual "Generar" agrupa 5 claves de ambos mundos.
4. **Nomenclatura desalineada.** `KENI_INVESTIGADOR_INTERVALO_HORAS` gobierna la cadencia del
   pipeline de **producción** (mal nombre); coexiste con otro daemon "Investigador" (snapshot
   Fase-1). "Motor de noticias" y "máquina de contenido" se usan sin frontera nítida.

## Decisión

La app se organiza en **dos procesos con nombre, frontera explícita y control independiente**:

### 1. Investigación (el «motor de noticias»)

Recolecta, deduplica, clasifica, **rankea** y **verifica** noticias. Etapas:

ingesta (sondeo RSS + agencias) → clustering → merge léxico → **fusión semántica** →
traducción → **clasificación de marca** → ranking/score (incl. perfil de relevancia) →
admisión → **validación (QA de fuente)**.

**Salida:** un pool de historias deduplicadas, clasificadas por marca, rankeadas y
**verificadas**, listas para producir. Es el insumo de Producción.

### 2. Producción (la «máquina de contenido»)

Convierte una historia verificada en pieza publicable. Etapas:

redacción editorial (voz de marca / copy) → arte → avance a revisión → publicación.

### 3. Frontera

Una historia **sale de Investigación cuando está verificada (QA pasada)**. Producción
empieza en la redacción del copy. Es decir: **Validación (QA) es Investigación**; **editorial
(voz/redacción), copy y arte son Producción**.

> Hoy QA corre sobre `contenido` (ya cruzada la frontera de datos `crear_tema_de_cluster`).
> Alinear el modelo de datos con esta frontera —que QA verifique la historia *antes* de
> materializar contenido de producción— es trabajo de la fase F3 (split físico). Hasta
> entonces la frontera es **conceptual y de control** (toggles + UI), no de plumbing.

### 4. Toggles: dos maestros

Se reagrupa el catálogo de ajustes en dos maestros independientes, cada uno con override por
marca (`::marca`) y bajo el kill-switch global `KENI_MAQUINA`:

| Maestro | Agrupa (claves físicas actuales) |
|---|---|
| **Investigación** | `KENI_PIPELINE_SELECCION` (ingesta), `KENI_PIPELINE_FUSION`, `KENI_CLASIFICAR_MARCA_IA`, `KENI_RENDIMIENTO_RANKING`, perfil de relevancia (ver §5), `KENI_PIPELINE_VALIDACION` (QA) |
| **Producción** | `KENI_PIPELINE_COPY` (copy/editorial), `KENI_PIPELINE_ARTE`, `KENI_PUBLICAR_REAL`, `KENI_AUTO_PROGRAMAR` |

El interruptor virtual "Generar" (que hoy escribe 5 claves de ambos mundos) se **parte** en
los dos maestros. `etapa_activa(flag, marca)` sigue siendo la fuente única de verdad por
etapa; los maestros son una capa de agrupación encima, no reemplazan los flags por etapa.

### 5. Nomenclatura (se unifica)

- **«Motor de noticias» = Investigación**; **«máquina de contenido» = Producción**. Se retira
  el uso ambiguo cruzado.
- `KENI_INVESTIGADOR_INTERVALO_HORAS` → se renombra a una clave de **cadencia de producción**
  (p. ej. `KENI_PRODUCCION_INTERVALO_HORAS`) con **alias legado** (store/env viejos siguen
  leyéndose) para no romper despliegues.
- `KENI_PIPELINE_EDITORIAL` **no es** la voz/redacción editorial: hoy es el **perfil de
  keywords que alimenta el RANKING** (investigación). Para quitar la ambigüedad se renombra a
  un nombre de *relevancia/ranking* (p. ej. `KENI_RANKING_PERFIL_IA`, con alias legado) y se
  ubica en el maestro **Investigación**. El término "editorial" queda reservado para la
  redacción del copy (Producción). *(Punto a confirmar por el equipo: si se prefiere tratar el
  perfil editorial como Producción, se mueve de maestro sin cambiar su función.)*
- "CI" (admisión) y "Ola A–D" son jerga interna; en la UI y los nombres de cara al equipo se
  usan términos del proceso (admisión, ranking, verificación), no las siglas.

### 6. UI: dos páginas-proceso

- **Investigación**: el proceso completo en una página —el pool/mesa + las **etapas visibles**
  (fusión, clasificación de marca, ranking, **validación**) con su estado, el **monitor de
  investigación** (qué se está fusionando/clasificando/verificando y su coste) y **sus
  toggles**. Se **superficie la marca asignada y el QA como etapas** (hoy ocultos/como badge).
- **Producción**: la página actual (feed de runs + cola + toggles de producción),
  recortada a copy/arte/avance/publicación. Los toggles de investigación **salen** del Monitor
  de Producción.

## Plan por fases

- **F0 — este ADR.** Fija modelo, frontera, grupos de toggles y nomenclatura.
- **F1 — Backend/toggles (bajo riesgo).** Dos maestros (Investigación/Producción) en
  `ajustes_catalogo.py`; partir "Generar"; renombrar `KENI_INVESTIGADOR_INTERVALO_HORAS` y
  `KENI_PIPELINE_EDITORIAL` con alias legado. Sin cambios de modelo de datos.
- **F2 — UI.** Página Investigación como proceso (etapas + marca + QA visibles + monitor +
  toggles); sacar los toggles de investigación del Monitor de Producción.
- **F3 — Split físico (futuro, mayor).** Separar `_barrido` para que Investigación
  (admisión + QA) y Producción (copy + arte + avance) corran como loops independientes con su
  propia cadencia/gate, alineando el modelo de datos con la frontera (QA verifica antes de
  materializar producción), desacoplados por el contrato `contenido`/cola.

## Consecuencias

**A favor**
- Modelo mental claro: dos procesos con nombre, frontera y control propio; deja de haber un
  "pipeline" monolítico que mezcla investigar y producir.
- Investigación deja de estar dispersa: la fusión, la clasificación de marca, el ranking y la
  verificación se ven como etapas de un proceso, con su monitor y sus toggles.
- Se pueden encender/parar y escalar los dos procesos por separado (p. ej. investigar sin
  producir mientras se valida una marca).

**Coste / riesgos**
- Migración de toggles y renombrados: requieren **alias legado** y propagar a tests (el
  catálogo de ajustes y `etapa_activa` tienen consumidores en daemon, UI y catálogo).
- La frontera "QA = investigación" es **conceptual hasta F3**: el modelo de datos (QA sobre
  `contenido`) no cambia en F1–F2; se documenta para no confundir.
- F2 toca varias superficies del frontend (sidebar, página Investigación, Monitor).

**Respeta**
- ADR 0001 (generación `claude -p`), ADR 0002 / 0005 (descomposición y fronteras entre apps:
  el handoff Investigación→Producción es el seam A↔C ya contemplado), ADR 0004 (Postgres),
  ADR 0010 (economía de tokens: ambos procesos siguen bajo el presupuesto y el kill switch).

## Alternativas consideradas

- **Solo regroup de UI/toggles sin frontera nueva.** Más barato, pero deja la verificación del
  lado producción y no resuelve la confusión conceptual; se descartó como destino final
  (se adopta como F1–F2, con F3 cerrando la frontera de datos).
- **Split físico inmediato (mover QA antes de `contenido`).** Más fiel desde el día 1, pero
  toca el modelo de datos y el orquestador a la vez que la UI; se difiere a F3 para reducir
  riesgo y entregar valor visible antes.
