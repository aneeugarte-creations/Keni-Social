# deploy/ — keni-social dockerizado (stack hosted/equipo)

`docker compose` que levanta keni-social como **servicio compartido** (ADR
[0001](../docs/adr/0001-runtime-servicio-compartido.md) /
[0002](../docs/adr/0002-descomposicion-monolito-modular-catalogo-apps.md), Fase C):

| Servicio | Imagen | Rol | Expuesto |
|---|---|---|---|
| `traefik` | `traefik:v3` | Reverse proxy + TLS (Let's Encrypt), `network_mode: host` | **:80/:443** |
| `front` | build `front/` | SPA React (nginx) | vía Traefik (todo menos `/api`) |
| `back` | build `back/` | Gateway Starlette + generación | vía Traefik (`/api`) |
| `mcp` | build `mcp/` | `keni-metricas` por HTTP | interno (ver abajo) |
| `db` | `postgres:16` | Estado compartido | interno |
| `files` | `dxflrs/garage` | Object storage S3 (media) | interno |

> El contexto de build de las imágenes propias es la **raíz del repo** (`..`),
> porque necesitan `keni-shared/ + mcp-metricas/ + consola/ + skills-copy/`.

---

## ⚠️ Lee esto antes de nada: estado honesto

Esto **dockeriza la arquitectura objetivo**, pero el código aún no la consume entera:

- **Postgres (`db`) y Garage (`files`) están provisionados por adelantado.** Hoy el
  back persiste en **SQLite** (`/data/keni-social/consola.db`) y guarda media en
  **disco** (`/data/keni-social/media`), ambos en el volumen `keni-data`. Las vars
  `DATABASE_URL` y `S3_*` quedan cableadas para cuando `db.py`/`media.py` migren
  (parte del trabajo multiusuario en curso, rama `feat/auth-backend`). Mientras
  tanto los contenedores `db`/`files` corren pero el back **no** los usa.
- **La imagen `back` es interina.** Incluye Node + la CLI `claude` porque la
  generación corre con `claude -p` en proceso (ADR 0001, Fase 0). ADR 0002 Fase B
  extrae un **worker** que llamará a la API de Claude y dejará la imagen sin Node.
- **whisper (clip→copy) NO está en hosted.** Por privacidad (el audio no sale de la
  máquina), la transcripción es del perfil local. El gateway hosted no transcribe.
- **Expuesto públicamente tras auth.** `/api` va protegido por el token interino
  (`KENI_CONSOLA_TOKEN`) + CSRF por `Origin`, más el login multiusuario user/pass
  (#130). El admin inicial se crea desde `KENI_CONSOLA_ADMIN_USER/PASS` (o pass
  aleatoria logueada). El bind `0.0.0.0` del back solo lo alcanza Traefik.
- **Claude (generación) usa el OAuth token de la máquina**, no una API key: el back
  recibe `CLAUDE_CODE_OAUTH_TOKEN` desde `/etc/learn-platform/claude-oauth-token`.

---

## Ingress (estado actual: Traefik único, Caddy retirado)

**HECHO.** En `learn-01` (162.43.191.103) Traefik es el **ingress único**
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

## Requisitos en el host

```bash
# El plugin compose v2 NO está instalado en learn-01; Docker sí.
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
(No urge: el back aún no usa S3; ver "estado honesto".)

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
  **worker** de generación (Fase B) aún no existe: se añadirá como servicio
  `worker` cuando se extraiga, y el back pasará a **encolar** en vez de ejecutar.

## Gaps a cerrar antes de producción real

- [ ] Terminar auth multiusuario (#130) y validar `Origin`/CSRF tras Traefik.
- [ ] `config.toml` real (System User token de Meta) para `KENI_METRICAS_FUENTE=real`.
- [ ] Migrar `db.py` SQLite → Postgres y `media.py` disco → S3/Garage.
- [ ] Extraer el worker de generación (ADR 0002 Fase B) → quitar Node de `back`.
- [ ] Backups de `pgdata` y `keni-data`. Hardening del contenedor `back` (no-root).
- [ ] Decidir/ejecutar el ingress (migrar Caddy) en ventana de mantenimiento.
