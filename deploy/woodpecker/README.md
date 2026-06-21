# Woodpecker CI — keni-social (server Latitude)

CI self-hosted para el repo privado `kenitech-io/keni-social`. Stack **separado**
en el server Latitude (<IP-DEL-SERVIDOR>) que reusa el Traefik de keni-social como
ingress + TLS. Sustituye al CI de GitHub Actions (bloqueado por facturacion).
Pipelines en `.woodpecker/` (espejo de `.github/workflows/ci.yml`).

> Convenciones tomadas del rol Ansible de DevOps (`kenidevops/devops-infra/
> ansible/roles/woodpecker`). No se usa Ansible aqui porque los servers DevOps
> estan deprovisionados; este compose vive con la app.

## Topologia

- `woodpecker-server` — UI + API. En las redes `keni-ci_woodpecker` (interna) y
  `keni-social_edge` (para que el Traefik host-mode lo enrute). Sin puertos
  publicados; Traefik le da `https://ci-social.kenitech.io` con el resolver `le`.
- `woodpecker-agent` — ejecuta los pipelines (monta `/var/run/docker.sock`).
- Forge: GitHub OAuth (org `kenitech-io`).

## Aislamiento de recursos — el CI comparte host con PRODUCCION ⚠

Este runner corre en el **mismo VPS** (Latitude, 12 vCPU / 61 GiB) que el stack de
producción (back interactivo, worker `claude -p`, Postgres, Garage). Sin topes, un
build pesado (imágenes Docker + `tsc`/`vite` + `pytest`, hasta
`WOODPECKER_MAX_WORKFLOWS=3` en paralelo) puede **saturar la CPU y degradar la UI de
prod**. Mitigaciones ya aplicadas en `docker-compose.yml` (topes DUROS):

- `woodpecker-server`: `cpus: 1.0`, `mem_limit: 512m` (UI/API, liviano).
- `docker-socket-proxy`: `cpus: 0.5`, `mem_limit: 64m`.
- `woodpecker-agent`: `cpus: 4.0`, `mem_limit: 4g` — pero eso solo acota al **agente**,
  no a los contenedores de cada *step* (los arranca el daemon Docker como hermanos,
  fuera del cgroup del agente). Para acotar el cómputo REAL de los steps se fijan
  límites por step vía backend Docker: `WOODPECKER_BACKEND_DOCKER_LIMIT_CPU_QUOTA=200000`
  (2 vCPU/step) y `WOODPECKER_BACKEND_DOCKER_LIMIT_MEM=4294967296` (4 GiB/step). Con 3
  workflows en paralelo el CI no pasa de ~6 vCPU, dejando ≥6 vCPU para prod.

> **Recomendación: mover el runner a un host aparte.** Compartir host es una solución
> de circunstancia (los servers DevOps están deprovisionados; reusamos el Traefik de la
> app). Aunque los topes de arriba evitan el peor caso, el aislamiento por cgroups **no
> es perfecto** (I/O de disco hacia el mismo SSD que Postgres/Garage, page-cache,
> presión de memoria, contención del propio daemon Docker) y un build aún puede tocar la
> latencia de prod. Lo correcto es **un VPS dedicado para el `woodpecker-agent`** (o al
> menos para los steps), apuntando al mismo `woodpecker-server`. Mientras siga aquí:
> mantén estos límites, NO subas `WOODPECKER_MAX_WORKFLOWS`, y prefiere ejecutar los
> deploys/builds pesados fuera de las horas punta del equipo.

## Prerrequisitos (una vez)

1. **DNS:** registro `A` `ci-social.kenitech.io -> <IP-DEL-SERVIDOR>` en modo
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
dispara los pipelines de `.woodpecker/`: 7 de CI/tests (`tests-python`,
`tests-shell`, `tests-app-metricas`, `tests-app-operacion`, `tests-app-produccion`,
`frontend-build`, `fronteras`) y el de despliegue (`deploy`).

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

Ademas de los 7 pipelines de CI (tests), hay un pipeline de **despliegue**:
`.woodpecker/deploy.yml`. Como el agente corre en el **mismo host** que el stack y ya
monta el `docker.sock`, el step construye las imagenes desde el checkout del pipeline
(sin rsync) y recrea el stack via `deploy/deploy.sh`.

- **Auto-deploy en push a `main`** (`when: event: push, branch: main`), DESPUES de los
  pipelines de test (via `depends_on`); tambien disparable como *manual*. Un push con
  tests en rojo NO despliega; NO despliega en PRs ni otras ramas.
- **Hace:** `docker compose build` -> `stop back` -> chown del volumen a uid 10001 (los
  contenedores corren no-root) -> `migracion --solo-db` (aserto de esquema idempotente
  sobre Postgres; no-op tras ADR 0004, no destructivo) -> `up -d`. Detalle en
  `deploy/deploy.sh`.

### Requisitos (una vez) para que el deploy funcione

1. **Activa "Volumenes" en la seccion "Confiado"** del repo (Repo Settings -> General ->
   *Confiado* -> *Volumenes*: "Pipeline containers are allowed to mount volumes"). En
   Woodpecker v3.13 el antiguo flag "Trusted" es **granular**; con "Volumenes" basta para
   que el step monte el `docker.sock` + el `.env` (deja "Network" y "Seguridad" en off).
   Para disparar por la pestana *Deployments*, activa ademas **"Permitir despliegues"**.
   (Alternativa global, menos segura: fija `WOODPECKER_BACKEND_DOCKER_VOLUMES` en el agente
   — pero eso expone el socket a TODOS los steps, incluidos los de test.)
2. **`.env` de secretos** en `/home/ubuntu/keni-social/deploy/.env` (el del stack
   principal; ya existe). Hasta bootstrapear Garage, deja las `S3_*` **vacias** ahi: la
   media se queda en disco (volumen `keni-data`) y Postgres/worker/auth ya funcionan.
3. **Garage (S3) — bootstrap de una vez** (cuando quieras media en object storage):
   ver `deploy/README.md` ("Bootstrap de Garage" + "Cutover a Postgres + S3"). Tras
   crear bucket+clave y poner las `S3_*` reales en `.env`, corre
   `migracion --solo-media` (o el deploy completo) para subir la media existente.

> La operacional vive en Postgres (ADR 0004); SQLite ya no existe. `migracion --solo-db`
> es un aserto de esquema idempotente (no-op cuando el esquema ya esta al dia), no un
> cutover de datos.
