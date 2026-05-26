# Plan de persistencia — consolidación del almacenamiento (H2 / E5)

> Sesión 4. Plan **read-only**: análisis y diseño. **No se ha tocado código ni
> migrado nada.** Este documento se presenta para APROBACIÓN antes de ejecutar.
> Es el ítem de **mayor riesgo** de la consolidación: toca datos del piloto AMX en
> vivo. Repo: `/Users/mm/projects/keni-social`. Estado local del autor inspeccionado
> el 2026-05-25. Rutas absolutas; referencias `archivo:línea`.

---

## 0. Resumen ejecutivo

Hoy conviven **dos backends de persistencia de CONTENIDO conmutables** por la env
`KENI_CONSOLA_BACKEND` (`repos.py:41-48`): `ficheros.py` (YAML por marca, DEFECTO) y
`db.py` (SQLite, comportamiento histórico). Más un **índice SQLite regenerable**
(`indice.py`), una **migración one-shot** SQLite→YAML (`migracion.py`) y varios
almacenes laterales (secretos, preferencias, sugerencias, termómetro, media,
generaciones, runs de agentes). Las **tareas** y el **comercial** (serie temporal)
viven SIEMPRE en SQLite vía `db.py`, en ambos backends.

La directriz del usuario NO es "un solo backend", sino una **división funcional
limpia**: YAML = contenido editable a mano (fuente de verdad); SQLite = índice y
datos operacionales **regenerables** y series temporales. El objetivo es **retirar el
conmutador** (`db.py` como backend alternativo de contenido) y dejar `repos.py` como
fachada única coherente, sin perder los datos del piloto.

**Hallazgo crítico de estado real (§1.4):** el `consola.db` del autor todavía
contiene **2 publicaciones que NUNCA llegaron a YAML** (`0447d8740548`,
`df147c356cf5`) y **39 `comercial_snapshots` huérfanos** (sin fila padre en
`comercial_publicaciones`, que está vacía). Cualquier retirada de `db.py` debe
**re-correr la migración primero** y **decidir** qué se hace con esos huérfanos.

---

## 1. Estado real HOY

### 1.1 El conmutador `repos.py` (la fachada)

`repos.py` (368 L, no 1592 — la cifra del contexto confundía con `db.py`) re-exporta
TODAS las funciones públicas con firmas idénticas a `db.py`; cada `api/*.py` consume
SIEMPRE a través de `repos`. El conmutador:

```python
# repos.py:41-48
def _backend():
    elegido = (os.environ.get("KENI_CONSOLA_BACKEND") or "ficheros").strip().lower()
    return db if elegido == "sqlite" else ficheros
```

Reparto interno de `repos.py`:

- **Conmutables por `_backend()`** (CONTENIDO): publicaciones (`:113-164`), grupos de
  hashtags (`:172-193`), franjas (`:201-212`), plantillas (`:220-241`), fuentes RSS +
  items vistos + salud (`:249-290`), historial de skills (`:86-105`).
- **SIEMPRE en SQLite vía `db.py`** (no pasan por el conmutador):
  - **tareas** (`repos.py:56-78`; nota de cabecera `:14-15`).
  - **comercial** — publicaciones comerciales y snapshots (`repos.py:293-368`,
    cabecera `:296-299`: "serie temporal append-only; no encaja en ficheros").

El backend SQLite (`db.py`) sigue **íntegro y operativo**: aunque el defecto sea
`ficheros`, `db._conectar()` (`db.py:65-76`) crea el esquema completo on-demand y
**también** corre una micro-migración del viejo `tareas.json`→SQLite
(`db.py:5-7,75`). Es decir, `consola.db` se materializa siempre (por tareas/comercial)
aunque el contenido viva en YAML.

### 1.2 El backend de ficheros `ficheros.py` (fuente de verdad del contenido)

YAML por marca bajo `KENI_CONSOLA_RAIZ` (def `~/keni-proyectos`,
`ficheros.py:74-78`). Layout (`ficheros.py:8-20`):

```
<raiz>/<marca>/
    marca.yaml                    # id, etiqueta, id_metricas
    CLAUDE.md
    publicaciones/<id>.yaml
    plantillas/<id>.yaml
    fuentes-rss/<id>.yaml
    hashtags/<id>.yaml
    franjas.yaml                  # UN fichero lista por marca
    historial/<YYYY>/<MM>/<id>.yaml
    .keni/rss-vistos.yaml         # {fuente_id: [clave, ...]}
```

- `id` IMPLÍCITO = nombre de fichero; `marca` IMPLÍCITA = carpeta (`ficheros.py:21-24`).
- Escritura atómica vía `io_atomico.escribir_atomico` (`ficheros.py:51,164-179`).
- Lectura tolerante: YAML inválido / `red`/`estado` fuera de allowlist se OMITE con
  log, no rompe el listado (`ficheros.py:182-199,361-385`).
- Cuerpos multilínea en bloque `|` para editar a mano (`ficheros.py:144-161`).
- **tareas NO viven aquí**: `ficheros.py:1147-1164` delega en `db.py` (paridad de firma).

### 1.3 El índice `indice.py` y la migración `migracion.py`

**`indice.py`** (202 L): SQLite de SOLO índice en
`~/.config/keni-social/indice.sqlite` (`indice.py:39-44`, env `KENI_CONSOLA_INDICE`).
Tabla única `entradas(id, tipo, marca, ruta, mtime, red, estado, evergreen, fecha,
fecha_creacion)` con PK `(tipo, id)` (`indice.py:53-71`). Indexa 5 tipos:
`publicacion, plantilla, fuente_rss, grupo_hashtags, historial` (`indice.py:36`).
**NO** indexa franjas ni items vistos (viven en fichero-lista por marca,
`indice.py:20-22`).

- Contrato de **regenerabilidad** (`indice.py:9-14`): se puede borrar en cualquier
  momento; se reconstruye leyendo los YAML.
- `ficheros._buscar_ruta` consulta el índice y, si está vacío/desfasado, re-indexa el
  tipo y reintenta (`ficheros.py:217-235`). `_listar_validado` reconstruye si el índice
  está vacío pero hay ficheros (`ficheros.py:301-326`). `reconstruir_indice()`
  reconstruye TODO desde disco (`ficheros.py:295-298`). **Ya existe el round-trip
  YAML→índice; no hay que inventarlo.**

**`migracion.py`** (346 L): one-shot SQLite→YAML. Lee cada tabla de contenido de
`consola.db` y la vuelca a su YAML conservando el `id` original, convirtiendo
CSV/JSON→listas y 0/1→bool, agrupando franjas por marca y trasladando items vistos
(`migracion.py:93-291`). **Idempotente y best-effort** (no duplica ids ya en disco,
`migracion.py:58-60`; una fila corrupta no rompe, `:328-329`). `tareas` NO se migra;
deja `consola.db.bak` como respaldo (`migracion.py:8-16,333-337`). Se invoca a mano:
`python -m keni_consola migrar-a-ficheros` (`__main__.py:35-47`). **No se auto-ejecuta
en el arranque** — el arranque normal (`__main__.main`) no migra ni reconstruye índice.

### 1.4 Datos del piloto AMX HOY (estado local inspeccionado)

**`~/keni-proyectos/`** (contenido YAML, fuente de verdad) — marcas en disco:
`claro-sports`, `claro-sports-golf`, `unotv`, `nacion-gamer`, `piso-15`, `keni`,
`_sin-marca`. Volumen:

| Tipo | YAML en disco | Índice (`indice.sqlite`) |
|---|---|---|
| publicaciones | **38** | publicacion: **38** ✅ coincide |
| historial | **16** | historial: **16** ✅ coincide |
| fuentes-rss | **3** | fuente_rss: **3** ✅ coincide |
| plantillas | 0 | — |
| hashtags | 0 | — |
| franjas | 0 ficheros | (no se indexa) |

El índice coincide 1:1 con el disco → la regeneración funciona en la práctica.

**`~/.config/keni-social/consola.db`** (139 KB) — todavía contiene:

| Tabla | Filas | Naturaleza |
|---|---|---|
| `publicaciones` | **8** | residuo: 6 ya migrados a YAML (mismo id), **2 DB-ONLY** |
| `skill_historial` | 4 | residuo pre-migración (los 16 vivos están en YAML) |
| `fuentes_rss` | 1 | residuo |
| `rss_items_vistos` | 1 | residuo |
| `grupos_hashtags` | 0 | — |
| `franjas` | 0 | — |
| `plantillas` | 0 | — |
| `tareas` | 0 | SIEMPRE-SQLite (vacío) |
| `comercial_publicaciones` | **0** | SIEMPRE-SQLite (vacío) |
| `comercial_snapshots` | **39** | SIEMPRE-SQLite, **39 huérfanos** (sin padre) |

**Dos anomalías a resolver antes de tocar nada:**

1. **2 publicaciones DB-ONLY** (`0447d8740548`, `df147c356cf5`): existen en
   `consola.db` pero NO tienen YAML. La migración one-shot debió crearlas; o se
   crearon en SQLite tras la migración (con `KENI_CONSOLA_BACKEND=sqlite`), o son
   residuo de pruebas. **Si se borra `db.py` sin re-migrar, se pierden.**
2. **39 `comercial_snapshots` huérfanos** con `comercial_publicaciones` vacía: la serie
   temporal apunta a piezas comerciales que ya no existen (borradas, o data de prueba).
   Hay que decidir si se conservan, se purgan o se reasocian.

Existe ya un `consola.db.bak` (106 KB, del 2026-05-24) = respaldo de la migración
previa.

### 1.5 Mapa COMPLETO entidad → almacén actual

| Entidad | Almacén HOY | Ruta / módulo | Conmutable | Fuente de verdad |
|---|---|---|---|---|
| **publicaciones** | YAML (def) / SQLite | `ficheros.py:416` · `db.py` | **Sí** (`_backend`) | YAML |
| **plantillas** | YAML (def) / SQLite | `ficheros.py:767` · `db.py` | **Sí** | YAML |
| **fuentes RSS** | YAML (def) / SQLite | `ficheros.py:897` · `db.py` | **Sí** | YAML |
| **items RSS vistos** | YAML `.keni/rss-vistos.yaml` (def) / SQLite | `ficheros.py:1035` · `db.py` | **Sí** | YAML |
| **grupos hashtags** | YAML (def) / SQLite | `ficheros.py:555` · `db.py` | **Sí** | YAML |
| **franjas** | YAML `franjas.yaml` (def) / SQLite | `ficheros.py:679` · `db.py` | **Sí** | YAML |
| **historial de skills** | YAML (def) / SQLite | `ficheros.py:1091` · `db.py` | **Sí** | YAML |
| **tareas** | **SQLite SIEMPRE** | `db.py` vía `repos.py:56-78` | No | SQLite |
| **comercial: piezas** | **SQLite SIEMPRE** | `db.py` vía `repos.py:302-354` | No | SQLite |
| **comercial: snapshots** | **SQLite SIEMPRE** (serie temporal) | `db.py` vía `repos.py:357-368` | No | SQLite |
| **índice de contenido** | **SQLite** `indice.sqlite` | `indice.py` | No (derivado) | regenerable desde YAML |
| **secretos** (clave imagen) | TOML `secretos.toml` (0600) | `secretos.py:34-39` | No | TOML |
| **preferencias** (esfuerzo gen.) | TOML `preferencias.toml` | `preferencias.py:38-43` | No | TOML |
| **sugerencias** (buzón) | JSON `sugerencias.json` | `sugerencias.py:66-70` | No | JSON |
| **termómetro mundial** | JSON `termometro.json` | `termometro.py:43-48` | No | JSON |
| **media** (imágenes) | ficheros binarios | `media.py:76-78` (`KENI_CONSOLA_MEDIA`) | No | ficheros |
| **generaciones** (jobs `claude -p`) | YAML efímeros `<id>.yaml` | `generaciones.py:100-105` | No | YAML efímero |
| **runs de agentes** | YAML `<marca>/runs/<id>.yaml` | `agentes.py:82,9` | No | YAML |
| **config consola** (allowlist proy.) | TOML `consola.toml` | `KENI_CONSOLA_CONFIG` | No | TOML |
| **marcas (catálogo)** | código + `marca.yaml` sembrado | `marcas.py:59-65` · `ficheros.py:94-103` | No | código (H3, fuera de alcance) |

**Conclusión §1:** sólo 7 entidades de CONTENIDO son conmutables; el resto ya tiene
un almacén único y coherente. El trabajo de E5 se concentra en esas 7 + decidir el
destino de `tareas` y `comercial`.

---

## 2. Diseño objetivo (según la directriz)

**Principio:** YAML = contenido editable a mano = **fuente de verdad**. SQLite =
**índice regenerable** (consulta rápida) + **datos operacionales / series temporales**
que NO son editables a mano y NO encajan en un fichero por entidad. **Se elimina el
conmutador**: `repos.py` deja de tener dos modelos de datos alternativos para el mismo
concepto.

### 2.1 Tabla entidad → almacén OBJETIVO

| Entidad | Almacén OBJETIVO | Justificación |
|---|---|---|
| publicaciones | **YAML** (único) | Contenido editorial editable a mano; ya es el defecto y la fuente de verdad |
| plantillas | **YAML** (único) | Contenido editable |
| fuentes RSS | **YAML** (único) | Config editorial por marca, editable |
| items RSS vistos | **YAML** (`.keni/`) | Estado ligado a la fuente; ya conviven en la carpeta de marca |
| grupos hashtags | **YAML** (único) | Contenido editable |
| franjas | **YAML** (`franjas.yaml`) | Config editorial por marca, editable |
| historial de skills | **YAML** (único) | Registro de contenido producido; editable/auditables |
| **índice de contenido** | **SQLite** (`indice.sqlite`) | Datos de índice/operacional; **regenerable** desde YAML. SE CONSERVA tal cual |
| **tareas** | **SQLite** (decisión D1, §2.3) | No es contenido editorial; operacional. Recomendado: queda en SQLite |
| **comercial: piezas** | **SQLite** (decisión D2) | Cabecera de una serie temporal; operacional |
| **comercial: snapshots** | **SQLite** (decisión D2) | Serie temporal append-only; NO encaja como fichero por entidad |
| secretos / preferencias / sugerencias / termómetro / media / generaciones / runs / config | **sin cambio** | Cada uno ya tiene almacén único coherente |

### 2.2 Qué se ELIMINA, qué se CONSERVA, cómo queda `repos.py`

**Se ELIMINA:**

- El **conmutador** `_backend()` y la lectura de `KENI_CONSOLA_BACKEND` (`repos.py:41-48`).
- `db.py` como **backend alternativo de CONTENIDO**: se retiran de `db.py` las
  funciones de publicaciones, plantillas, fuentes RSS, items vistos, grupos de
  hashtags, franjas e historial de skills (y su esquema). Se conserva SÓLO lo que
  SQLite debe seguir sirviendo (ver abajo).
- `migracion.py` como módulo **vivo en el árbol**: se ARCHIVA tras la migración final
  verificada (o se mueve a `scripts/` con un guard de "ya migrado"). El subcomando
  `migrar-a-ficheros` (`__main__.py:35-47`) se retira o se marca legacy.

**Se CONSERVA:**

- `ficheros.py` como **único backend de contenido**.
- `indice.py` como **índice SQLite regenerable** (ya cumple la directriz: regenerable,
  consulta rápida, no autoritativo). Sin cambios funcionales.
- `db.py` **adelgazado** a sólo: tareas + comercial (piezas + snapshots) + su esquema y
  la micro-migración `tareas.json`. Pasa de ~1592 L a ~la mitad. Decisión D1/D2 puede
  reducirlo más.

**`repos.py` objetivo** (fachada ÚNICA, sin conmutador):

- Funciones de CONTENIDO → delegan SIEMPRE en `ficheros` (1:1, sin `_backend()`).
- Funciones de tareas y comercial → delegan SIEMPRE en `db` (como hoy).
- Mismas firmas públicas: **ningún `api/*.py` cambia** (la fachada absorbe el cambio).
- Se mantiene el invariante de los tests `test_repos.py`: "todas las funciones de
  contenido existen con firma estable y son callable".

### 2.3 Decisiones que requieren al usuario (ver §5)

- **D1 — tareas:** dejarlas en SQLite (recomendado: operacional, no editorial) o
  migrarlas también a YAML para "cero SQLite de datos". Recomendación: **SQLite**, es
  coherente con la directriz (operacional, no contenido editable a mano).
- **D2 — comercial (piezas + snapshots):** la serie temporal append-only NO encaja como
  un YAML por punto. Recomendación: **SQLite** (operacional). Alternativa: piezas en
  YAML + snapshots en SQLite (mixto), pero añade un tercer patrón. Recomendado: ambas en
  SQLite.
- **D3 — huérfanos comerciales (39 snapshots sin padre):** purgar / conservar / exportar
  a `.bak`. Recomendación: **purgar** tras respaldo (son serie de piezas inexistentes).
- **D4 — 2 publicaciones DB-ONLY:** re-migrar a YAML (recomendado, no perder dato) o
  descartar si son residuo de prueba. Requiere que el usuario confirme que son reales.

---

## 3. Plan de migración paso a paso (incremental y reversible)

Cada paso es **mergeable** por sí solo y deja el sistema funcionando. El orden minimiza
riesgo: primero saneamos el estado, luego congelamos el defecto, después retiramos el
conmutador, y sólo al final adelgazamos `db.py`.

### Paso 0 — Backup y foto del estado real (PRE-requisito, sin código)

1. `cp ~/.config/keni-social/consola.db ~/.config/keni-social/consola.db.preE5.bak`
2. `cp ~/.config/keni-social/indice.sqlite ~/.config/keni-social/indice.sqlite.preE5.bak`
3. `tar czf ~/keni-proyectos.preE5.tgz -C ~ keni-proyectos`
4. Volcar conteos y checksums a un fichero de referencia:
   - Conteo por tipo en YAML (find) y en `indice.sqlite` (deben coincidir).
   - Conteo por tabla en `consola.db`.
   - `sha256` de cada YAML de contenido (manifiesto de round-trip).

**Criterio de avance:** backup verificado (re-listable) y conteos anotados.

### Paso 1 — Sanear el estado del piloto (datos, sin retirar nada)

1. **Re-correr la migración** `python -m keni_consola migrar-a-ficheros` para que las
   **2 publicaciones DB-ONLY** (D4) y cualquier residuo real de contenido salten a YAML
   (idempotente: lo ya migrado no se duplica). Verificar que `obtener_publicacion` por
   `repos` (backend ficheros) las encuentra.
2. **Reconstruir el índice** desde YAML (`ficheros.reconstruir_indice()`, o borrar
   `indice.sqlite` y dejar que se regenere) y verificar conteo índice == disco.
3. **Decidir y aplicar D3** (huérfanos comerciales): exportar a `.bak` y purgar
   `comercial_snapshots` sin padre, o conservar.

**Verificación:** conteos YAML == índice; las 2 publicaciones DB-ONLY ahora tienen
YAML; `pytest` verde.
**Reversible:** restaurar backups del Paso 0.

### Paso 2 — Congelar el defecto y blindar contra el backend SQLite de contenido

1. En `repos._backend()`: emitir un `warning` (deprecación) si
   `KENI_CONSOLA_BACKEND=sqlite`, manteniendo el comportamiento. Documentar que el
   backend SQLite de contenido está en retirada.
2. Añadir un test-guard que afirme que el defecto es `ficheros` y que ningún `api/*.py`
   importa `db` directamente para contenido (sólo vía `repos`).

**Verificación:** suite verde; el warning aparece sólo con la env explícita.
**Reversible:** revertir el commit (cambio aditivo).

### Paso 3 — Retirar el conmutador en `repos.py` (el corazón de E5)

1. Reescribir `repos.py`: las funciones de CONTENIDO delegan directamente en `ficheros`
   (eliminar `_backend()` y la rama `db`). Tareas y comercial siguen en `db`.
2. Ajustar `test_repos.py`: los tests que hoy fijan `KENI_CONSOLA_BACKEND=sqlite` para
   verificar la delegación 1:1 en `db` (`tests/test_repos.py:60-95`) se reescriben para
   verificar la delegación en `ficheros` (contenido) y en `db` (tareas/comercial).
3. Mantener intactos los tests de paridad de firma (`test_repos.py:29-44`).

**Verificación:** `pytest` verde en `consola/`; arranque manual de la consola; smoke
de un CRUD de publicación end-to-end (crear → editar → listar → borrar) que escriba
YAML real (en tmp).
**Reversible:** revertir el commit; `ficheros.py` y `db.py` intactos.

### Paso 4 — Adelgazar `db.py` (retirar el backend de contenido)

1. Eliminar de `db.py` las funciones y el esquema de las 7 entidades de contenido
   (publicaciones, plantillas, fuentes_rss, rss_items_vistos, grupos_hashtags, franjas,
   skill_historial). Conservar: tareas, comercial (piezas + snapshots), `ruta_db`,
   `_conectar`, micro-migración `tareas.json`.
2. `ficheros.py` importa de `db.py` `ESTADOS_PUBLICACION`/`ESTADOS_TAREA`
   (`ficheros.py:50`): mover esas constantes a un módulo neutro (p. ej.
   `estados.py` o reusar `redes.py`) para no dejar a `ficheros` dependiendo del `db`
   adelgazado por una constante. Aplica también a `repos.py:34-38`.
3. `migracion.py` importa `db._parsear_piezas_historial` (`migracion.py:238`): al
   archivar `migracion.py` esta dependencia desaparece; si se conserva en `scripts/`,
   llevarse también ese helper.
4. Borrar/actualizar `test_db_*.py` que prueben el backend de contenido en SQLite
   (`test_db_publicaciones.py`, `test_db_contenido.py`, `test_db_pr_backend.py`); dejar
   `test_db.py` cubriendo sólo tareas/comercial.

**Verificación:** `pytest` verde; `ruff` limpio; no quedan referencias a las funciones
borradas (grep).
**Reversible:** revertir el commit; el contenido vive en YAML y ya no depende de estas
funciones.

### Paso 5 — Archivar `migracion.py` y limpiar el subcomando

1. Mover `migracion.py` a `scripts/` (o eliminar) con guard "ya migrado".
2. Retirar el subcomando `migrar-a-ficheros` de `__main__.py:35-47` (o marcarlo legacy
   apuntando al script archivado).
3. Actualizar `docs/arquitectura.md` y la cabecera de `repos.py` para reflejar el
   diseño final (un backend de contenido + índice regenerable + SQLite operacional).

**Verificación:** suite verde; docs coherentes; arranque normal sin warnings.
**Reversible:** restaurar el módulo desde git.

### 3.1 Cómo se REGENERA el índice (ya implementado, a apoyarse en él)

- Borrar `indice.sqlite` → en la primera consulta, `_listar_validado` detecta índice
  vacío con ficheros en disco y reconstruye el tipo (`ficheros.py:314-316`).
- Forzado completo: `ficheros.reconstruir_indice()` (`ficheros.py:295-298`).
- **Punto de verificación de round-trip:** tras regenerar, conteo por tipo en índice ==
  conteo de ficheros YAML por tipo; y `listar_*()` devuelve el mismo conjunto de ids
  antes y después de borrar el índice.

---

## 4. Rollback

**Backup previo (Paso 0):** copias `.preE5.bak` de `consola.db` e `indice.sqlite`, y
tarball de `~/keni-proyectos`. Más el `consola.db.bak` ya existente.

**Rollback por paso:**

| Paso | Cómo volver atrás |
|---|---|
| 0 | n/a (sólo backup) |
| 1 (saneo datos) | Restaurar `consola.db`/`indice.sqlite`/`keni-proyectos` desde `.preE5.bak`/tarball |
| 2 (deprecación) | `git revert` del commit (cambio aditivo) |
| 3 (retirar conmutador) | `git revert`; `ficheros.py`/`db.py` quedan intactos, los datos no se tocan |
| 4 (adelgazar db.py) | `git revert` restaura las funciones; el contenido sigue en YAML (no se pierde nada) |
| 5 (archivar migración) | Restaurar `migracion.py` desde git |

**Criterios de ABORT (parar y revertir):**

- Tras Paso 1, conteo índice ≠ conteo YAML, o desaparece alguna publicación que estaba
  en YAML.
- Cualquier paso deja `pytest` o `ruff` en rojo y no se arregla en la misma sesión.
- El smoke end-to-end (crear/editar/listar/borrar publicación) no hace round-trip por
  disco YAML.
- Se detecta pérdida de dato real del piloto comparando con el manifiesto sha256 del
  Paso 0.

**Nota de seguridad:** mientras `db.py` conserve las funciones de contenido (hasta
Paso 4), el rollback es trivial porque ambos backends coexisten. El punto de no retorno
"barato" es Paso 4; por eso va al final y exige el manifiesto del Paso 0 verde.

---

## 5. Riesgos y verificación

### 5.1 Riesgos principales

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Pérdida de las 2 publicaciones DB-ONLY** al retirar `db.py` | Re-migrar en Paso 1 ANTES de adelgazar; verificar por id en YAML |
| R2 | **Snapshots comerciales huérfanos** (39) ensucian o se pierden sin decisión | Decisión D3 explícita + respaldo antes de purgar |
| R3 | Alguien arranca con `KENI_CONSOLA_BACKEND=sqlite` y crea contenido nuevo en SQLite tras la retirada | Paso 2 deprecación + guard; Paso 3 elimina la env; documentar |
| R4 | Índice desincronizado del disco (mtime / edición externa) | Apoyarse en re-indexado por mtime ya existente; reconstrucción completa en Paso 1; test de round-trip |
| R5 | `ficheros.py` depende de constantes de `db.py` (`ESTADOS_*`) y al adelgazar se rompe el import | Paso 4.2: mover constantes a módulo neutro antes de tocar `db.py` |
| R6 | Datos del piloto en la máquina del operador AMX difieren del estado local del autor | Correr el plan PRIMERO contra una copia del estado real de AMX; no asumir el estado del autor |

### 5.2 Tests / guards a añadir

- **Guard de round-trip índice↔YAML:** crear N entidades, borrar `indice.sqlite`,
  reconstruir, afirmar mismos ids/conteos (apoya el contrato de regenerabilidad).
- **Guard de un solo backend:** afirmar que `repos` ya no lee `KENI_CONSOLA_BACKEND` y
  que las funciones de contenido escriben YAML en disco (no tocan `consola.db`).
- **Guard anti-regresión de API:** la suite `tests/test_api_*` (publicaciones, rss,
  plantillas, franjas, hashtags, sugerencias, etc.) debe pasar SIN cambios — prueba que
  la fachada absorbió el cambio.
- **Test de migración final:** mantener `test_migracion.py` mientras exista la
  migración; al archivarla, convertirlo en un test del script archivado o eliminarlo.

### 5.3 Validación contra datos reales del piloto (antes de "hecho")

1. Correr el plan sobre una **copia del estado real de AMX** (no sólo el del autor).
2. Comparar manifiesto sha256 de YAML pre/post: el contenido editorial no debe cambiar.
3. Conteos índice == disco en todas las marcas (`claro-sports`, `unotv`, `nacion-gamer`,
   `piso-15`, `claro-sports-golf`, `keni`).
4. Smoke manual de la consola: listar publicaciones por marca, editar una, ver que el
   YAML cambia y el índice refleja el cambio.

### 5.4 Verificación (no hay CI activo — mirror local)

GitHub Actions está **desactivado** (`git log`: "elimina el workflow de CI"); no hay
`.github/workflows/` ni script de mirror. La verificación es **local por paquete**:

- `consola/`: `pytest` (suite amplia, fixtures aíslan todo en `tmp_path` vía env vars,
  `tests/conftest.py`) + `ruff check`.
- `mcp-metricas/`: `pytest` + `ruff` (no afectado por E5).
- `frontend/`: `tsc` + `vitest` + build (no afectado por E5: el backend mantiene firmas
  y formas de respuesta).
- Cada ola NO se mergea si pytest/ruff de `consola/` no están en verde.

### 5.5 Qué necesita confirmación humana o credenciales

- **D1–D4** (§2.3): decisiones de diseño/dato que sólo el usuario puede aprobar
  (tareas, comercial, huérfanos, publicaciones DB-ONLY). **Ninguna requiere
  credenciales.**
- **Acceso al estado real de AMX** para §5.3 (copia del `~/.config/keni-social` y
  `~/keni-proyectos` de la máquina del operador piloto). No son secretos de red, pero sí
  datos del cliente: requiere el OK del usuario para manipularlos.
- **Ninguna credencial de red** (Meta/YouTube/X/TikTok) interviene: E5 no toca el MCP de
  métricas ni `secretos.toml`.

---

## 6. Troceado propuesto en sub-issues / olas

Cada ola es mergeable a `main` y verificable con `pytest`+`ruff` de `consola/`.

| Ola | Issue (propuesta) | Contenido | Riesgo | Reversible |
|---|---|---|---|---|
| **E5-0** | Backup + manifiesto del estado del piloto | Paso 0: copias `.preE5.bak`, tarball, conteos y sha256. Sólo datos/doc. | Nulo | n/a |
| **E5-1** | Saneo de datos del piloto | Paso 1: re-migrar (D4), reconstruir índice, resolver huérfanos (D3). Sólo datos. | Bajo | Sí (backups) |
| **E5-2** | Deprecar el backend SQLite de contenido | Paso 2: warning + guards (defecto ficheros, API no importa `db` para contenido). Aditivo. | Bajo | Sí |
| **E5-3** | Retirar el conmutador en `repos.py` | Paso 3: `repos` delega siempre en `ficheros` para contenido; reescribir `test_repos.py`. | **Medio** | Sí (revert) |
| **E5-4** | Adelgazar `db.py` (sólo tareas + comercial) | Paso 4: quitar funciones/esquema de contenido; mover `ESTADOS_*` a módulo neutro; limpiar `test_db_*`. | **Medio-alto** | Sí (revert; datos en YAML) |
| **E5-5** | Archivar `migracion.py` y limpiar CLI/docs | Paso 5: mover a `scripts/`, retirar subcomando, actualizar `arquitectura.md` y cabeceras. | Bajo | Sí |

**Dependencias:** E5-0 → E5-1 → E5-2 → E5-3 → E5-4 → E5-5 (estrictamente secuencial; el
punto de no retorno barato es E5-4, que va al final). **Olas previas de la auditoría
(Q1-Q4, E1) son independientes** y pueden ir antes; E5 NO depende de la capa
`keni-shared` salvo por el detalle de R5/E5-4.2 (mover constantes), que puede resolverse
con un módulo local sin esperar a `keni-shared`.

---

*Plan de persistencia, sólo análisis y diseño. No se modificó código ni se migró ningún
dato. Severidades y decisiones (D1–D4) requieren aprobación del usuario antes de
ejecutar. Validar SIEMPRE contra una copia del estado real del piloto AMX, no sólo
contra el estado local del autor.*
