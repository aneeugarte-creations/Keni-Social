# Runbook de endurecimiento — pasos de HOST (manuales)

Paso que el OPERADOR ejecuta en el server (`ssh latitude`) para acotar las credenciales de
GitHub que hoy montan los workers. No toca `docker compose` ni el repo: es config de host
(`.env` del host + un eventual cambio de volumen).

---

## A — PAT de GitHub minimo + segregar credenciales del volumen compartido

### A.1 PAT fine-grained de scope minimo para los workers que pushean

Los carriles de auto-desarrollo (`worker-dev`, `worker-ralph`) pushean a `main`. Hoy usan una
credencial mas amplia de la necesaria. Crea un **PAT fine-grained** acotado:

1. GitHub -> Settings -> Developer settings -> Fine-grained tokens -> Generate.
2. **Resource owner**: `kenitech-io`. **Repository access**: solo `kenitech-io/keni-social`.
3. **Permissions**: SOLO `Contents: Read and write`. Nada mas (ni workflows, ni admin, ni metadata
   extra mas alla del minimo obligatorio). Caducidad corta y rotacion calendarizada.
4. Ponlo en el `.env` del host (`/home/ubuntu/keni-social/deploy/.env`, NO en git) en la variable
   que consumen esos workers para `gh`/git push. Recrea solo esos servicios en la siguiente
   ventana (`docker compose up -d worker-dev worker-ralph`).

### A.2 Segregar `/data/gh` y `secretos.toml` del volumen `keni-data` (DOCUMENTADO, no aplicado)

**Estado: NO aplicado en el compose.** Es un cambio de modelo de volumen con riesgo; se deja como
paso manual a evaluar, no se toco `deploy/docker-compose.yml`.

Hoy `back`, `daemons`, `worker` y `transcriptor` montan el MISMO volumen `keni-data` en `/data`,
que contiene de todo: media, modelo whisper, `claude-cfg/`, `ajustes.toml`, **`secretos.toml`** y
**`/data/gh`** (credenciales de GitHub). Consecuencia: servicios que NO necesitan esas credenciales
las tienen igualmente montadas:

- `transcriptor`: solo necesita cola (Postgres), media (S3) y el modelo whisper. NO necesita
  `secretos.toml` ni `/data/gh`. Sin embargo monta `keni-data:/data` entero.
- `worker` (contenido): SI usa `secretos.toml` (clave de generacion de imagen), pero NO `/data/gh`.

**Por que NO se aplica en el compose ahora**: las credenciales viven DENTRO del unico volumen
`keni-data`, no como ficheros/volumenes propios. Quitarlas de un servicio implica:
  1. mover `secretos.toml` y `gh/` a su propio volumen (p.ej. `keni-secrets`) o a Docker secrets, y
  2. cambiar el codigo que hoy los lee por ruta fija bajo `/data` (`KENI_DATA_DIR`).
Hacerlo mal deja a `back`/`daemons` (que SI los necesitan: login de Claude, push) sin credenciales
-> rompe generacion y auto-desarrollo. Es un cambio coordinado codigo+volumen+migracion de datos,
fuera del alcance "limpio y sin riesgo".

**Camino recomendado cuando se aborde** (ventana de mantenimiento):

1. Crear volumen `keni-secrets` y mover ahi `secretos.toml` y `gh/` (copia, no move, hasta validar).
2. Montar `keni-secrets` SOLO en los servicios que lo necesitan: `secretos.toml` -> `back`,
   `daemons`, `worker`; `gh/` -> solo los carriles que pushean (`daemons`, `worker-dev`,
   `worker-ralph`). `transcriptor` deja de ver ambos.
3. Ajustar el codigo a la nueva ruta (o symlink de compat bajo `/data`).
4. Validar generacion, login de Claude, push de auto-dev y transcripcion antes de borrar las copias
   viejas de `keni-data`.

**Riesgo si se omite**: un compromiso del contenedor `transcriptor` (imagen con faster-whisper,
egress a HuggingFace) expone hoy `secretos.toml` y el PAT de `/data/gh` pese a no usarlos. La
segregacion reduce ese blast radius. Es endurecimiento de defensa en profundidad, no un agujero
explotable por si solo (el contenedor corre como no-root, sin sock, en redes internas).
