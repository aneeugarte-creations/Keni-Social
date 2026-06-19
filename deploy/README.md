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
> porque necesitan `keni-shared/ + mcp-metricas/ + consola/`.

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
  propio, kill del árbol al timeout/cancel, tope de concurrencia, sin procesos sueltos). Por eso
  **`worker` lleva Node + la CLI `claude` y `back` ya no** (`KENI_WORKER_EXTERNO=1` en el
  back evita que levante su worker in-proceso). La generación **sigue siendo `claude -p`**
  (ADR 0001): el worker **no** usa la API de Claude. *Reiniciar el back NO mata los jobs en
  curso del worker* (es otro contenedor). En **local / un solo proceso** no hace falta el
  servicio: el back arranca el worker **en proceso** (un hilo), y la UX no cambia.
- **whisper NO está en hosted.** Por privacidad (el audio no sale de la máquina), TODA la
  transcripción (clip→copy, subtítulos de vídeo y el gestor de audio) corre con whisper.cpp
  (`whisper-cli` + modelo `v3 turbo`) en el **perfil local**. El worker hosted no lleva
  `whisper-cli` ni el modelo: el motor `keni_consola.transcripcion` degrada con un error claro en
  español si faltan. El gateway hosted no transcribe.
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
- **La cuenta de Claude (generación) se fija con `claude auth login` desde el panel**
  (Sistema → Cuenta de Claude); las credenciales viven en `CLAUDE_CONFIG_DIR`
  (`/data/claude-cfg`, volumen compartido). Ver §Cuenta.

---

## Cuenta de Claude (cambiar desde el panel) — ADR 0013

El panel **Sistema** (admin) trae una sección **Cuenta de Claude del servidor**: ve el estado
de auth y el medidor de uso (`/usage`), y permite **cambiar de cuenta** (login: URL → pegar
código) y cerrar sesión, **sin SSH**. Lo sirve el `daemons` (tiene `claude`; instancia única)
por un listener de control interno; el `back` lo proxea (admin-gated). Está **ACTIVO por
defecto**: el bearer interno back↔daemons se auto-persiste en `/data`, sin configurar nada.

Las credenciales viven en el volumen compartido `/data/claude-cfg`
(`CLAUDE_CONFIG_DIR`), así que un login aplica **en caliente** a `worker`+`daemons` sin
reiniciar. NO hay token por entorno: la cuenta se fija únicamente por login.

**Fijar la cuenta (única acción):** en el panel (Sistema → Cuenta de Claude) → **Cambiar
cuenta**: abre la URL, inicia sesión y pega el código. Las credenciales se escriben en
`/data/claude-cfg`; la generación y el medidor `/usage` quedan operativos al instante.

> `claude auth logout` desde el panel deja al servidor SIN cuenta hasta el siguiente login (la
> generación para): úsalo solo para cambiar de cuenta.

---

## Ingress (estado actual: Traefik único, Caddy retirado)

**HECHO.** En el servidor Latitude (`social.kenitech.io`) Traefik es el **ingress único**
(`network_mode: host`, dueño de `:80/:443`, ACME Let's Encrypt). El Caddy de sistema
fue **retirado** (paquete purgado). Traefik sirve:

- `social.kenitech.io` → front / back (este stack). **LIVE.**

Los sitios legacy `code.kenitech.io` (code-launcher) y `api.kenitech.io`
(learn-control-plane / firecracker) fueron **desmantelados por completo**
(2026-06-12): servicios systemd, binarios, configs, usuarios `code-*`/`learn`,
container `learn-postgres` y la partición `/var/lib/firecracker` eliminados del
servidor; el router `traefik/dynamic/legacy-sites.yml` se borró del repo.
Backup previo en `/home/ubuntu/backups/legacy-code-learn-20260612.tar.gz`.

---

## Conexión al servidor

```bash
ssh -i <clave-ssh> <usuario>@<servidor>
```
- El acceso (IP del servidor, usuario sudo NOPASSWD y nombre de la llave SSH) lo conoce el
  equipo; **no se publica aquí** la receta completa para no exponer la combinación exacta. El
  privado de la llave **no** está en el repo.
- El stack vive en `/home/ubuntu/keni-social/deploy`. Operar desde ahí:
  `docker compose ps` · `docker compose logs -f back` · `docker compose up -d`.

## Requisitos en el host

```bash
# El plugin compose v2 NO está instalado en el servidor Latitude; Docker sí.
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
docker compose version            # comprobar
```

`ubuntu` ya está en el grupo `docker` (no hace falta sudo para docker).

## DNS

Hace falta `social.kenitech.io → <IP-DEL-SERVIDOR>` (A, **sin proxy** de Cloudflare —
Let's Encrypt necesita acceso directo para el challenge HTTP). El DNS de la zona lo
gestiona Terraform en `keni/devops-iac/cloudflare/dns/`. Añade el registro al mapa
`custom_records` de `terraform.tfvars` (donde ya están `code` y `api`):

```hcl
custom_records = {
  "code"   = "<IP-DEL-SERVIDOR>"
  "api"    = "<IP-DEL-SERVIDOR>"
  "social" = "<IP-DEL-SERVIDOR>"   # <-- añadir
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

## Versionado de imágenes + deploy quirúrgico + limpieza (janitor)

`deploy.sh` taggea cada imagen propia (`front`/`back`/`worker`/`mcp`) con un **hash de SUS
entradas de build** (`FRONT_VERSION`/`BACK_VERSION`/`WORKER_VERSION`/`MCP_VERSION`) y también
`:latest`. Así el deploy es **quirúrgico**: solo (re)construye y **recrea** el servicio cuyo
contenido cambió. Un deploy de **solo front** (o solo mcp) **no toca el `worker`**, de modo
que sus `claude -p` en proceso no se interrumpen. `back` y `worker` comparten `consola/`, así que
un cambio de código ahí recrea **ambos** (el worker DEBE correr ese código). El compose
interpola `${FRONT_VERSION:-latest}` etc., así que un `docker compose build` "pelado" sin las
vars sigue dando `:latest` (compatible). El hash se calcula del árbol de ficheros (no de git:
`deploy.sh` corre en el dir estable del host, cuyo `.git` puede no estar sincronizado).

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

## Encender el pipeline automático para VALIDACIÓN (Flujo C, Fase 2)

La "máquina de contenido" lleva cada tema de entrada a **borrador completo en la cola de
revisión** a través del **pipeline** (un único espinazo): `news-pool → etapa de Redactar → etapa de
Ilustrar → cola de revisión`. El modelo es **1 master + 3 etapas**, todo colgando del pipeline.
Vienen **OFF por defecto** (conservador). Para validar la cadena end-to-end en el hosted del
piloto, la decisión de dirección es **encender el master + las 3 etapas y dejar el de publicar
OFF**:

| Flag | Qué hace | Validación |
|---|---|---|
| `KENI_MAQUINA` | Interruptor general (kill-switch); sin él nada automático corre | **ON** |
| `KENI_PIPELINE_RECOLECTAR` | «Crear noticias»: Recolectar + Agrupar + Traducir/tropicalización MX | **ON** |
| `KENI_PIPELINE_REDACTAR` | «Generar copy»: etapa de Redactar (único motor de copy) | **ON** |
| `KENI_PIPELINE_ILUSTRAR` | «Generar arte»: etapa de Ilustrar (temas con copy sin imagen) | **ON** |
| `KENI_PUBLICAR_REAL` | Publica de verdad a Metricool | **OFF** (queda en dry-run) |

**Por qué es SEGURO encender el master + las 3 etapas:** la máquina de contenido solo PRODUCE
hasta el borrador. Cada pieza nace `borrador`/`pendiente` y **para en la cola de revisión**
(`/api/aprobacion/cola`, UI `/operacion/revision/editorial`); el **gate humano** (aprobación
multinivel) sigue intacto. **Nada sale a redes** sin que el humano lo autorice: el posteo real
va por Metricool y está gated por `KENI_PUBLICAR_REAL`, que se queda **OFF**. Además el pipeline
tiene cap por barrido (`KENI_PIPELINE_MAX`, `KENI_AUTOGEN_ARTE_MAX`, def 3) y dedup por
etiqueta, así que no hay ráfagas. La etapa de Ilustrar **degrada** si no hay proveedor de imagen
configurado (no hace nada). Los **defaults siguen OFF en código**: encender es una decisión de
operación, no un cambio de fuente.

Quién los lee: el servicio **`daemons`** (`python -m keni_consola.daemons`) es el que corre los
hilos de fondo en prod (el `back` no arranca daemons; el `worker` solo procesa la cola). Los
flags y el tuning se leen con precedencia **store editable (`/data/ajustes.toml`) > env >
default**.

**Dos formas de encender** (cualquiera vale; el store gana al env):

1. **En caliente, sin reiniciar** (recomendado para validar): cambia el flag en el store editable
   (`KENI_CONSOLA_AJUSTES=/data/ajustes.toml`, compartido por back/worker/daemons) desde la UI de
   ajustes o editando el TOML. El bucle de cada daemon comprueba su flag **en cada ciclo**:
   apagar aplica en ≤ ~1 min; encender tras estar apagado dispara un barrido de inmediato.

2. **Por env** (persistente entre reinicios): descomenta en `deploy/docker-compose.yml` (servicio
   `daemons`) y recrea el servicio:

   ```yaml
   #   KENI_MAQUINA:       "1"
   #   KENI_PIPELINE_RECOLECTAR:       "1"
   #   KENI_PIPELINE_REDACTAR:      "1"
   #   KENI_PIPELINE_ILUSTRAR:  "1"
   #   KENI_PUBLICAR_REAL deliberadamente NO se pone (sigue OFF = dry-run).
   ```

   ```bash
   docker compose up -d --no-deps daemons   # recrea solo el servicio de daemons
   ```

**Observar el avance:** la UI **Pipelines** (`/datos/pipelines`) muestra los temas por etapa de
la cadena (`priorizada → generando_copy → generando_arte → lista_para_revisar`) y el tablero
(`/operacion/parrilla/pendientes`) la lista del día. La cola de aprobación está en
`GET /api/aprobacion/cola` (`total`).

---

## MCP operativo: operar la consola desde Claude Code (`/mcp`)

Hay **dos** MCP, no confundir:

- **`mcp` (servicio, keni-metricas):** SOLO métricas, interno, sin auth propia. Es el de
  la sección siguiente ("Exponer el MCP (opcional)"). No hace falta para lo de abajo.
- **MCP OPERATIVO (`/mcp` del back):** lo que usa **este Claude Code** para *operar* la
  consola —crear/gestionar/aprobar contenido y leer métricas— **sin conocer la API**. Vive
  DENTRO del back (no es un servicio aparte): se sirve en `https://social.kenitech.io/mcp`
  por el mismo Traefik (el router `back` ya enruta `/api` **y** `/mcp`). Implementación en
  `consola/src/keni_consola/mcp_operativo.py`.

**Encenderlo** (apagado por defecto): fija el bearer en `deploy/.env` y recrea el back.

```bash
# Secreto del endpoint (lo presenta el cliente Claude). Guárdalo: no se vuelve a mostrar.
echo "KENI_MCP_BEARER=$(openssl rand -base64 24)" >> .env
# Opcional: usuario al que se atribuyen las acciones (def: KENI_CONSOLA_ADMIN_USER, el dueño).
# echo "KENI_MCP_USUARIO=duena@kenitech.io" >> .env
docker compose up -d --force-recreate back
# Humo: sin bearer -> 401; con bearer -> NO 401 (el MCP responde su handshake).
curl -s -o /dev/null -w '%{http_code}\n' https://social.kenitech.io/mcp                          # 401
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $KENI_MCP_BEARER" \
     -H 'Accept: application/json, text/event-stream' https://social.kenitech.io/mcp             # 405/406, no 401
```

> El usuario `KENI_MCP_USUARIO` debe existir y **no** tener `debe_cambiar_password`
> pendiente (el dueño real ya lo cambió); si no, el MCP queda bloqueado igual que ese
> usuario en la UI. Las acciones llegan **hasta aprobación**: no hay tool de publicar/
> programar real (eso sigue gated por `KENI_PUBLICAR_REAL` y se opera desde la UI).

**Conectar Claude Code** (en la máquina de cada persona):

```bash
claude mcp add --transport http keni-social https://social.kenitech.io/mcp \
  --header "Authorization: Bearer <KENI_MCP_BEARER>"
```

Luego, en Claude Code, las tools aparecen como `keni_contexto`, `keni_crear_contenido`,
`keni_cola_aprobacion`, `keni_aprobar`, `keni_metricas_reporte`, etc.

---

## Exponer el MCP de métricas (opcional)

El `mcp` (keni-metricas) es interno y **sin auth propia**. Para que clientes Claude del
equipo lo usen por HTTP, añade a `mcp` un router Traefik con subdominio + middleware bearer:

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
      Pendiente fino: `--scale worker=N` si el piloto necesita más throughput. (El plan
      de sandbox por usuario en `code.kenitech.io` quedó descartado: ese entorno se
      desmanteló el 2026-06-12.)
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
