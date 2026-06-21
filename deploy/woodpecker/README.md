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

- `woodpecker-server`: `cpus: 1.0`, `mem_limit: 512m`, `cpuset: 3-11` (UI/API, liviano).
- `docker-socket-proxy`: `cpus: 0.5`, `mem_limit: 64m`, `cpuset: 3-11`.
- `woodpecker-agent`: `cpus: 4.0`, `mem_limit: 4g`, `cpuset: 3-11` — pero eso solo acota
  al **agente**, no a los contenedores de cada *step* (los arranca el daemon Docker como
  hermanos, fuera del cgroup del agente). Para acotar el cómputo REAL de los steps se fijan
  límites por step vía backend Docker: `WOODPECKER_BACKEND_DOCKER_LIMIT_CPU_QUOTA=200000`
  (2 vCPU/step), `WOODPECKER_BACKEND_DOCKER_LIMIT_MEM=4294967296` (4 GiB/step) y
  `WOODPECKER_BACKEND_DOCKER_LIMIT_CPU_SET=3-11`. Con 3 workflows en paralelo el CI no pasa
  de ~6 vCPU sobre los cores 3-11, dejando los cores **0-2 intactos para el `back`+`db`
  user-facing** y ≥6 vCPU compartidos con el prod pesado.

### Decisión: cgroups/cpuset, NO una VM (medido en el server, 2026-06)

El dueño pidió evaluar montar una **VM dedicada** (KVM) para Woodpecker si eso resolvía
la contención CI↔prod. Se midió el server **con 3 workflows de CI corriendo a tope** y la
conclusión con datos es que **el aislamiento por cgroup/cpuset YA resuelve el problema; una
VM no aportaría headroom, solo repartiría el mismo cómputo con overhead añadido**:

| Métrica (server Latitude, AMD EPYC 4244P 6c/12t, 61 GiB) | Valor medido (CI activo) |
| --- | --- |
| Idle cores **0-2** (back+db user-facing) | **94–97 %** — el `back` ni se entera del CI |
| Idle cores **3-11** (CI + prod pesado) | 50–72 % (≈30 % ocupados de media) |
| Idle global | ~70 % |
| Memory PSI (`/proc/pressure/memory`) | `full avg10=0.00`, `some avg10=0.00` — **cero presión** |
| RAM disponible | 52 GiB de 61 GiB; swap 4 MiB de 4 GiB |
| OOM-kills (dmesg + journal 7 días) | **0**; ningún contenedor con `OOMKilled=true` |
| Límites de step reales (`docker inspect`) | `CpuQuota=200000` (2 vCPU), `CpusetCpus=3-11`, `Memory=4 GiB` — aplicados ✔ |

**Por qué cgroups y no VM:**

- **El cuello NO es falta de compute total ni de memoria** (70 % idle global, 52 GiB RAM
  libre, PSI de memoria en cero). Una VM **no añade núcleos ni RAM**: solo trocea los 12
  vCPU / 61 GiB ya existentes, reservándolos en duro (un vCPU dado a la VM deja de estar
  disponible para prod aunque el CI esté ocioso) y pagando overhead de doble kernel +
  daemon Docker anidado. Como **no hay un OOM real que aislar** (0 kills en 7 días), el
  beneficio de aislar el dominio OOM en su propio kernel —el único punto donde una VM gana
  de verdad a cgroups— **no aplica hoy**.
- **El único riesgo era CPU del back**, y ya está neutralizado por `cpuset`: el `back` y
  `db` viven en los cores **0-2** y el CI entero (agente + steps) en **3-11**. Con CI a
  tope los cores 0-2 quedaron **94–97 % idle**: la partición de núcleos hace lo mismo que
  haría una VM para el caso que importa (que un build no degrade la UI), sin reservar RAM
  ni doblar kernel.
- Los fallos que motivaron las notas del código (`-n auto`=12 saturaba RAM y abortaba un
  worker; `start_period` subido a 120 s para no rollbackear bajo carga) eran de **ANTES**
  de existir estos topes. Con los límites actuales **no se reproducen** (0 OOM, PSI memoria
  en cero). El problema descrito ya está resuelto por cgroups; añadir una VM sería resolver
  dos veces el mismo problema, peor.

**Endurecimiento aplicado en este cambio** (cerrar el último hueco): el `woodpecker-agent`,
`woodpecker-server` y `docker-socket-proxy` **no tenían `cpuset`** y podían planificarse en
los cores 0-2. Aunque son livianos (16/48 MiB RAM, CPU≈0) se fijan a `3-11` para que el
invariante «los cores 0-2 son sagrados para el user-facing» sea total. Cambio de **fichero
solo**: se aplica recreando los servicios de CI en una ventana sin pipelines en curso
(`cd deploy/woodpecker && docker compose up -d`).

> **Reconsiderar una caja aparte solo si cambia la realidad medida**, p. ej. si el equipo
> sube `WOODPECKER_MAX_WORKFLOWS`, si el prod pesado (worker `claude -p`, transcriptor)
> empieza a llenar de verdad los cores 3-11 a la vez que el CI, o si aparecen OOM-kills /
> PSI de memoria sostenida. En ese escenario **la respuesta correcta es otra máquina física
> (más compute real), no una VM en la misma caja** (que no añade compute). Como contingencia
> intermedia en el MISMO host está documentada abajo una VM KVM; el server tiene `/dev/kvm`
> y AMD-V, así que es viable, pero **hoy no se recomienda** por lo anterior.

<details>
<summary>Contingencia (NO ejecutar hoy): VM KVM dedicada para el agente en el mismo host</summary>

Solo si la realidad medida cambia (ver arriba). Aísla el dominio OOM y el kernel del CI del
de prod, a costa de **reservar en duro** vCPU+RAM (dejan de estar disponibles para prod aunque
el CI esté ocioso) y del overhead de virtualización. El server soporta KVM (`/dev/kvm`
presente, flag `svm`/AMD-V, módulos `kvm_amd` cargados), pero **no hay tooling de virt
instalado** (`qemu`/`libvirt` ausentes): habría que instalarlo.

Plan de provisioning (lo ejecuta el humano en el server, NO un agente):

1. **Instalar virt** (Ubuntu): `sudo apt-get install -y qemu-kvm libvirt-daemon-system virtinst cloud-image-utils`; añadir `ubuntu` a los grupos `libvirt`,`kvm`.
2. **Dimensionar la VM con reserva DURA** sobre la partición 3-11 (NUNCA 0-2): p. ej. `--vcpus 4 --memory 8192`, ancladas a los cores 3-11 con `virsh vcpupin` / `<cputune>` para no pisar el back. Disco qcow2 ~40 GiB en `/var/lib/libvirt/images` (hay 683 GiB libres en `/`).
3. **Cloud-init** una Ubuntu LTS minimal: instalar Docker, unir la VM a la tailnet, y arrancar SOLO el `woodpecker-agent` (mismo `WOODPECKER_AGENT_SECRET`) apuntando al `woodpecker-server` que sigue en el host (`woodpecker-server:9000` vía la red/tailnet). El `server`, el `docker-socket-proxy` y el ingress Traefik se quedan en el host.
4. **Deploy de la app:** el pipeline `.woodpecker/deploy.yml` monta el `docker.sock` del **host** para recrear el stack. Si el agente pasa a la VM, ese step ya no ve el socket del host: hay que **dejar el agente de deploy en el host** (agente etiquetado) y mandar a la VM solo los agentes de test, o exponer el socket del host a la VM (peor superficie). Documentar la separación de agentes por label antes de migrar.
5. **Bajar los topes del agente del host** una vez la VM asuma los tests, o pararlo.

Trade-off neto: la VM **reserva** 4 vCPU + 8 GiB que hoy prod puede usar cuando el CI está
ocioso (los cgroups actuales son topes elásticos, no reservas). Por eso solo compensa cuando
el aislamiento del dominio OOM/kernel sea un beneficio real, no hoy.

</details>

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
