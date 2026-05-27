# deploy/ — keni-social dockerizado (stack hosted/equipo)

`docker compose` que levanta keni-social como **servicio compartido** (ADR
[0001](../docs/adr/0001-runtime-servicio-compartido.md) /
[0002](../docs/adr/0002-descomposicion-monolito-modular-catalogo-apps.md), Fase C):

| Servicio | Imagen | Rol | Expuesto |
|---|---|---|---|
| `traefik` | `traefik:v3` | Reverse proxy + TLS (Let's Encrypt), `network_mode: host` | **:80/:443** |
| `front` | build `front/` | SPA React (nginx) | vía Traefik (todo menos `/api`) |
| `back` | build `back/` | Gateway Starlette; **ENCOLA** la generación (sin Node/`claude`) | vía Traefik (`/api`) |
| `worker` | build `worker/` | Consume la cola y corre **`claude -p`** (#130 Fase 2) | interno |
| `mcp` | build `mcp/` | `keni-metricas` por HTTP | interno (ver abajo) |
| `db` | `postgres:16` | Estado compartido + **cola de jobs** | interno |
| `files` | `dxflrs/garage` | Object storage S3 (media) | interno |

> El contexto de build de las imágenes propias es la **raíz del repo** (`..`),
> porque necesitan `keni-shared/ + mcp-metricas/ + consola/ + skills-copy/`.

---

## ⚠️ Lee esto antes de nada: estado honesto

Esto **dockeriza la arquitectura objetivo**, pero el código aún no la consume entera:

- **Postgres (`db`) y Garage (`files`) ya los CONSUME el back (#130).** El backend de la
  persistencia operacional lo elige el entorno:
  - **Con `DATABASE_URL`** (este stack la cablea) → la DB operacional (tareas, comercial,
    rota, usuarios/sesiones) va a **Postgres**. **Sin** `DATABASE_URL` (perfil local/privado)
    → SQLite, como siempre (ADR 0001/0002): el modo local NO cambia.
  - **Con `S3_*`** (endpoint + credenciales) → la media va al **bucket Garage/S3**. Sin S3
    → disco (`/data/keni-social/media`), como siempre.
  El cutover de los datos que hoy viven en SQLite+disco se hace UNA vez con
  `python -m keni_consola.migracion` (idempotente; ver "Cutover a Postgres + S3" abajo).
  **FUERA de alcance (#130):** el contenido editorial YAML (`ficheros.py`,
  `/data/keni-proyectos/<marca>/...`) y su índice regenerable (`indice.py`) **siguen en el
  volumen** (`keni-data`/`KENI_DATA_DIR`); migrarlos a object storage es trabajo futuro.
- **Generación DESACOPLADA (#130 Fase 2 / ADR 0002 Fase B).** El `back` ya **no** ejecuta
  `claude -p`: **ENCOLA** un job (tabla `jobs` en Postgres) y responde al instante. El
  servicio **`worker`** clava el job, reconstruye prompt + post-procesado desde el `spec`
  serializado y corre **`claude -p`** (con todo el endurecimiento #137: grupo de procesos
  propio, kill del árbol al timeout/cancel, tope de concurrencia, sin huérfanos). Por eso
  **`worker` lleva Node + la CLI `claude` y `back` ya no** (`KENI_WORKER_EXTERNO=1` en el
  back evita que levante su worker in-proceso). La generación **sigue siendo `claude -p`**
  (ADR 0001): el worker **no** usa la API de Claude. *Reiniciar el back NO mata los jobs en
  curso del worker* (es otro contenedor). En **local / un solo proceso** no hace falta el
  servicio: el back arranca el worker **en proceso** (un hilo), y la UX no cambia.
- **whisper (clip→copy) NO está en hosted.** Por privacidad (el audio no sale de la
  máquina), la transcripción es del perfil local. El gateway hosted no transcribe.
- **Expuesto públicamente tras auth (login multiusuario + CSRF; token interino OPCIONAL).**
  La barrera **principal** de `/api` es el **login multiusuario** user/pass + roles (#130):
  sesión server-side (cookie `keni_consola_sesion`, HttpOnly+SameSite=Strict). El admin
  inicial se crea desde `KENI_CONSOLA_ADMIN_USER/PASS` (o pass aleatoria logueada). Sobre
  eso, **CSRF en mutaciones** por `Origin`/`Referer`: detrás de Traefik el `Origin` del SPA
  es el host **público** (`social.kenitech.io`), que el back puede no ver byte a byte como
  `Host`, por eso `KENI_CONSOLA_ORIGENES` (cableado a `KENI_HOST`) lo declara como host de
  confianza — sin él las mutaciones del SPA darían 403; un `Origin` ajeno se sigue
  rechazando. `KENI_CONSOLA_HTTPS=1` marca las cookies `Secure` (Traefik termina TLS). El
  **token interino** (`KENI_CONSOLA_TOKEN`) es ahora un **gate EXTRA OPCIONAL**, no un
  requisito: si lo dejas vacío, el back queda igualmente protegido por **sesión + CSRF** (sin
  sesión válida → 401 en `/api`). Si lo pones, sigue valiendo como credencial adicional de
  mantenimiento. El bind `0.0.0.0` del back solo lo alcanza Traefik.
- **Claude (generación) usa el OAuth token de la máquina**, no una API key: el back
  recibe `CLAUDE_CODE_OAUTH_TOKEN` desde `/etc/learn-platform/claude-oauth-token`.

---

## Ingress (estado actual: Traefik único, Caddy retirado)

**HECHO.** En el servidor Latitude (162.43.191.103) Traefik es el **ingress único**
(`network_mode: host`, dueño de `:80/:443`, ACME Let's Encrypt). El Caddy de sistema
fue **parado y deshabilitado** (`sudo systemctl disable --now caddy`). Traefik sirve,
además de keni-social:

- `social.kenitech.io` → front / back (este stack). **LIVE.**
- `code.kenitech.io`   → `127.0.0.1:9001` (code-launcher), router en `traefik/dynamic/legacy-sites.yml`.
- `api.kenitech.io`    → `127.0.0.1:8080` (learn-control-plane) + CORS replicado.

`network_mode: host` es necesario porque code/api escuchan **solo en `127.0.0.1`**
(un Traefik en bridge no los alcanza). `learn.kenitech.io` **no vive en este box**
(su DNS apunta a `187.124.247.53`), por eso no tiene router aquí.

**Rollback de emergencia** (restaura code/api bajo Caddy):
`docker compose stop traefik && sudo systemctl start caddy`.

---

## Conexión al servidor

```bash
ssh -i ~/.ssh/ai-learning ubuntu@162.43.191.103
```
- Usuario `ubuntu` (sudo NOPASSWD). Llave SSH `~/.ssh/ai-learning` (el privado **no**
  está en el repo). Origen del acceso: `keni/code-kenitech/infra/deploy.sh`.
- El stack vive en `/home/ubuntu/keni-social/deploy`. Operar desde ahí:
  `docker compose ps` · `docker compose logs -f back` · `docker compose up -d`.
- Rollback de emergencia (restaura code/api bajo Caddy):
  `docker compose stop traefik && sudo systemctl start caddy`.

## Requisitos en el host

```bash
# El plugin compose v2 NO está instalado en el servidor Latitude; Docker sí.
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
docker compose version            # comprobar
```

`ubuntu` ya está en el grupo `docker` (no hace falta sudo para docker).

## DNS

Hace falta `social.kenitech.io → 162.43.191.103` (A, **sin proxy** de Cloudflare —
Let's Encrypt necesita acceso directo para el challenge HTTP). El DNS de la zona lo
gestiona Terraform en `keni/devops-iac/cloudflare/dns/`. Añade el registro al mapa
`custom_records` de `terraform.tfvars` (donde ya están `code` y `api`):

```hcl
custom_records = {
  "code"   = "162.43.191.103"
  "api"    = "162.43.191.103"
  "social" = "162.43.191.103"   # <-- añadir
}
```

y aplica (necesita `CLOUDFLARE_API_TOKEN`, que vive en ansible-vault
`devops-infra: inventory/keni-prod/group_vars/all/secrets.yml`):

```bash
cd keni/devops-iac/cloudflare/dns
export CLOUDFLARE_API_TOKEN=...   # desde el vault
terraform plan    # revisa que SOLO añade el record social
terraform apply
```

## Arranque

```bash
cd deploy
cp .env.example .env
# Rellena .env. Genera secretos:
#   openssl rand -base64 24   (tokens/passwords)   ·   openssl rand -hex 32   (GARAGE_RPC_SECRET)
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f back     # el admin inicial (#130) se loguea aquí en el 1er arranque
```

El primer arranque crea el admin desde `KENI_CONSOLA_ADMIN_USER/PASS` (si la BD no
tiene usuarios). Entra por `https://social.kenitech.io`.

## Bootstrap de Garage (una sola vez)

Garage arranca "vacío": hay que asignar layout y crear bucket + clave.

```bash
G="docker compose exec files /garage"
$G status                                   # copia el ID del nodo
$G layout assign -z dc1 -c 50G <NODE_ID>
$G layout apply --version 1
$G bucket create keni-media
$G key create keni-back                     # apunta Key ID + Secret
$G bucket allow --read --write keni-media --key keni-back
```
Pon el Key ID/Secret en `.env` (`S3_ACCESS_KEY`/`S3_SECRET_KEY`) y `docker compose up -d`.
Con esas vars puestas, el back ya **guarda y sirve la media desde el bucket** (#130).

---

## Cutover a Postgres + S3 (#130) — secuencia EXACTA, una sola vez

El back arranca con un **guardia de seguridad**: si `DATABASE_URL` apunta a un Postgres
**vacío** pero existe un `consola.db` SQLite **con datos** en el volumen, **REHÚSA arrancar**
(no sirve en blanco "perdiendo" los datos) y te apunta al comando de migración. Por eso el
cutover sigue este orden — **hazlo en una ventana de mantenimiento**:

```bash
cd /home/ubuntu/keni-social/deploy

# 0) Para el back (que nadie escriba durante el copiado). Postgres/Garage siguen vivos.
docker compose stop back

# 1) BACKUP de lo que existe HOY (recuperable si algo sale mal):
#    - el volumen del back (SQLite + media en disco): keni-social_keni-data
#    - el volumen de Postgres (por si ya tuviera algo): keni-social_pgdata
docker run --rm -v keni-social_keni-data:/d -v "$PWD":/b alpine \
  tar czf /b/backup-keni-data-$(date +%F).tgz -C /d .
docker run --rm -v keni-social_pgdata:/d -v "$PWD":/b alpine \
  tar czf /b/backup-pgdata-$(date +%F).tgz -C /d .

# 2) Bootstrap de Garage (si no se hizo ya) y S3_* puestas en .env (sección anterior).

# 3) DRY-RUN: cuenta lo que migraría, SIN escribir. Revisa los números.
docker compose run --rm \
  -e DATABASE_URL -e S3_ENDPOINT -e S3_REGION -e S3_BUCKET -e S3_ACCESS_KEY -e S3_SECRET_KEY \
  back python -m keni_consola.migracion --dry-run

# 4) MIGRACIÓN real (idempotente: SQLite -> Postgres y media de disco -> bucket S3).
docker compose run --rm \
  -e DATABASE_URL -e S3_ENDPOINT -e S3_REGION -e S3_BUCKET -e S3_ACCESS_KEY -e S3_SECRET_KEY \
  back python -m keni_consola.migracion

# 5) Arranca el back. Con Postgres ya CON datos, el guardia es transparente.
docker compose up -d back
docker compose logs -f back     # sin "Arranque INSEGURO"; entra por https://social.kenitech.io

# 6) VERIFICA: entra, comprueba usuarios/tareas/comercial y que las imágenes se ven.
#    docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt'  # tablas
#    docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT count(*) FROM usuarios;'
```

El comando es **idempotente**: si se interrumpe, vuelve a correrlo sin miedo (las filas se
insertan con conflicto→no-op y los objetos S3 ya presentes se saltan). `--solo-db` /
`--solo-media` migran una sola mitad. **No migra el YAML editorial** (fuera de alcance):
ese viaja con el volumen `keni-data`. Tras el cutover, mantén el backup hasta verificar.

## Exponer el MCP (opcional)

El `mcp` es interno y **sin auth propia**. Para que clientes Claude del equipo lo
usen por HTTP, añade a `mcp` un router Traefik con subdominio + middleware bearer:

```yaml
labels:
  - traefik.enable=true
  - traefik.docker.network=keni-social_edge
  - traefik.http.routers.mcp.rule=Host(`mcp.kenitech.io`)
  - traefik.http.routers.mcp.entrypoints=websecure
  - traefik.http.routers.mcp.tls.certresolver=le
  - traefik.http.services.mcp.loadbalancer.server.port=8000
  - traefik.http.routers.mcp.middlewares=mcp-auth
  - traefik.http.middlewares.mcp-auth.basicauth.users=USER:$$apr1$$...   # htpasswd
```
y mete `mcp` también en la red `edge`. TLS obligatorio (el bearer viaja en claro).

---

## Cómo encaja con los ADR

- **ADR 0001 (runtime):** este compose ES el "servicio compartido multiusuario".
  Fase 1 (auth) la sirve el back; la generación sigue en Fase 0 (`claude -p`).
- **ADR 0002 (descomposición):** `back`+`front` = gateway/catálogo; `mcp` = el 3er
  deployable; `db`/`files` = la infra compartida (Postgres + object storage). El
  **worker** de generación (Fase B) **ya existe** como servicio `worker`: el back
  **ENCOLA** (tabla `jobs` en Postgres) y el worker **ejecuta `claude -p`**. La generación
  corre **fuera del proceso del gateway**; reiniciar el back no mata los jobs en curso.

## Gaps a cerrar antes de producción real

- [x] **Auth multiusuario (#130) + `Origin`/CSRF tras Traefik validados (HECHO).** El back se
      protege con **login multiusuario (sesión) + CSRF**; el **token interino es OPCIONAL**
      (gate extra). El chequeo CSRF detrás del proxy honra el host público vía
      `KENI_CONSOLA_ORIGENES` (= `KENI_HOST`) además del `Host` de la petición (local intacto:
      127.0.0.1 sin allowlist sigue comparando contra el `Host`). Tests en
      `consola/tests/test_seguridad.py` (sección 7 CSRF tras proxy y 8 token opcional).
- [ ] `config.toml` real (System User token de Meta) para `KENI_METRICAS_FUENTE=real`.
- [x] Migrar `db.py` SQLite → Postgres y `media.py` disco → S3/Garage **(#130, HECHO)**. El
      back consume Postgres (`DATABASE_URL`) y S3 (`S3_*`) cuando están puestas; sin ellas,
      sigue en SQLite+disco (perfil local). Cutover one-shot con
      `python -m keni_consola.migracion` (ver "Cutover a Postgres + S3"). Pendiente solo el
      **YAML editorial** (`ficheros.py`/`indice.py`), fuera de alcance de #130.
- [x] Extraer el worker de generación (ADR 0002 Fase B) → Node fuera de `back` **(HECHO)**.
      El `back` ENCOLA (tabla `jobs` en Postgres); el servicio `worker` corre `claude -p`.
      Pendiente fino: aislamiento por usuario del sandbox en `code.kenitech.io` (infra más
      profunda; ver más abajo) y `--scale worker=N` si el piloto necesita más throughput.
- [x] **Hardening: `back` y `worker` corren como usuario no-root (HECHO).** Ver
      "Hardening / contenedor no-root" abajo (implicación de permisos del volumen).
- [ ] Backups de `pgdata` y `keni-data` (el cutover ya los respalda; falta automatizarlo).
- [ ] Decidir/ejecutar el ingress (migrar Caddy) en ventana de mantenimiento.

---

## Hardening / contenedor no-root (#130)

`back` y `worker` corren como un **usuario sin privilegios** (`keni`, uid `10001`), no como
root. Las imágenes crean ese usuario y le dan `/app` (código) y `/data` (estado: SQLite,
`secretos.toml` 0600, media). El `worker` instala `claude` **globalmente como root** (en el
build) y luego sólo lo **ejecuta** como `keni`; fuera de root, `claude` ya **no** restringe
`--dangerously-skip-permissions` (esa guarda es sólo para uid 0), así que `IS_SANDBOX` deja
de ser necesario (se deja inocuo por compatibilidad).

**Implicación de permisos del volumen `keni-data`:**

- **Volumen NUEVO (primer `up` tras esta imagen):** Docker inicializa el punto de montaje
  copiando el contenido y los **permisos del directorio `/data` de la imagen** (ya `chown`eado
  a `keni`), así que el usuario no-root puede escribir desde el arranque. **Nada que hacer.**
- **Volumen YA EXISTENTE (poblado antes, siendo root):** Docker **no** re-chownea un volumen
  con datos. Tras actualizar a esta imagen, el proceso no-root podría no poder escribir. Ajusta
  la propiedad **una vez** en el host (ventana de mantenimiento, con el stack parado):

  ```bash
  cd /home/ubuntu/keni-social/deploy
  docker compose stop back worker
  # uid:gid del usuario no-root de las imágenes (keni = 10001:10001)
  docker run --rm -v keni-social_keni-data:/d alpine chown -R 10001:10001 /d
  docker compose up -d back worker
  ```
