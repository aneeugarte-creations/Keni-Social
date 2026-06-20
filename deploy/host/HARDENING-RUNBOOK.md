# Runbook de endurecimiento — pasos de HOST (manuales)

Pasos que el OPERADOR ejecuta en el server (`ssh latitude`, con `sudo`) para completar dos
endurecimientos cuyo cambio de repo YA esta hecho pero que NO surten efecto hasta tocar el host:

- **F — deploy sin `docker.sock` RW**: el step de CI ya no monta el socket; ahora despliega por
  SSH contra `keni-deploy`. Hasta completar esta seccion, **el pipeline de deploy falla cerrado**
  (es deliberado: mejor no desplegar que desplegar con el agujero abierto).
- **A — PAT de GitHub de scope minimo + segregar credenciales del volumen compartido**: reduce el
  blast radius de las credenciales que hoy montan los workers.

> Los artefactos versionados de F viven en `deploy/host/keni-deploy/`. Igual que el resto de
> `deploy/host/`, se instalan a mano con los comandos de abajo; no entran en `docker compose`.

---

## F — Deploy por SSH a `keni-deploy` (sin docker.sock en CI)

### Modelo

El step `build-and-deploy` de `.woodpecker/deploy.yml` ya NO monta `/var/run/docker.sock` ni
volumenes. Hace:

```
ssh -i <deploy_ssh_key> -o StrictHostKeyChecking=yes keni-deploy@host.docker.internal "$CI_COMMIT_SHA"
```

`keni-deploy` es un usuario **sin privilegios y sin grupo docker**. Su `authorized_keys` fuerza
(`command=`) un unico comando: `sudo -n /usr/local/sbin/keni-deploy-run`. La SHA viaja en
`SSH_ORIGINAL_COMMAND`; el wrapper la **valida** (`^[0-9a-f]{40}$`), exige que sea **antecesora de
`origin/main`**, toma `flock` sobre `/home/ubuntu/keni-social/.deploy.lock`, hace `git checkout
--force <sha>` y delega en `deploy/deploy.sh` (su logica de build/up/healthcheck/rollback NO se
toca). El cliente CI no puede ejecutar nada mas: solo entregar una SHA ya presente en `main`.

### 1. Crear el usuario `keni-deploy` (sin grupo docker)

```sh
sudo useradd --create-home --shell /usr/sbin/nologin keni-deploy
# Verifica que NO esta en el grupo docker (no debe aparecer):
id keni-deploy
```

> `nologin` esta bien: la sesion SSH no abre shell, ejecuta la forced command via sudo.

### 2. Instalar el wrapper privilegiado

```sh
sudo install -m 0755 -o root -g root \
  deploy/host/keni-deploy/keni-deploy-run /usr/local/sbin/keni-deploy-run
```

### 3. sudoers (NOPASSWD solo para el wrapper + env_keep de la SHA)

```sh
sudo install -m 0440 -o root -g root \
  deploy/host/keni-deploy/keni-deploy.sudoers /etc/sudoers.d/keni-deploy
sudo visudo -cf /etc/sudoers.d/keni-deploy     # DEBE decir "parsed OK"; si falla, borra el fichero
```

### 4. Par de claves SSH del CI + authorized_keys con forced command

En tu maquina (o en el host, da igual) genera el par del CI:

```sh
ssh-keygen -t ed25519 -f /tmp/deploy_ssh_key -C keni-deploy-ci -N ''
# /tmp/deploy_ssh_key      -> secreto Woodpecker `deploy_ssh_key` (PRIVADA, paso 7)
# /tmp/deploy_ssh_key.pub  -> va en authorized_keys de keni-deploy (PUBLICA, aqui)
```

Construye el `authorized_keys` desde la plantilla versionada, sustituyendo la clave publica:

```sh
sudo install -d -m 700 -o keni-deploy -g keni-deploy /home/keni-deploy/.ssh
# Toma la linea `command=...` de la plantilla y reemplaza la parte ssh-ed25519 por tu .pub:
PUB="$(cut -d' ' -f1-2 /tmp/deploy_ssh_key.pub)"
sudo sh -c "sed 's# ssh-ed25519 AAAA_REEMPLAZA_POR_LA_CLAVE_PUBLICA keni-deploy-ci# '\"$PUB\"' keni-deploy-ci#' \
  deploy/host/keni-deploy/authorized_keys.example | grep '^command=' > /home/keni-deploy/.ssh/authorized_keys"
sudo chown keni-deploy:keni-deploy /home/keni-deploy/.ssh/authorized_keys
sudo chmod 600 /home/keni-deploy/.ssh/authorized_keys
cat /home/keni-deploy/.ssh/authorized_keys   # revisa: una linea, forced command + tu clave
```

### 5. Convertir `/home/ubuntu/keni-social` en clon git con credencial READ-ONLY

Hoy ese dir es un arbol sincronizado por `rsync`. El nuevo deploy hace `git fetch/checkout`
ahi, asi que debe ser un clon git con acceso de SOLO LECTURA a `origin` (el fetch no necesita
push; cuanto menos pueda, mejor).

```sh
cd /home/ubuntu/keni-social
# Si aun no es un repo git, inicializa el remoto preservando .env y datos del host:
sudo -u ubuntu git init -q 2>/dev/null || true
sudo -u ubuntu git remote add origin https://github.com/kenitech-io/keni-social.git 2>/dev/null \
  || sudo -u ubuntu git remote set-url origin https://github.com/kenitech-io/keni-social.git
# Credencial READ-ONLY: PAT fine-grained con `contents: read` (NO write) sobre el repo, o repo
# publico sin credencial. Guardala fuera del arbol, modo store con permisos estrictos:
sudo -u ubuntu git config credential.helper 'store --file=/home/ubuntu/.git-credentials-ro'
# (escribe /home/ubuntu/.git-credentials-ro con la linea https://x-access-token:<PAT_RO>@github.com)
sudo install -m 600 -o ubuntu -g ubuntu /dev/null /home/ubuntu/.git-credentials-ro
# rellena el fichero con la credencial RO; luego:
sudo -u ubuntu git fetch --quiet origin main
sudo -u ubuntu git checkout -B main origin/main
```

> El wrapper corre `git` como root (via sudo) en este dir. Asegura que root puede leer la
> credencial RO o configura `credential.helper` a nivel de sistema; alternativa simple: deja el
> repo publico y el `git fetch` no necesita credencial.

### 6. Red CI -> host (host.docker.internal)

El step alcanza el sshd del host por `host.docker.internal` (mapeado a `host-gateway` en el
YAML). Confirma que el sshd escucha en la interfaz del bridge Docker y que **fail2ban no banea la
subred del bridge** (el deploy usa clave, no falla, asi que no deberia gatillar; aun asi):

```sh
sudo ss -ltnp 'sport = :22'                 # sshd escuchando (0.0.0.0:22 cubre el bridge)
ip -4 addr show docker0                      # rango del bridge (p.ej. 172.17.0.0/16)
sudo fail2ban-client get sshd ignoreip       # considera anadir el rango del bridge al ignoreip
```

> Si prefieres no exponer sshd al bridge, alternativa: apuntar el deploy al endpoint tailnet del
> host y enganchar el step a la tailnet; mas complejo. La via host-gateway es la mas simple.

### 7. Registrar los secretos en Woodpecker

`ci-social.kenitech.io` -> Repo `keni-social` -> Settings -> Secrets:

- **`deploy_ssh_key`** = contenido de `/tmp/deploy_ssh_key` (clave PRIVADA, multilinea completa).
- **`deploy_known_hosts`** = host-key PUBLICA FIJADA del destino. Genera la linea con la clave del
  host pero usando el nombre con el que conecta el CI:

  ```sh
  # toma la host-key real del servidor y reescribe el nombre a host.docker.internal:
  ssh-keyscan -t ed25519 162.43.191.103 2>/dev/null | sed 's/^[^ ]*/host.docker.internal/'
  ```

  Pega esa linea como valor del secreto. (No es sensible —es publica— pero como secreto se
  mantiene en un solo sitio y fuera del git.)

> Limita ambos secretos al evento que los usa si tu Woodpecker lo permite. No marques el repo como
> "trusted/Volumenes" para este pipeline: ya no monta sock ni volumenes.

### 8. Validar (disparo manual, sin tocar prod si falla)

```sh
# Desde el contenedor de step seria el ssh; a mano, simula el camino feliz como keni-deploy:
SHA=$(cd /home/ubuntu/keni-social && git rev-parse origin/main)
sudo -u keni-deploy env SSH_ORIGINAL_COMMAND="$SHA" sudo -n /usr/local/sbin/keni-deploy-run
# Casos que DEBEN fallar (exit !=0) sin desplegar:
sudo -u keni-deploy env SSH_ORIGINAL_COMMAND="nope" sudo -n /usr/local/sbin/keni-deploy-run; echo "exit=$?"
sudo -u keni-deploy env SSH_ORIGINAL_COMMAND="$(printf '%040d' 0)" sudo -n /usr/local/sbin/keni-deploy-run; echo "exit=$?"
```

Luego lanza el pipeline `deploy` "manual" en Woodpecker sobre `main` y verifica verde + web viva
(`curl -I https://social.kenitech.io`). Solo tras esto el endurecimiento F esta completo.

### Revertir (si algo falla)

El cambio es solo de invocacion; `deploy.sh` no cambio. Para volver al modelo anterior basta
restaurar el step que montaba el sock (git revert del commit de F). No hay migracion de datos.

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

> El PAT de DEPLOY (seccion F.5) es DISTINTO y de solo `Contents: read`. No reutilices uno para
> ambos: push y fetch tienen necesidades opuestas de privilegio.

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
