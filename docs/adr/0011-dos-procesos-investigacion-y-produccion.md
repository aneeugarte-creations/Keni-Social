# ADR 0011 — La frontera Verificar/Redactar: el flujo en loops independientes

El flujo noticia → publicación NO es un "pipeline" monolítico que mezcle investigar
con producir. Hoy se organiza en tres loops con nombre, cadencia y control propios:
**Investigación**, **Producción** y **Portal**. El número de loops es elástico (ya
pasó de dos a tres); lo esencial y duradero es la **frontera** entre investigar y
producir, no cuántos loops la rodean.

## Investigación (el motor de noticias)

Recolecta, deduplica, clasifica por marca, prioriza y **verifica** noticias de fuentes
ajenas: Recolectar → Agrupar → Fusionar → Traducir → Clasificar marca → Priorizar →
Admitir → Verificar (QA de fuente).

**Salida:** un pool de historias deduplicadas, clasificadas por marca, priorizadas y
verificadas. Es el insumo de Producción.

## Producción (el brazo de reutilizar)

Convierte una historia YA verificada en pieza publicable: Redactar (voz de marca) →
Ilustrar → avance a revisión → Publicar.

Aquí "Producción" significa Redactar+Ilustrar sobre historias verificadas: es el brazo
de **reutilizar** lo que ya existe. No confundir con la "máquina de contenido original"
de la misión del producto, que designa el motor de **crear** contenido propio (fotos,
arte, investigación en persona del equipo humano); eso vive fuera de este ADR.

## Portal (fuente propia, admisión directa)

Admite DIRECTO al tablero las historias de **fuente propia** (`fuentes_rss.propia=1`)
como temas `origen='portal'`, **sin umbral ni verificación**: todo el contenido propio
salta la QA porque ya es de la casa. Loop propio (lock `pipeline_portal`, cadencia y
gate Recolectar propios). Lo que admite el Portal lo redacta luego Producción
(`temas_para_redactar` los incluye), así que el Portal alimenta a Producción sin pasar
por la verificación de Investigación.

## Frontera (lo esencial)

Una historia ajena **sale de Investigación cuando está verificada (QA pasada)**, y la
QA verifica la HISTORIA antes de materializar contenido: solo se promueve lo verificado;
lo que tiene problema no cruza. Producción empieza en Redactar. Por tanto:
**Verificar (QA) es Investigación**; **Redactar e Ilustrar son Producción**. Esta
frontera es lo que se conserva aunque cambie el número de loops.

## Cómo está organizado hoy

- **Tres loops independientes**, cada uno con su propio hilo, cadencia, gate y
  single-flight (locks `pipeline_investigacion`, `pipeline_produccion`,
  `pipeline_portal`). `iniciar_pipeline()` arranca los tres. Se pueden encender, parar y
  escalar por separado (p. ej. investigar sin producir mientras se valida una marca).
- **Control NO simétrico.** `KENI_INVESTIGACION` es un maestro real: el loop de
  Investigación solo barre si su admisión o su verificación están encendidas
  (`alguna_etapa_investigacion_activa`); con ambas OFF duerme. El loop de Producción NO
  tiene un maestro equivalente con criterio: `alguna_etapa_produccion_activa()` devuelve
  True siempre (la etapa de Avance corre incondicional), así que el gate real del loop
  de Producción es el kill-switch global `KENI_MAQUINA`. Las fases que gastan `claude -p`
  (Redactar/Ilustrar) se auto-gatean DENTRO del barrido por su propio toggle global +
  override por marca. El Portal se gatea por Recolectar, también bajo `KENI_MAQUINA`.
- **Control granular por fase y marca:** apagar una fase en una marca no afecta al resto.
  Los pasos pre-marca o cross-marca quedan solo globales: no se puede gatear por una
  marca que aún no existe en el ítem.
- **Nomenclatura:** «motor de noticias» = Investigación. El término "editorial" queda
  reservado para la redacción del copy (Producción); el perfil que alimenta Priorizar es
  relevancia (Investigación).

## Respeta

ADR 0001 (generación `claude -p`), ADR 0002 / 0005 (el handoff Investigación→Producción
es el seam A↔C entre apps), ADR 0004 (Postgres) y ADR 0010 (los loops bajo el
presupuesto de tokens y el kill switch).

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- Aparezca un nuevo canal de admisión o una etapa propia (p. ej. re-edición post-rechazo) → el número de loops vuelve a cambiar; lo que se conserva es la frontera de verificación.
- Se cierre el piloto AMX → reevaluar la topología del pipeline.
