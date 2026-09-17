# Rescate del servidor Latitude — 17 de septiembre de 2026

Todo lo necesario para volver a montar lo que corría en `162.43.191.103` antes de apagarlo.
Asume que no queda nada encendido: ni el host, ni la tailnet, ni el CI.

**El código NO está aquí.** Vive en `aneeugarte-creations/Keni-Social` (privado) y en
`kenitech-io/keni-social`. Aquí están solo los datos y la configuración, que es lo que no
cabía en git.

## El servidor no era solo keni-social

Servía siete dominios. Todos cayeron a la vez:

| Stack | Dominio | Qué se rescató |
|---|---|---|
| keni-social | `social.kenitech.io` | BD + media + `/data` + secretos |
| keni-ci | `ci-social.kenitech.io` | BD de Woodpecker + su estado |
| keni-voice | `audio.kenitech.io` | BD + modelos + media |
| keni-ops-stg | `ops-stg` / `ops-admin` | BD (12 esquemas) + media |
| deploy-errors | `errors-stg.kenitech.io` | BD + uploads |
| keni-guardian | `guardian.kenitech.io` | repos + trazas + config |

## Qué contiene cada cosa

### `20260917-111220/` — keni-social (14 GB)

| Fichero | Contenido | Sin esto… |
|---|---|---|
| `postgres/keni-*.dump` | BD completa, `pg_dump -Fc` | no hay piezas, usuarios, métricas ni tablero |
| `volumenes/keni-data.tar.gz` | `/data`: 7 marcas, prompts, plantillas, voces | la app arranca vacía |
| `volumenes/garage-data.tar.gz` | blobs S3 | se pierde **toda** la media publicada |
| `volumenes/garage-meta.tar.gz` | índice LMDB de Garage | los blobs existen pero nadie sabe qué son |
| `volumenes/pgdata.tar.gz` | volumen crudo de Postgres | red de seguridad si el dump fallara |
| `volumenes/keni-repo.tar.gz` | clon del carril de auto-desarrollo | — (sus ramas ya están en el archivo git) |
| `volumenes/traefik-acme.tar.gz` | certificados TLS | se regeneran; copiarlo evita el rate-limit de Let's Encrypt |
| `secretos/` | `.env`, `~/.claude`, `authorized_keys` | **nada arranca** |
| `inventario/` | imágenes con digest, compose resuelto, units, firewall | reconstruir el host a ciegas |
| `host/` | systemd, sshd, auditd, crontabs | el endurecimiento del host |

> **`inventario/` y `secretos/` llevan credenciales en claro.** `docker-inspect.json`
> interpola el entorno de los contenedores, así que contiene `POSTGRES_PASSWORD` y
> `WOODPECKER_AGENT_SECRET`. `keni-data.tar.gz` lleva dentro `claude-cfg/.credentials.json`,
> los `secretos.toml` por marca y `control-bearer.secret`. Nada de esto va a un repo.

### `otros/` — los demás stacks (8,1 GB)

Cuatro dumps lógicos (`keni-ops-stg`, `errores`, `keni-voice`, `woodpecker-ci`), sus
volúmenes de datos, y en `dirs-desplegados/` los árboles de `keni-voice`, `keni-guardian`
y `keni-ops-staging-login` tal cual estaban en el servidor — porque allí no eran repos git
y podían llevar ediciones hechas a mano que nunca volvieron a GitHub.

## Levantar keni-social otra vez

```sh
# 0. Los secretos primero: sin el .env no arranca nada.
gpg --decrypt secretos.tar.gz.gpg | tar xzf -

# 1. Código, en el commit que estaba desplegado (979fa43) MÁS la deriva de producción.
git clone git@github.com:aneeugarte-creations/Keni-Social.git keni-social
cd keni-social && git checkout rescate/deriva-produccion
cp ../secretos/env-keni-social deploy/.env

# 2. Volúmenes: crear y rellenar ANTES de levantar el stack.
for v in keni-data garage-meta garage-data keni-repo traefik-acme; do
  docker volume create keni-social_$v
  docker run --rm -v keni-social_$v:/v -v "$PWD/../volumenes":/b alpine \
    sh -c "cd /v && tar xzf /b/$v.tar.gz"
done

# 3. Postgres. OJO: crea el rol keni_app ANTES de restaurar, o cada GRANT del dump falla
#    (ruidoso pero inofensivo; los datos entran igual).
cd deploy && docker compose up -d db && sleep 10
docker exec keni-social-db-1 psql -U postgres -c "create role keni_app login" 2>/dev/null || true
docker exec -i keni-social-db-1 sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists --no-owner' < ../postgres/keni-20260917-111220.dump

# 4. El resto del stack.
bash deploy.sh
```

`garage-meta` y `garage-data` van **juntos**: restaurar uno sin el otro deja la media
inaccesible.

Para los otros stacks, el patrón es el mismo con sus dumps y volúmenes. `keni-ops-stg`
necesita `pgvector/pgvector:0.8.5-pg18`, no un Postgres pelado — usa la extensión.

## Lo que NO sobrevive y hay que rehacer

- **DNS**: los siete dominios apuntaban a `162.43.191.103`. Un servidor nuevo tiene otra IP.
- **Un tenant por instancia** (ADR 0003): secretos y estado son globales por despliegue.
  Cada cliente nuevo necesita su propio stack, no una cuenta dentro de este.
- **El token OAuth de Claude** caduca solo. Está rescatado, pero si expiró hay que
  regenerarlo: sin él los workers no generan copy.
- **Woodpecker**: su BD está rescatada, pero reconstruir el CI es trabajo aparte.
- **La clave SSH `ai-learning`** ya estaba perdida antes del apagado, y el servidor había
  dejado de ser nodo de la tailnet. Se entró autorizando una clave nueva vía el agente de CI.

## Verificado el día del rescate

No es una copia sin comprobar. Se verificó esto:

- **Checksums**: 44/44 en keni-social y 62/62 en los otros stacks, calculados en el
  servidor y recomprobados tras la descarga. La copia es idéntica bit a bit.
- **Restore real de Postgres**, no solo `pg_restore --list`:
  - keni-social → **72 tablas, 31.028.533 filas**
  - keni-ops-stg → **512 tablas en 12 esquemas, 247.687 filas** (con pgvector)
  - errores → 827 tablas, 72.577 filas
  - woodpecker-ci → 19 tablas, 53.851.801 filas
  - keni-voice → 23 tablas, 104 filas
- **Integridad de los 27 tars** con `gzip -t` (CRC del stream completo).
- **Contenido**: las 7 marcas presentes en `marcas.toml` — unotv, claro-sports,
  nacion-gamer, piso-15, fundacion, unotv-us, claro-sports-us.
- **Código**: los 2.077 ficheros versionados de producción son idénticos a `979fa43`,
  salvo 3 con deriva, ya rescatada en `rescate/deriva-produccion`.
- **`gitleaks`** sobre los 3.199 commits del repo: sin filtraciones.
