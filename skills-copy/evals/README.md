# evals — calidad del copy de skills-copy

El copy es el producto, pero las skills no tenían evaluación automática. Esto la
añade en **dos capas** separadas a propósito por su coste y sus dependencias:

| Capa | ¿Usa el modelo? | ¿En CI? | Qué comprueba |
|---|---|---|---|
| **Estática** | No | **Sí** | Estructura del repo + unidad de `contar.py` |
| **Local (gate)** | Sí (`claude -p`) | **No** | Propiedades del copy que genera la skill |

La capa estática corre en cualquier runner con solo Python. La capa local **no es
para CI**: necesita Claude (consume modelo) y, para los casos de clip, whisper en
local. Es un gate que corres en tu máquina antes de confiar en un cambio de
skill/contexto.

---

## Capa 1 — Chequeos estáticos (CI-safe, sin modelo)

Python puro, sin dependencias de terceros (pytest es opcional). Ficheros:

- **`test_static.py`** — estructura del repo:
  - Cada `SKILL.md` tiene el frontmatter obligatorio: `name`, `description`,
    `allowed-tools` (y `name` coincide con la carpeta).
  - `contexto-editorial/` tiene los ficheros que las skills cargan:
    `plataformas.md`, `tropicalizacion.md`, `reglas-legales.md`, las 5 marcas
    (`claro-sports`, `fundacion`, `nacion-gamer`, `piso-15`, `unotv`) y
    `voces/_plantilla.md`.
  - **Unit test de `contar.py`**: cuenta *code points*, no bytes — acentos
    (`café` = 4) y emojis (`hola 😀` = 6) cuentan **1** cada uno; quita el salto
    final que añade el heredoc. Se prueba importando la lógica **y** invocando
    `contar.py` por subproceso (como hace la skill). No se modifica `contar.py`.
- **`test_checks_copy.py`** — prueba el *motor* de aserciones de la capa local
  (`checks.py`) con fixtures sintéticos de copy "bueno" y "malo", para que la
  lógica del gate esté verificada en CI aunque el gate en sí no corra ahí.
- **`checks.py`** — módulo compartido por ambas capas (sin dependencias).

### Cómo correrlos

```bash
# con pytest (recomendado; lo usa CI)
python3 -m venv .venv && .venv/bin/pip install pytest -q
.venv/bin/pytest -q           # desde skills-copy/evals/

# o sin pytest, como script (mini-runner integrado)
python3 test_static.py
python3 test_checks_copy.py
```

CI los ejecuta en el job `skills-copy-estatico` de `.github/workflows/ci.yml`
(solo Python + pytest + PyYAML, con `keni-shared` instalado para anclar los
límites a su fuente única; sin Claude, sin whisper, sin red). El job corre
`test_static.py`, `test_checks_copy.py`, `test_limites.py` y
`test_wave3_skills.py`.

---

## Capa 2 — Corredor local (gate con modelo)

`run.sh` ejecuta una skill en **headless** (`claude -p`) contra una fixture de
`ejemplos/`, captura la salida y le pasa `assert_output.py`, que corre las
**propiedades deterministicas** sobre el copy generado:

1. **X ≤ 280** y **cada tuit del hilo ≤ 280** (contando con `contar.py`).
2. **Título de YouTube ≤ 70**.
3. **Bloque de auto-verificación presente**: al menos un símbolo `✅`/`⚠️`/`❌`
   **y** un veredicto (`Veredicto:` / `LISTO PARA APROBAR` / `LISTO TRAS
   VERIFICAR`).
4. **Sin "bandera con escudo"**: no propone la bandera de México con escudo
   nacional (prohibida por `reglas-legales.md`); "bandera sin escudo" sí pasa.
5. **Fidelidad**: no afirma un **número** ni una **cita** que no esté en la
   fuente (compara contra el/los `.md` de `ejemplos/`, ignorando numeración de
   hilo/slide y el propio bloque de verificación).

Estas son propiedades *deterministicas* (no juzgan estilo): comprueban que el
copy no rompe un límite duro ni inventa datos. La calidad subjetiva sigue siendo
del humano que aprueba.

### Requisitos (por qué no va en CI)

- `claude` en el PATH y con sesión iniciada (**consume modelo**).
- Para el caso **clip**: `whisper-cli` (whisper.cpp) + `ffmpeg` + el modelo local
  — `clip-a-copy` transcribe **en local** y el audio no sale de la máquina (ver
  `../../docs/despliegue-local.md`). El caso clip genera un audio de prueba con
  `ejemplos/generar-clip-prueba.sh` si no le pasas uno.
- `python3` para las aserciones.

### Cómo correrlo

```bash
# desde skills-copy/evals/
bash run.sh nota     # copy-desde-nota con los dos cables (cross-check 40/45 mde)
bash run.sh clip     # clip-a-copy (transcribe en local y evalúa)
bash run.sh all      # ambos
KENI_EVAL_KEEP=1 bash run.sh nota   # conserva el output capturado en .out/
```

`run.sh` lanza `claude` con el cwd en la raíz de `skills-copy/` para que Claude
Code descubra `.claude/skills/` y resuelva las rutas del contexto editorial.

### Evaluar un output ya capturado (sin volver a llamar al modelo)

```bash
python3 assert_output.py \
  --salida mi_output.txt \
  --fuente ../ejemplos/cable-1.md --fuente ../ejemplos/cable-2.md \
  [--ignorar-numero 2026]
```

Sale `0` si todas las propiedades se cumplen, `!=0` si alguna falla (con el
detalle por comprobación).

---

## Por qué la separación

- Las propiedades **estructurales** (frontmatter, ficheros, conteo de
  caracteres) no dependen del modelo: deben fallar el build si alguien rompe el
  contrato. Van en CI.
- Las propiedades del **copy generado** requieren generar copy (modelo) y, para
  clip, transcribir audio local. Meter eso en CI lo haría lento, no determinista
  y dependiente de credenciales/binarios. Por eso es un **gate local**
  documentado, no un check de CI.
