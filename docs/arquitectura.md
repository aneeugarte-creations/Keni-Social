# Arquitectura

Tres piezas independientes que se complementan: el **sistema de copy** (skills), el **MCP de
métricas**, y la **Consola** (UI que orquesta ambos). Cada una funciona por su cuenta.

Para el **estado** de cada pieza (qué está listo, qué está pausado por gating externo) la fuente
única es [`estado-producto.md`](estado-producto.md); aquí se describe **cómo** encajan, no el
estado.

## 1. Sistema de copy (`skills-copy/`)

Agent Skills de Claude Code + contexto editorial versionado.

```
fuente (nota escrita)            fuente (video | audio)
   └─ copy-desde-nota                └─ clip-a-copy
        │                                  ├─ transcribe en LOCAL (whisper.cpp; el audio no sale de la máquina)
        │                                  ├─ saca citas con marca de tiempo (puntos de corte del clip)
        │                                  └─ ↓ (mismo contexto editorial y verificación)
        ├─ carga: reglas-legales → tropicalizacion → plataformas → marca → voz
        ├─ produce: 1 variante por plataforma (con conteo de caracteres)
        └─ auto-verifica: fechas, nombres, cifras, legal, "¿suena mexicano?", límites
             └─ veredicto: LISTO PARA APROBAR / qué revisar
```

Separación clave: **marca** (línea editorial institucional, estable) vs **voz** (toque personal, lo rellena cada quien). La skill compone voz sobre marca sobre reglas globales.

`clip-a-copy` añade el caso "mete el video y dame el copy": transcribe el material en local y trata el texto de ASR como **no verificado** (nombres, cifras y citas se marcan para confirmar contra el audio). Comparte el mismo contexto editorial y la misma auto-verificación que `copy-desde-nota`.

## 2. MCP de métricas (`mcp-metricas/`)

Servidor MCP (Python/FastMCP), ejecutable por **stdio** (local) o **HTTP** (alojado, `KENI_MCP_TRANSPORT=http`), con una **fuente** activa y acotable por marca:

```
tools (listar_cuentas, metricas_resumen, mejores_piezas, comparar_periodos,
       tendencia_historica, reporte_consolidado, picos)
   ├─ FuenteMetricas
   │    ├─ FuenteMuestra        (datos offline deterministas; default)
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

Distribución: todo el conjunto (skills + MCP) se instala y actualiza como **plugin de Claude Code** desde un marketplace privado (ver `README.md`). La voz personal de cada quien vive en `~/.config/keni-social/voces/` para sobrevivir a las actualizaciones.

## 3. Consola (`consola/`)

Capa de gestión opcional para máquinas no técnicas (community managers): una UI web local que
**orquesta** las skills de copy/imagen y el MCP de métricas, sin reemplazarlos. Backend Starlette
(Python) + frontend React/TS/Vite/shadcn (bundle vendorizado en
`consola/src/keni_consola/webapp/`). La generación corre **en segundo plano con `claude -p`**
(stream-json, token a token), con un semáforo de concurrencia (`KENI_MAX_JOBS`, def. 4).

```
Consola (Starlette + React, local 127.0.0.1)
   ├─ páginas de Trabajo: Generar copy · Imágenes · Reporte deportes · Termómetro mundial …
   │    └─ lanzan las MISMAS skills (`claude -p`) que un usuario técnico invocaría a mano
   ├─ páginas de métricas: dashboard / reporte sobre el MCP `keni-metricas`
   └─ Ajustes: credenciales (`secretos.toml`, 0600), buzón de sugerencias
```

Las skills son un plugin independiente y leen solo variables de entorno; la Consola **exporta** la
clave del almacén único (`secretos.toml`) al subproceso al lanzar una skill. Detalle en
[`consola.md`](consola.md).

**Persistencia operacional (ADR 0004): Postgres único.** Las tareas, el seguimiento comercial,
la rota, los usuarios/sesiones y la cola de jobs viven en **Postgres** (`DATABASE_URL`
obligatoria en local y hosted; `deploy/dev/docker-compose.yml` levanta un Postgres local).
El contenido editorial sigue en **YAML por marca** (`ficheros.py`) con su índice SQLite
regenerable (`indice.py`). El histórico de métricas del MCP (SQLite local por persona) es
otro almacén distinto y no se ve afectado.

### Versionado de esquema de los YAML

La Consola guarda su contenido como **ficheros YAML editables a mano** (fuente de verdad). Para que
un cambio incompatible de forma no obligue a una migración heurística, cada fichero lleva una clave
top-level `version: <int>`. El registro único vive en `keni_shared.esquema_yaml`:

- `VERSIONES` (tipo → versión actual) y `MIGRACIONES` (tipo → lista de funciones `dict → dict`).
- `sellar(tipo, datos)` estampa la versión actual antes de volcar; `migrar(tipo, datos)` la sube al
  leer. Cada lector de YAML llama `migrar` tras `safe_load`; cada escritor llama `sellar` antes de
  serializar.

Upgrade **perezoso**: la versión 1 es la forma actual, así que hoy `MIGRACIONES` está vacío y un
fichero legado sin `version` solo se re-sella al siguiente guardado (sin reescritura masiva al
arranque ni fichero sidecar). **Añadir una migración** cuando cambie la forma de un tipo: subir
`VERSIONES[tipo]` a N+1 y añadir a `MIGRACIONES[tipo]` una función en la posición N (0-based = versión
de partida) que transforme de N a N+1; el salto 0→1 es identidad y no se registra.

## Cómo encajan

`copy-desde-nota` puede consultar `mejores_piezas` del MCP para ajustar el tono a lo que funcionó (paso opcional con degradación: si el MCP no está, se omite). Así el sistema que **produce** aprende del que **mide**, sin acoplarse: cada uno funciona solo. La Consola es la cara visible que reúne las tres piezas para quien no quiere usar Claude Code a pelo.

> **Estado y hitos:** la fuente única es [`estado-producto.md`](estado-producto.md) (qué está
> listo, qué está pausado por gating externo de plataforma). Las cifras de la fuente `muestra`
> están ancladas a la entrevista de estrategia (Claro Sports ~80M vis/mes 2–3%; UnoTV alto alcance,
> bajo engagement). El detalle operativo de credenciales reales está en
> [`credenciales.md`](credenciales.md).
