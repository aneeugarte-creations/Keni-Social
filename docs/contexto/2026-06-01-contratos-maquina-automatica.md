# Contratos congelados — máquina automática de contenido (Paso 0)

> Fecha: 2026-06-01 · Estado: CONGELADO (paso 0 de §3.bis del plan
> `2026-06-01-maquina-automatica-plan.md`). Este documento fija los contratos COMPARTIDOS
> para que los flujos concurrentes A/B/C/D/E no diverjan. No describe diseño nuevo: refleja
> lo que YA existe en el repo y los pocos cambios transversales que introduce este paso 0.
> Si un flujo necesita cambiar algo de aquí, se modifica ESTE documento primero.

## Por qué este documento

Las fases se ejecutan en paralelo, cada una en su worktree. Lo que hace seguro el paralelismo
es acordar ANTES los seams compartidos (forma del borrador, tabla red→formatos, flags, el
nuevo origen). Los cambios de enums/flags que tocarían módulos transversales
(`estados.py`, `config.py`, `repos.py`) se hacen aquí, una vez, para que los flujos no
compitan por ellos.

---

## (a) Forma del borrador/pieza y el seam A→C

**Propiedad:** app C (Operación). Módulo único: `consola/src/keni_consola/dominio/publicaciones.py`.

El modelo es padre + hijos: `contenido` (tema del tablero) + `contenido_plataforma` (una fila
por red). Una pieza publicable vive como fila `contenido_plataforma` con `es_publicacion=1`.

**Campos de texto (NO renombrar — son el contrato):**

- `contenido`: el copy que ACOMPAÑA a la publicación (el cuerpo del post por red).
- `copy_in`: el texto que va DENTRO de la imagen (copy-in / placa), distinto de `contenido`.
- `titulo`, `marca`, `red`, `veredicto`, `estado`, `origen`.
- Imagen: `imagen` (archivo de media compuesto), `foto` (media id de la foto cruda de fondo),
  `imagen_fuente` (URL externa de la fuente), `tipo_contenido` ∈ `{ia, galeria, fuente}`.
- Checklist por red: `falta_copy`, `falta_imagen`, `falta_revision`, `falta_publicar`.

La forma pública serializada la fija `publicaciones.publicacion_a_dict(...)` (es el único
serializador; consumidores NO re-serializan a mano).

**Seam A→C (handoff, ADR 0005 §Seams #1) — la ÚNICA puerta de creación que A usa:**

- `publicaciones.crear_borrador(marca, red, *, titulo, contenido, copy_in, veredicto, origen,
  imagen, imagen_fuente, tipo_contenido, evergreen, autor)` → pieza nueva con padre propio.
- `publicaciones.crear_borrador_en(contenido_id, marca, red, ...)` → NIDA el borrador bajo un
  tema EXISTENTE del tablero (crea la fila `contenido_plataforma` con `es_publicacion=1`,
  estado `pendiente` == `borrador` editorial, `falta_copy=False`). Devuelve `None` si el tema
  no existe. Es el camino que usa la auto-generación (vía `dominio.generar.lanzar_copy` con
  `contenido_id`), para que el borrador cuelgue de su tema origen.

Invariantes del seam (NO los toque ningún flujo):

- El estado inicial SIEMPRE es `borrador`/`pendiente`. A NO puede crear algo ya
  aprobado/programado por esta vía (`crear_borrador` no expone `estado`).
- Revisión, programación y publicación son responsabilidad EXCLUSIVA de C. A no llama a
  `repos.crear_publicacion` directamente.
- Estados de una fila por plataforma (`estados.ESTADOS_CONTENIDO_PLATAFORMA`):
  `pendiente → en_curso → en_revision → aprobado → programado → publicado`.

El gate humano vive en C (cola de revisión / aprobación multinivel) y permanece intacto en
todas las fases: la IA produce hasta el borrador; el humano aprueba cada pieza y autoriza
cada publicación.

---

## (b) Tabla `red → formatos` — propiedad del Flujo B

Hoy NO existe. `consola/src/keni_consola/limites_plataforma.py` solo cubre LÍMITES DE TEXTO
por plataforma, no la matriz de recortes de imagen.

**El modelo de datos `red → formatos` (la matriz de §5 del plan: 9:16 / 4:5 / 1:1·16:9) es
propiedad EXCLUSIVA del Flujo B (Fase 3, arte multi-formato).** Ningún otro flujo lo define ni
lo modela. El Flujo D (feed) y el Flujo C (orquestación) lo CONSUMEN cuando el Flujo B lo haya
mergeado; hasta entonces no asumen su forma. Este paso 0 NO crea esa tabla a propósito (evita
que dos flujos definan el mismo modelo).

---

## (c) Flags y `origen='equipo'`

### Flags (semántica ya existente en `config.py`; este paso 0 NO los renombra ni cambia sus
defaults)

Los cuatro accesores YA existen y leen vía `_crudo` (precedencia store editable > env >
default). Todos default OFF (conservador). No se añadió ningún helper nuevo.

| Flag (env) | Accesor `config.*` | Default | Semántica |
|---|---|---|---|
| `KENI_RADAR_AUTO` | `radar_auto_activo()` | OFF | Daemon que auto-promueve temas virales del Radar a `flujo='importante'` (origen `radar-auto`). |
| `KENI_AUTOGEN` | `autogen_activo()` | OFF | Daemon que encola COPY para temas de fuente sin copy y con marca. Nada se publica solo. |
| `KENI_AUTOGEN_ARTE` | `autogen_arte_activo()` | OFF | Daemon que genera ARTE por IA para temas con copy pero sin imagen. Sin proveedor de imagen, degrada (no hace nada). |
| `KENI_PUBLICAR_REAL` | `publicar_real()` | OFF | Gate de publicación REAL vía Metricool. OFF = dry-run (solo estampa `preparado_en`). |

**Estado de VALIDACIÓN (decisión de dirección 2026-06-01):** `KENI_RADAR_AUTO`,
`KENI_AUTOGEN`, `KENI_AUTOGEN_ARTE` = ON; `KENI_PUBLICAR_REAL` = OFF. Es seguro encender los
tres primeros en el hosted del piloto: con `KENI_PUBLICAR_REAL` OFF, todo para en la cola de
revisión y nada sale a redes sin que el humano lo autorice. (El encendido efectivo en el
deploy lo aplica el Flujo C; este paso 0 solo fija la semántica.)

**Cómo encender los flags para validar (Flujo C, Fase 2):** el procedimiento concreto (en
caliente vía `/data/ajustes.toml` o por env en `deploy/docker-compose.yml`), por qué es seguro
(todo para en la cola de revisión, gate humano intacto) y cómo observar el avance está en
`deploy/README.md` §"Encender la tubería automática para VALIDACIÓN". El servicio que corre los
daemons en prod es `daemons` (`python -m keni_consola.daemons`), que ahora arranca también
`autogen_copy`/`autogen_arte` (gateados; def OFF). Los DEFAULTS de los flags siguen OFF en código.

Tuning asociado (sin cambios): `KENI_AUTOGEN_MAX` (def 3), `KENI_AUTOGEN_INTERVALO_HORAS`
(def 1), `KENI_AUTOGEN_ARTE_MAX` (def 3), `KENI_RADAR_AUTO_UMBRAL` (def 50000), etc.

### `origen='equipo'` (nueva fuente de auto-generación)

Definido en este paso 0 en el módulo neutro `estados.py`:

- `estados.ORIGEN_EQUIPO = "equipo"`: el `origen` con que nace un alta CREATIVA del equipo
  (foto/nota/idea con marca). Decisión de dirección: se AUTO-GENERA SIEMPRE (no opt-in).
- `estados.ORIGENES_AUTOGEN`: tupla de orígenes que la auto-generación de copy trata como
  "tema redactable" = fuentes externas históricas (`import-calendario`, `radar-auto`,
  `radar`, `rss`) + `equipo`.
- `autogen_copy.ORIGENES_TOPIC` ahora deriva de `estados.ORIGENES_AUTOGEN` (fuente única; ya
  no lista literales sueltos). El daemon de auto-copy procesa `origen='equipo'` igual que a
  una fuente externa (mismo pipeline `dominio.generar.lanzar_copy`).

**Distinción clave (la inversión del plan, §2):** `origen='equipo'` se auto-genera; el alta
TECLEADA legada (`origen=""`) sigue EXCLUIDA de la auto-generación (lo genera quien lo crea,
si quiere). El test `test_omite_origen_manual` (origen `""`) sigue verde; un nuevo test cubre
que `equipo` SÍ entra.

**Límite de alcance de este paso 0:** se fija el VALOR del origen y la REGLA (auto-genera).
El endpoint/UI que da de alta material con `origen='equipo'`, y cualquier cambio de la lógica
del daemon, son del **Flujo A** (Fase 1). `origen` es texto libre en `repos.crear_contenido`
(no hay enum duro en la DB), así que el Flujo A solo tiene que crear el `contenido` con
`origen=estados.ORIGEN_EQUIPO`; el daemon ya lo recogerá.

---

## Resumen de cambios de este paso 0

- `consola/src/keni_consola/estados.py`: + `ORIGEN_EQUIPO`, + `ORIGENES_AUTOGEN`.
- `consola/src/keni_consola/autogen_copy.py`: `ORIGENES_TOPIC` deriva de `ORIGENES_AUTOGEN`
  (incluye `equipo`); comentario de exclusión invertido para el alta creativa.
- `consola/tests/test_autogen_copy.py`: + cobertura de `origen='equipo'`.
- Flags: SIN cambios de código (los accesores ya existían con la semántica correcta).
- Tabla `red→formatos`: NO se crea aquí (propiedad del Flujo B).
