# Woodpecker CI — keni-social (server Latitude)

CI self-hosted para el repo privado `kenitech-io/keni-social`. Stack **separado**
en el server Latitude (162.43.191.103) que reusa el Traefik de keni-social como
ingress + TLS. Sustituye al CI de GitHub Actions (bloqueado por facturacion, ver
issue #136). Pipelines en `.woodpecker/` (espejo de `.github/workflows/ci.yml`).

> Convenciones tomadas del rol Ansible de DevOps (`kenidevops/devops-infra/
> ansible/roles/woodpecker`). No se usa Ansible aqui porque los servers DevOps
> estan deprovisionados; este compose vive con la app.

## Topologia

- `woodpecker-server` — UI + API. En las redes `keni-ci_woodpecker` (interna) y
  `keni-social_edge` (para que el Traefik host-mode lo enrute). Sin puertos
  publicados; Traefik le da `https://ci-social.kenitech.io` con el resolver `le`.
- `woodpecker-agent` — ejecuta los pipelines (monta `/var/run/docker.sock`).
- Forge: GitHub OAuth (org `kenitech-io`).

## Prerrequisitos (una vez)

1. **DNS:** registro `A` `ci-social.kenitech.io -> 162.43.191.103` en modo
   **DNS-only (nube gris)**, gestionado por Terraform en
   `kenidevops/devops-iac/cloudflare/dns` (forma GitOps de DevOps). Imprescindible
   el modo DNS-only: Traefik valida el cert por HTTP-01; con proxy naranja falla.
2. **GitHub OAuth App** en `https://github.com/organizations/kenitech-io/settings/applications/new`
   - Homepage URL: `https://ci-social.kenitech.io`
   - Authorization callback URL: `https://ci-social.kenitech.io/authorize`
   - Copia el **Client ID** y genera un **Client Secret**.

## Despliegue

```sh
cd /home/ubuntu/keni-social/deploy/woodpecker
cp .env.example .env
# Rellena .env:
#   WOODPECKER_ADMIN        = tu login de GitHub (admin)
#   WOODPECKER_GITHUB_CLIENT/_SECRET = de la OAuth App
#   WOODPECKER_AGENT_SECRET = openssl rand -hex 32

# El volumen de datos lo escribe el server como uid 1000 (imagen v3):
docker volume create woodpecker_data
docker run --rm -v woodpecker_data:/data alpine chown -R 1000:1000 /data

docker compose up -d
docker compose logs -f woodpecker-server   # comprueba arranque + cert
```

Entra en `https://ci-social.kenitech.io`, autoriza con GitHub y activa el repo
`kenitech-io/keni-social` (Repositories -> Add). A partir de ahi cada push/PR
dispara los 3 pipelines de `.woodpecker/`.

## Operacion

```sh
docker compose ps
docker compose logs -f woodpecker-agent
docker compose pull && docker compose up -d   # actualizar (sube WOODPECKER_VERSION)
docker compose down                            # parar (no borra volumenes)
```

Secretos de pipeline (registry, tokens) se anaden en la UI de Woodpecker por repo
(Settings -> Secrets), nunca en git.

## Despliegue de la app (`.woodpecker/deploy.yml`)

Ademas de los 3 pipelines de CI (tests), hay un pipeline de **despliegue**:
`.woodpecker/deploy.yml`. Como el agente corre en el **mismo host** que el stack y ya
monta el `docker.sock`, el step construye las imagenes desde el checkout del pipeline
(sin rsync) y recrea el stack via `deploy/deploy.sh`.

- **Disparo MANUAL** (`when: event: manual`): se lanza desde la UI (boton *Run
  pipeline*/manual) sobre `main`. A proposito NO se despliega en cada push (piloto en
  vivo).
- **Hace:** `docker compose build` -> `stop back` -> chown del volumen a uid 10001 (los
  contenedores corren no-root) -> `migracion --solo-db` (cutover SQLite->Postgres,
  idempotente y no destructivo) -> `up -d`. Detalle en `deploy/deploy.sh`.

### Requisitos (una vez) para que el deploy funcione

1. **Marca el repo como TRUSTED** en Woodpecker (Repo Settings -> *Trusted*). Sin eso,
   Woodpecker **bloquea** el montaje del `docker.sock` y del `.env` que el step necesita.
   (Alternativa si no quieres confiar el repo: fija en el agente
   `WOODPECKER_BACKEND_DOCKER_VOLUMES=/var/run/docker.sock:/var/run/docker.sock,/home/ubuntu/keni-social/deploy/.env:/secrets/env:ro`
   — pero eso expone el socket a TODOS los steps, incluidos los de test.)
2. **`.env` de secretos** en `/home/ubuntu/keni-social/deploy/.env` (el del stack
   principal; ya existe). Hasta bootstrapear Garage, deja las `S3_*` **vacias** ahi: la
   media se queda en disco (volumen `keni-data`) y Postgres/worker/auth ya funcionan.
3. **Garage (S3) — bootstrap de una vez** (cuando quieras media en object storage):
   ver `deploy/README.md` ("Bootstrap de Garage" + "Cutover a Postgres + S3"). Tras
   crear bucket+clave y poner las `S3_*` reales en `.env`, corre
   `migracion --solo-media` (o el deploy completo) para subir la media existente.

> El primer deploy migra `consola.db` (SQLite) a Postgres. Es idempotente: si algo
> falla, el SQLite sigue intacto y puedes reintentar. La guarda de arranque del back
> impide arrancar contra un Postgres vacio teniendo datos en SQLite.
