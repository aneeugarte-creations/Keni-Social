# 06 — Calidad del feed: filtro de entrada, umbral, explicabilidad y caducidad

El pool de noticias es la materia prima de la producción automática: cada historia
promovida acaba en Verificar + Redactar (`claude -p` ×2, coste real de tokens de la suscripción).
Este doc cubre las CUATRO defensas que mantienen el feed constante, jerarquizado y de
calidad para las marcas del piloto (unotv = noticias nacionales MX, claro-sports =
deportes, nacion-gamer = gaming), y por qué cada una vive donde vive:

```
RSS/agencias/trends ──► [1 FILTRO DE ENTRADA] ──► noticias_items ──► Agrupar
                                                                        │ (dedup por
                                                                        ▼  evento)
        panel Cobertura ◄── score EXPLICABLE ◄── noticias_clusters ─────┘
                                                       │
              [4 CADUCIDAD TTL] ◄──(reloj)──           │
                                                       ▼
                                    [2 UMBRAL] ──► promoción Admitir ──► Verificar ──► Redactar ($)
```

## 1. Filtro de ENTRADA por agenda de marca (`KENI_INGESTA_FILTRO`, def ON)

Un feed asignado a una marca (agregadores, Google News, secciones mixtas) puede traer
de todo. Antes se archivaba TODO (hasta `KENI_INGESTA_MAX_ITEMS` por sondeo): el ruido
saturaba pool y panel y competía por promoción. Ahora **la puerta filtra**:

- `dominio/ingesta.filtrar_por_vocabulario(items, palabras)` (pura): pasa el item que
  casa ≥ 1 término de la agenda de la marca (título o resumen; misma normalización y
  mismo vocabulario que el ranking). Con vocabulario vacío NO filtra (sin agenda no hay
  criterio).
- Exentos: feeds **propios** (su contenido ES la marca), feeds **sin marca**
  (compartidos/agencias/trends) y marcas sin vocabulario.
- **Fail-open**: si el filtro revienta, se archiva todo (perder cobertura es peor que
  archivar ruido; el umbral después (en el flujo) contiene el coste).
- Observable, no silencioso: `fuentes_rss.ultimo_filtrados` por sondeo (columna nueva),
  visible en `/api/noticias/salud` y en la tabla de Salud de fuentes («Filtrados»), y
  agregado en el log/resumen del barrido (`items_filtrados`).

## 2. UMBRAL de producción automática (`noticias_umbral` — fuente única)

El panel lista TODO el pool jerarquizado, pero **promover** exige un umbral más alto:

- Regla PURA en `dominio/clustering.evaluar_umbral(cluster, ...) -> (supera, motivo)`:
  1. la verificación no es `dudosa` (única fuente no fiable / clickbait → jamás);
  2. el score **recalculado AHORA** (no el persistido, que envejece) alcanza
     `KENI_PROMOVER_MIN_SCORE` (def 0.35);
  3. el encaje de marca por vocabulario alcanza `KENI_PROMOVER_MIN_MARCA` (def 0.2 ≈ 1
     término en el título). Exentas: historias **curadas** por el equipo (señal de
     cajón: el humano ya decidió) y **breaking corroboradas** (evento mayor confirmado
     por varias fuentes a la vez, cuyo vocabulario puede ser nuevo).
- `keni_consola/noticias_umbral.py` es la **fuente única de la decisión** (umbral vivo
  de config + vocabulario efectivo perfil-Haiku-vs-inicial): la usan la promoción CI
  (`pipeline_contenido.clusters_para_promover`, fail-closed) y la API del panel
  (`promovible`/`promovible_motivo` por historia). Si el panel dijera una cosa y el
  pipeline hiciera otra, sería un bug aquí.
- Lo retenido queda `nuevo` en el pool: visible con su motivo, usable a mano
  («Empujar ya»), y caduca solo (§4). Ambos umbrales editables en caliente (ajustes ·
  Ranking de noticias). `0` desactiva cada regla.

## 3. Relevancia EXPLICABLE (score con razón y desglose)

`clustering.puntuar_detalle() -> (score, razon, desglose)` y el daemon PERSISTE la
explicación junto al score (`noticias_clusters.score_razon` / `score_desglose`):

- `razon`: humana («3 fuentes · reciente · relevante para la marca (cdmx, sismo)»).
- `desglose`: señales crudas [0,1] (`corroboracion/frescura/viralidad/marca/
  rendimiento`), `breaking` y `palabras` (los términos del vocabulario que casaron).
  Crudas a propósito: el desglose explica QUÉ tiene la historia; los pesos (editables)
  explican cuánto cuenta cada cosa.
- El re-score periódico refresca TAMBIÉN la explicación (si no, la razón explicaría un
  score viejo). La UI (Cobertura) la enseña en el tooltip del badge de score y en los
  badges «Auto-producible» / «Bajo el umbral».
- El vocabulario inicial por marca vive en `relevancia_marca.py` (~80–190 términos por
  marca del piloto, criterio documentado ahí: términos de una palabra solo si
  identifican la agenda sin ambigüedad; nombres genéricos en frase — `club leon` — para
  no arrastrar historias al asignar marca por vocabulario). El perfil editorial Haiku
  (`KENI_PIPELINE_EDITORIAL`) lo SUSTITUYE cuando está activo.

## 4. CADUCIDAD del pool (TTL + retención) — el feed es perecedero

A diferencia del GC por relevancia (`KENI_NOTICIAS_GC`, selectivo y def OFF), la
caducidad es el RELOJ del feed y va **encendida por defecto**:

- TTL (`KENI_NOTICIAS_TTL_H`, def 72 = la vida de la frescura del score; 0 = off):
  una historia `nuevo` SIN `contenido_id` y sin actividad en el TTL pasa a
  `descartado` — sale del panel, del ranking y de la promoción. Soft y reversible;
  **lo usado nunca caduca**.
- Retención (`KENI_NOTICIAS_RETENCION_H`, def 336 = 14 días; 0 = no borrar): lo
  caducado sin usar se BORRA con sus items, más los items sueltos viejos (techo del
  archivo).
- Corre DENTRO del barrido de ingesta (`ingesta_daemon.paso_caducidad`, throttled a
  1 pasada/15 min) y también en el GC daemon (instalaciones con la ingesta apagada).
  La lógica vive en `db_noticias.caducar_pool`.

## Dedup por EVENTO (Agrupar, token-sort)

`clustering._ratio_claves = max(ratio directo, ratio con tokens ordenados)`: el mismo
evento titulado con las mismas palabras en otro orden («América vence a Chivas en el
clásico» / «En el clásico, América vence a Chivas») se une sin relajar el umbral
global (0.82). Aplica en `asignar`, `Asignador` y en la diversidad de la promoción
(`seleccionar_diversos`). Fusionar (semántica Haiku, `KENI_PIPELINE_FUSIONAR`) sigue
cubriendo los titulares de sintaxis distinta.

## Knobs (todos editables en caliente desde ajustes)

| Knob | Def | Grupo | Qué controla |
|------|-----|-------|--------------|
| `KENI_INGESTA_FILTRO` | ON | noticias_entrada | filtro de entrada por agenda de marca |
| `KENI_PROMOVER_MIN_SCORE` | 0.35 | noticias_produccion | score mínimo del umbral |
| `KENI_PROMOVER_MIN_MARCA` | 0.2 | noticias_produccion | encaje de marca mínimo del umbral |
| `KENI_NOTICIAS_TTL_H` | 72 | tuning | caducidad del pool (0 = off) |
| `KENI_NOTICIAS_RETENCION_H` | 336 | tuning | borrado de lo caducado (0 = nunca) |

Defaults de los umbrales del umbral en `dominio/clustering.py`
(`UMBRAL_MIN_SCORE_DEF` / `UMBRAL_MIN_MARCA_DEF`); contrato del catálogo en
`tests/test_ajustes_catalogo.py`.
