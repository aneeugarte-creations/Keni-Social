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

- **Postgres (`db`) y Garage (`files`) ya los CONSUME el back (#130).** Tras la **ADR 0004**
  Postgres es el **backend único** de la operacional (ya no hay SQLite):
  - **`DATABASE_URL` es OBLIGATORIA** en local y en hosted (este stack la cablea). En
    desarrollo no se ofrece Postgres local: la ejecución/validación se hace en el server
    (CI Woodpecker / hosted); si necesitas correr la app en local, provee tu propio
    `DATABASE_URL` apuntando a un Postgres que tú gestiones. La DB operacional (tareas,
    comercial, rota, usuarios/sesiones, cola de jobs) vive en **Postgres**. Sin
    `DATABASE_URL` el back falla al arrancar con un mensaje accionable.
  - **Con `S3_*`** (endpoint + credenciales) → la media va al **bucket Garage/S3**. Sin S3
    → disco (`/data/keni-social/media`), como siempre.
  El antiguo cutover SQLite → Postgres ya es historia (ADR 0004); el comando
  `python -m keni_consola.migracion --solo-db` se mantiene como NO-OP idempotente que
  garantiza el esquema, por compatibilidad con `deploy.sh`. Ver "Cutover de media a S3" abajo.
  **FUERA de alcance:** el contenido editorial YAML (`ficheros.py`,
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

## Versionado de imágenes + limpieza (janitor)

`deploy.sh` taggea las imágenes propias (`front`/`back`/`worker`/`mcp`) con un tag
**versionado** (`KENI_VERSION`, timestamp por defecto; o `KENI_VERSION=1.4.0 sh deploy.sh .env`)
y también las marca `:latest`. El compose interpola `${KENI_VERSION:-latest}`, así que un
`docker compose build` "pelado" sin la var sigue dando `:latest` (compatible).

Un **janitor** (`deploy/janitor/`, systemd timer **diario**) evita que las imágenes se
acumulen: conserva las **5** más recientes por repo `keni-social/*` (nunca borra una en
uso), y **solo si `/` supera el 50% usado** purga dangling + build cache (y baja la
retención a 1). Config en `/etc/keni-janitor.conf` (`KEEP=`, `THRESHOLD=`). Instalar/operar:

```bash
sudo install -m755 deploy/janitor/keni-janitor.sh /usr/local/bin/keni-janitor
sudo cp deploy/janitor/keni-janitor.{service,timer} /etc/systemd/system/
printf 'KEEP=5\nTHRESHOLD=50\n' | sudo tee /etc/keni-janitor.conf
sudo systemctl daemon-reload && sudo systemctl enable --now keni-janitor.timer
systemctl list-timers keni-janitor.timer    # próxima ejecución
sudo systemctl start keni-janitor.service    # correr ya una vez
tail -n 30 /var/log/keni-janitor.log
```

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

## Cutover de media a S3 (#130, vigente) — secuencia, una sola vez

> **Histórico:** el cutover de datos SQLite → Postgres se hizo y ya no aplica. La ADR 0004
> retiró SQLite operacional; ahora la operacional vive **siempre** en Postgres y el comando
> `python -m keni_consola.migracion --solo-db` quedó como NO-OP idempotente que garantiza el
> esquema (lo invoca `deploy.sh` como paso 4/5). El cutover que aún tiene sentido es la
> media (disco → bucket Garage/S3), si el back todavía guarda media en disco.

```bash
cd /home/ubuntu/keni-social/deploy

# 0) Para el back (que nadie escriba durante el copiado). Postgres/Garage siguen vivos.
docker compose stop back

# 1) BACKUP del volumen del back (media en disco): keni-social_keni-data.
docker run --rm -v keni-social_keni-data:/d -v "$PWD":/b alpine \
  tar czf /b/backup-keni-data-$(date +%F).tgz -C /d .

# 2) Bootstrap de Garage (si no se hizo ya) y S3_* puestas en .env (sección anterior).

# 3) DRY-RUN: cuenta lo que migraría, SIN escribir. Revisa los números.
docker compose run --rm \
  -e DATABASE_URL -e S3_ENDPOINT -e S3_REGION -e S3_BUCKET -e S3_ACCESS_KEY -e S3_SECRET_KEY \
  back python -m keni_consola.migracion --solo-media --dry-run

# 4) MIGRACIÓN real (idempotente: media de disco → bucket S3).
docker compose run --rm \
  -e DATABASE_URL -e S3_ENDPOINT -e S3_REGION -e S3_BUCKET -e S3_ACCESS_KEY -e S3_SECRET_KEY \
  back python -m keni_consola.migracion --solo-media

# 5) Arranca el back.
docker compose up -d back
docker compose logs -f back     # entra por https://social.kenitech.io

# 6) VERIFICA: que las imágenes se ven (servidas desde S3).
```

El comando es **idempotente**: si se interrumpe, vuelve a correrlo sin miedo (los objetos S3
ya presentes se saltan). **No migra el YAML editorial** (fuera de alcance): ese viaja con
el volumen `keni-data`. Tras el cutover, mantén el backup hasta verificar.

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

## Agencias de noticias: Reuters Connect / AFP (item F)

Las agencias son **fuentes opcionales** del Radar/pestaña Fuentes que traen notas
normalizadas (titulo/resumen/enlace/fecha/fuente) como un feed más. Están **gateadas por
credencial**: sin clave, la fuente aparece como "pendiente / no configurada" y **NO rompe**
nada (degradación honesta; el Radar y Fuentes lo dicen en claro, sin inventar contenido).

Para activarlas, pon las credenciales en `.env` y `docker compose up -d`:

```sh
# Reuters Connect — una API key (Bearer):
KENI_REUTERS_API_KEY=<tu-api-key>
# opcional, para apuntar a un endpoint/versión concreto:
# KENI_REUTERS_BASE_URL=https://api.reutersconnect.com

# AFP — OAuth2 client_credentials (client_id + client_secret):
KENI_AFP_CLIENT_ID=<tu-client-id>
KENI_AFP_CLIENT_SECRET=<tu-client-secret>
# KENI_AFP_BASE_URL=https://afp-apicore-prod.afp.com
```

Sin esas variables, la fuente queda "pendiente": no se descarga nada y el resto del pipeline
(Google Trends + feeds RSS del equipo) sigue funcionando igual. El estado de cada agencia se
ve en **Fuentes → Todas las fuentes → Agencias de noticias** y en el panel del **Radar**.

> Nota: los normalizadores de respuesta (Reuters GraphQL / AFP REST) están implementados y
> testeados; el cableado FINAL de autenticación/endpoint por agencia se completa cuando se
> conecte una cuenta real (las URLs base son configurables por las `*_BASE_URL`).

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
- [x] Migrar `db.py` SQLite → Postgres y `media.py` disco → S3/Garage **(#130, HECHO)**.
      Tras la **ADR 0004** la operacional es Postgres ÚNICO (`DATABASE_URL` obligatoria,
      local y hosted); el SQLite operacional se retiró. La media va a S3 si las `S3_*`
      están puestas; sin ellas sigue en disco. Pendiente solo el **YAML editorial**
      (`ficheros.py`/`indice.py`), fuera de alcance.
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
root. Las imágenes crean ese usuario y le dan `/app` (código) y `/data` (estado:
`secretos.toml` 0600, media en disco si no se cablea S3). El `worker` instala `claude` **globalmente como root** (en el
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
