# ADR 0011 — Dos procesos: Investigación y Producción

El flujo noticia → publicación se organiza en **dos procesos con nombre, frontera
explícita y control independiente**. No hay un "pipeline" monolítico que mezcle
investigar con producir.

## Investigación (el motor de noticias)

Recolecta, deduplica, clasifica por marca, prioriza y **verifica** noticias:
Recolectar → Agrupar → Fusionar → Traducir → Clasificar marca → Priorizar →
Admitir → Verificar (QA de fuente).

**Salida:** un pool de historias deduplicadas, clasificadas por marca, priorizadas y
verificadas. Es el único insumo de Producción.

## Producción (la máquina de contenido)

Convierte una historia verificada en pieza publicable: Redactar (voz de marca) →
Ilustrar → avance a revisión → Publicar.

## Frontera

Una historia **sale de Investigación cuando está verificada (QA pasada)**, y la QA
verifica la HISTORIA antes de materializar contenido de producción: solo se promueve lo
verificado, lo que tiene problema no cruza. Producción empieza en Redactar. Por tanto:
**Verificar (QA) es Investigación**; **Redactar e Ilustrar son Producción**.

## Invariantes

- **Dos loops independientes**, cada uno con su propio hilo, cadencia, gate y
  single-flight. Se pueden encender, parar y escalar por separado (p. ej. investigar
  sin producir mientras se valida una marca).
- **Control por dos maestros** (Investigación / Producción), cada uno con override por
  marca y bajo el kill-switch global `KENI_MAQUINA`. El control granular vive en un
  toggle por fase y por marca: apagar una fase en una marca no afecta al resto. Los
  pasos pre-marca o cross-marca quedan solo globales: no se puede gatear por una marca
  que aún no existe en el ítem.
- **Nomenclatura sin ambigüedad:** «motor de noticias» = Investigación; «máquina de
  contenido» = Producción. El término "editorial" queda reservado para la redacción del
  copy (Producción); el perfil que alimenta Priorizar es relevancia (Investigación).

## Respeta

ADR 0001 (generación `claude -p`), ADR 0002 / 0005 (el handoff Investigación→Producción
es el seam A↔C entre apps), ADR 0004 (Postgres) y ADR 0010 (ambos procesos bajo el
presupuesto de tokens y el kill switch).
