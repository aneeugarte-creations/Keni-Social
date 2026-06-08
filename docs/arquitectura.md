# Arquitectura

Tres piezas independientes que se complementan: la **Texto de Prompts** + lanzador neutro,
el **MCP de métricas**, y la **Consola** (UI que orquesta ambos). Cada una funciona por su cuenta.

Para el **estado** de cada pieza (qué está listo, qué está pausado por gating externo) la fuente
única es [`estado-producto.md`](estado-producto.md); aquí se describe **cómo** encajan, no el
estado.

## 1. Texto de Prompts + lanzador neutro

Reemplaza al antiguo "sistema de skills" (carpetas `SKILL.md` + `keni.yaml` con formularios) por
un **almacén único de documentos markdown** editables (`texto.py`, files-as-truth bajo
`KENI_TEXTO_DIR`) y un **lanzador NEUTRO** (`dominio/generar.py`) que es el único punto de
arranque de `claude -p`.

Cada documento es un `.md` con frontmatter YAML + cuerpo; conviven dos `tipo`:

- **`prompt`**: la instrucción que se LANZA sobre contenido/áreas (el motor de generación).
- **`editorial`**: la línea editorial (voz de marca, plataformas, tropicalización, reglas legales).
  Se ADJUNTA a un prompt al lanzarlo (auto por marca + ajustable).

```
documento prompt (Texto)        fuente (nota | video | audio | url | área)
   └─ lanzar (dominio/generar)            ├─ video/audio: transcribe en LOCAL (whisper.cpp; no sale de la máquina)
        │                                 └─ ↓
        ├─ compone: cuerpo del prompt + línea editorial adjunta (por marca) + contexto + redes
        ├─ encola un job `claude -p` con cwd NEUTRO (prompt AUTOCONTENIDO)
        ├─ produce: 1 variante por plataforma (con conteo de caracteres) o un documento
        └─ post-procesa: piezas/publicaciones/QA/hashtags, según el `procesar_spec` del job
             └─ veredicto: LISTO PARA APROBAR / qué revisar; queda en el historial
```

Separación clave: **marca** (línea editorial institucional, estable) vs **voz** (toque personal,
lo rellena cada quien). El lanzador compone voz sobre marca sobre reglas globales DENTRO del
prompt, que viaja autocontenido al subproceso.

El caso "mete el video y dame el copy" transcribe el material en local y trata el texto de ASR
como **no verificado** (nombres, cifras y citas se marcan para confirmar contra el audio), con la
misma auto-verificación que el copy desde nota.

## 2. MCP de métricas (`mcp-metricas/`)

Servidor MCP (Python/FastMCP), ejecutable por **stdio** (local) o **HTTP** (alojado, `KENI_MCP_TRANSPORT=http`), con una **fuente** activa y acotable por marca:

```
tools (listar_cuentas, metricas_resumen, mejores_piezas, comparar_periodos,
       tendencia_historica, reporte_consolidado, picos)
   ├─ FuenteMetricas
   │    ├─ FuenteMuestra        (datos offline deterministas; default / fallback)
   │    ├─ FuenteMetricol       (API REST de Metricool; AMX en plan Advanced)
   │    │     consume lo que Metricool ya consolidó (no ingesta propia por red);
   │    │     degrada a `muestra` si falta el token. Camino de dato real recomendado.
   │    └─ FuenteCompuesta      (real)
   │         └─ un AdaptadorPlataforma por red, tras una interfaz común:
   │            meta · youtube · x · tiktok   (degradan si no hay credenciales)
   └─ Historico (SQLite local)  guarda cada lectura → variación real vs. periodo
        anterior + serie temporal (tendencia_historica). Local por persona.
```

Añadir una plataforma = un adaptador nuevo, sin tocar las tools. El esquema (`schema.py`) normaliza todas las redes a la misma forma.

**Multi-usuario:** cada persona acota sus marcas con `KENI_METRICAS_MARCAS` (o el campo `marcas` del config); solo ve y consulta las suyas.

**Dos modos de despliegue** (arquitectura híbrida del producto):
- **Local por persona** — MCP por stdio, credenciales en la máquina de cada quien (ver `despliegue-local.md`, `credenciales.md`). Máxima privacidad.
- **Alojado por Keni** — MCP por HTTP con **System User tokens de Meta** (no caducan: sin renovación manual cada ~60 días) y OAuth centralizado, para máquinas bloqueadas (ver `despliegue-hosted.md`). Solo expone números agregados.

Distribución: el MCP se instala y actualiza como **plugin de Claude Code** desde un marketplace privado (ver `README.md`). La voz personal de cada quien vive en `~/.config/keni-social/voces/` para sobrevivir a las actualizaciones.

## 3. Consola (`consola/`)

Capa de gestión opcional para máquinas no técnicas (community managers): una UI web local que
**orquesta** la generación de copy/imagen (Texto + lanzador) y el MCP de métricas, sin
reemplazarlos. Backend Starlette
(Python) + frontend React/TS/Vite/shadcn (bundle vendorizado en
`consola/src/keni_consola/webapp/`). La generación corre **en segundo plano con `claude -p`**
(stream-json, token a token), con un semáforo de concurrencia (`KENI_MAX_JOBS`, def. 4).

```
Consola (Starlette + React, local 127.0.0.1)
   ├─ páginas de Trabajo: Texto · Generar copy · Imágenes · Reporte deportes · Termómetro mundial …
   │    └─ lanzan `claude -p` con el MISMO prompt autocontenido que un usuario técnico invocaría a mano
   ├─ páginas de métricas: dashboard / reporte sobre el MCP `keni-metricas`
   └─ Ajustes: credenciales (`secretos.toml`, 0600), buzón de sugerencias
```

El lanzador lee solo variables de entorno; la Consola **exporta** la clave del almacén único
(`secretos.toml`) al subproceso al lanzar una generación. Detalle en [`consola.md`](consola.md).

**Persistencia operacional (ADR 0004): Postgres único.** Las tareas, el seguimiento comercial,
la rota, los usuarios/sesiones y la cola de jobs viven en **Postgres** (`DATABASE_URL`
obligatoria en local y hosted; en desarrollo no se usa Postgres local —la ejecución y
validación se hacen en el server/CI— y, si hace falta correr en local, cada quien provee
su propio `DATABASE_URL`).
El **contenido editorial estructurado** (publicaciones, fuentes RSS, grupos de hashtags,
franjas) también vive en **Postgres** tras cerrar el rezago file→pg (ADR 0006). Solo la
**prosa editorial por marca** (el `marca.yaml` y el `CLAUDE.md` de cada marca, las voces) sigue
en ficheros versionados (`ficheros.py`). El histórico de métricas del MCP (SQLite local por
persona) es otro almacén distinto y no se ve afectado.

### Catálogo de apps (A/B/C + shell)

La Consola es un **catálogo de apps** (no un monolito enmarañado ni microservicios): un
único deployable que reúne tres apps de producto + un shell transversal, con fronteras
**verificadas en CI**. Decisión en [ADR 0005](adr/0005-agrupamiento-catalogo-por-unidad-de-producto.md)
sobre el mecanismo de [ADR 0002](adr/0002-descomposicion-monolito-modular-catalogo-apps.md).

- **A · Producción** (el moat): generación de copy/imagen, Texto de Prompts, investigación,
  revisión, agentes. Asíncrona + worker (`claude -p`) + whisper local.
- **B · Métricas**: lectura/insight/reporte. **Consumidora de Metricool** (`FuenteMetricol`),
  no ingesta propia por red; read-through con caché e histórico.
- **C · Operación**: rota, pendientes, parrilla, aprobación. CRUD transaccional multiusuario
  sobre Postgres; la **publicación real** enciende vía Metricool (flag `KENI_PUBLICAR_REAL`).
- **Shell** (no es app): auth, config, secretos, media, catálogo, panel. Base transversal.

Cómo se sostiene en el código:
- **Manifest por app** (`consola/src/keni_consola/apps/<app>.toml` + `apps/registro.py`): declara
  qué módulos `api/*` posee cada app, sus rutas y su **flag de activación** (`KENI_APP_*`).
- **`GET /api/catalogo`** devuelve solo las apps **activas** (según flags); el sidebar del
  frontend se **hidrata de ahí** (`navegacion.ts` ya no hardcodea): añadir/activar una app no
  edita la navegación a mano.
- **Lint de fronteras** (`consola/tests/test_fronteras.py`): falla si un router de una app importa
  internals de otra, salvo los **seams** declarados (allowlist con justificación). Los cruces
  legítimos van por **funciones-contrato** que la app dueña expone (p.ej. `dominio.publicaciones.
  crear_borrador` para el handoff A→C, o `cola_de_aprobacion`/`proximas_programadas` que lee el panel).
- **Test scoping** en CI: el aislamiento de apps permite correr **solo los tests de la app tocada**
  (+ contrato + `keni-shared`) por filtro de rutas; un cambio en `keni-shared` corre la suite completa.

### Versionado de esquema de los YAML que quedan en fichero

La prosa editorial por marca que sigue en **ficheros YAML editables a mano** (`marca.yaml` y demás;
el contenido estructurado migró a Postgres, ver arriba) se versiona para que un cambio incompatible
de forma no obligue a una migración heurística: cada fichero lleva una clave top-level
`version: <int>`. El registro único vive en `keni_shared.esquema_yaml`:

- `VERSIONES` (tipo → versión actual) y `MIGRACIONES` (tipo → lista de funciones `dict → dict`).
- `sellar(tipo, datos)` estampa la versión actual antes de volcar; `migrar(tipo, datos)` la sube al
  leer. Cada lector de YAML llama `migrar` tras `safe_load`; cada escritor llama `sellar` antes de
  serializar.

Upgrade **perezoso**: la versión 1 es la forma actual, así que hoy `MIGRACIONES` está vacío y un
fichero legado sin `version` solo se re-sella al siguiente guardado (sin reescritura masiva al
arranque ni fichero sidecar). **Añadir una migración** cuando cambie la forma de un tipo: subir
`VERSIONES[tipo]` a N+1 y añadir a `MIGRACIONES[tipo]` una función en la posición N (0-based = versión
de partida) que transforme de N a N+1; el salto 0→1 es identidad y no se registra.

### Contratos de la máquina automática

Cuando las fuentes (RSS, radar, calendario, alta del equipo) auto-generan borradores, el
trabajo concurrente se apoya en unos seams compartidos que NO deben divergir. Los contratos
vigentes (verificados en código):

- **Seam de handoff A→C — única puerta de creación de borradores** (`dominio/publicaciones.py`):
  - `crear_borrador(marca, red, *, titulo, contenido, copy_in, veredicto, origen, imagen,
    imagen_fuente, tipo_contenido, evergreen, autor)` → pieza nueva con padre propio.
  - `crear_borrador_en(contenido_id, marca, red, ...)` → NIDA el borrador bajo un tema
    existente del tablero (`contenido_plataforma` con `es_publicacion=1`); devuelve `None` si
    el tema no existe. Es el camino de la auto-generación, para que el borrador cuelgue de su
    tema origen.
  - Invariante: el estado inicial SIEMPRE es `borrador` (ninguna de las dos vías expone
    `estado`). Revisión, programación y publicación son responsabilidad EXCLUSIVA de C; el
    gate humano vive en C y permanece intacto: la IA produce hasta el borrador, el humano
    aprueba cada pieza y autoriza cada publicación.

- **Flags de automatización** (todos default OFF / conservador; accesores en `config.py`):

  | Flag (env) | Accesor | Semántica |
  |---|---|---|
  | `KENI_RADAR_AUTO` | `radar_auto_activo()` | Promueve temas virales del Radar al tablero (`origen='radar-auto'`). |
  | `KENI_AUTOGEN` | `autogen_activo()` | Encola COPY para temas de fuente sin copy y con marca. Nada se publica solo. |
  | `KENI_AUTOGEN_ARTE` | `autogen_arte_activo()` | Genera ARTE por IA para temas con copy pero sin imagen (degrada sin proveedor). |
  | `KENI_PUBLICAR_REAL` | `publicar_real()` | Gate de publicación REAL vía Metricool. OFF = dry-run. |

- **`origen='equipo'`** (`estados.ORIGEN_EQUIPO`): el origen con que nace un alta CREATIVA del
  equipo (foto/nota/idea con marca); se AUTO-GENERA siempre. La auto-generación de copy trata
  como "tema redactable" el conjunto `estados.ORIGENES_AUTOGEN` = fuentes externas históricas
  (`import-calendario`, `radar-auto`, `radar`, `rss`) + `equipo`. El alta tecleada legada
  (`origen=""`) queda EXCLUIDA a propósito (la genera quien la crea, si quiere).

## Cómo encajan

Un prompt de copy puede consultar `mejores_piezas` del MCP para ajustar el tono a lo que funcionó (paso opcional con degradación: si el MCP no está, se omite). Así el sistema que **produce** aprende del que **mide**, sin acoplarse: cada uno funciona solo. La Consola es la cara visible que reúne las tres piezas para quien no quiere usar Claude Code a pelo.

> **Estado y hitos:** la fuente única es [`estado-producto.md`](estado-producto.md) (qué está
> listo, qué está pausado por gating externo de plataforma). Las cifras de la fuente `muestra`
> están ancladas a la entrevista de estrategia (Claro Sports ~80M vis/mes 2–3%; UnoTV alto alcance,
> bajo engagement). El detalle operativo de credenciales reales está en
> [`credenciales.md`](credenciales.md).
