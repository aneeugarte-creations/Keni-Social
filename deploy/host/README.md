# Endurecimiento del host (keni-social)

Artefactos de seguridad a NIVEL DE HOST (no entran en `docker compose`; se instalan en
el servidor, igual que `deploy/janitor`). Todo aqui es versionado en git y se aplica con
los comandos de abajo por SSH (`ssh -i ~/.ssh/ai-learning ubuntu@162.43.191.103`).

Resumen de lo que cubre, con la severidad del audit de infra (2026-06):

| Artefacto | Item | Que hace |
|---|---|---|
| `firewall/keni-docker-firewall.*` | M1 | Cierra el bypass Docker↔UFW (politica por defecto en `DOCKER-USER`). |
| `auditd/keni.rules` | M2 | Traza de auditoria de identidad/sudo/SSH/Docker/secretos. |
| `sshd_config.d/99-keni-hardening.conf` | Low | `AllowUsers`, cripto moderna, RSA≥3072, sin agent-forwarding, `LogLevel VERBOSE`. |
| `apt/52-keni-auto-reboot.conf` | Low | Auto-reboot 04:00 UTC tras parches de kernel desatendidos. |
| `../backup/keni-backup.*` | C1 | Backup local diario (Postgres dump + media Garage) con retencion. |
| `keni-alertas.*` + `keni-alerta-fallo@.service` | M | Alertas de infra cada 10 min (healthchecks incl. db, disco, backup, TLS) sin servicios externos. |

> El backup vive en `deploy/backup/` (no aqui) porque depende del stack; se instala igual.

---

## 1. Backup local (C1 — critico)

```sh
sudo install -m 0755 deploy/backup/keni-backup.sh   /usr/local/bin/keni-backup
sudo install -m 0644 deploy/backup/keni-backup.service /etc/systemd/system/keni-backup.service
sudo install -m 0644 deploy/backup/keni-backup.timer   /etc/systemd/system/keni-backup.timer
# (opcional) overrides: echo 'BACKUP_KEEP=14' | sudo tee /etc/keni-backup.conf
sudo systemctl daemon-reload
sudo systemctl enable --now keni-backup.timer
sudo systemctl start keni-backup.service   # primer backup AHORA; revisa el resultado:
ls -lah /var/backups/keni-social/postgres /var/backups/keni-social/volumes
```

Cada run VERIFICA lo que escribe (`pg_restore --list` del dump + `gzip -t` de cada tar) y
deja `estado.json` en `$BACKUP_DIR` (lo muestra el panel Sistema de la Consola, que monta
el directorio en solo-lectura; por eso el script normaliza permisos a 755/644). Un fallo
de verificacion FALLA el run y dispara `OnFailure=` (keni-alertas).

Prueba de RESTORE completo (hazla tras cambios de esquema grandes o trimestralmente):
```sh
ULTIMO=$(ls -t /var/backups/keni-social/postgres/keni-*.dump | head -1)
docker run --rm -d --name pg-restore-test -e POSTGRES_PASSWORD=t postgres:16.13
sleep 8
docker exec -i pg-restore-test pg_restore -U postgres -d postgres --no-owner < "$ULTIMO"
docker exec pg-restore-test psql -U postgres -tc "select count(*) from pg_tables where schemaname='public'"
docker rm -f pg-restore-test
```

Restore (Postgres, formato custom): `docker exec -i keni-social-db-1 sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < keni-XXXX.dump`.
Restore (volumen): `docker run --rm -v keni-social_keni-data:/v -v /var/backups/keni-social/volumes:/b alpine sh -c 'cd /v && tar xzf /b/keni-data-XXXX.tar.gz'` (con el stack parado).
Offsite (recomendado al escalar): instala `rclone`, configura un remoto y pon
`BACKUP_RCLONE_REMOTE=remoto:keni-social` en `/etc/keni-backup.conf`. El script lo usa solo.

## 1b. Alertas de infra (M) — sin servicios externos

Chequeo cada 10 min: salud de contenedores (INCLUIDO `db`, que esta excluido de autoheal
a proposito), disco > 85 %, ultimo backup local > 26 h y certificado TLS < 15 dias. Alerta
SIEMPRE al journal con prioridad `err`; opcionalmente a un webhook JSON. Ademas, el
servicio de backup lleva `OnFailure=keni-alerta-fallo@%n.service`: un backup fallido
notifica por el mismo canal.

```sh
sudo install -m 0755 deploy/host/keni-alertas.sh /usr/local/bin/keni-alertas
sudo install -m 0644 deploy/host/keni-alertas.service        /etc/systemd/system/keni-alertas.service
sudo install -m 0644 deploy/host/keni-alertas.timer          /etc/systemd/system/keni-alertas.timer
sudo install -m 0644 deploy/host/keni-alerta-fallo@.service  /etc/systemd/system/keni-alerta-fallo@.service
# Reinstala tambien la unidad de backup (ahora con OnFailure= hacia keni-alerta-fallo@):
sudo install -m 0644 deploy/backup/keni-backup.service /etc/systemd/system/keni-backup.service
# (opcional) webhook y umbrales:
#   echo 'KENI_ALERTA_WEBHOOK=https://hooks.example.com/...' | sudo tee /etc/keni-alertas.conf
sudo systemctl daemon-reload
sudo systemctl enable --now keni-alertas.timer
sudo systemctl start keni-alertas.service   # chequeo AHORA; si todo esta sano sale 0
journalctl -t keni-alertas -n 20            # las alertas (si las hubo)
```

Ver las alertas historicas: `journalctl -p err -t keni-alertas`. Un chequeo con problemas
deja la unidad `failed` (visible en `systemctl --failed`) ademas de notificar.

## 2. Firewall DOCKER-USER (M1)

```sh
sudo install -m 0755 deploy/host/firewall/keni-docker-firewall.sh /usr/local/bin/keni-docker-firewall
sudo install -m 0644 deploy/host/firewall/keni-docker-firewall.service /etc/systemd/system/keni-docker-firewall.service
sudo systemctl daemon-reload
sudo systemctl enable --now keni-docker-firewall.service
sudo iptables -S DOCKER-USER          # verifica las 3 reglas
# Comprueba que NO rompio nada: la web sigue (curl -I https://social.kenitech.io) y el
# egress de contenedores va (docker exec keni-social-back-1 python -c "import urllib.request;
# print(urllib.request.urlopen('https://api.anthropic.com').status)").
```

## 3. auditd (M2)

```sh
sudo apt-get update && sudo apt-get install -y auditd audispd-plugins
sudo install -m 0640 deploy/host/auditd/keni.rules /etc/audit/rules.d/keni.rules
sudo augenrules --load
sudo systemctl enable --now auditd
sudo auditctl -l            # lista las reglas cargadas
```

## 4. SSH hardening (Low) — con red de seguridad

```sh
sudo install -m 0644 deploy/host/sshd_config.d/99-keni-hardening.conf /etc/ssh/sshd_config.d/99-keni-hardening.conf
sudo sshd -t               # DEBE pasar sin output. Si falla, NO recargues.
sudo systemctl reload ssh
# En OTRA terminal, ANTES de cerrar esta: confirma que entras con la clave de operacion.
ssh -i ~/.ssh/ai-learning ubuntu@162.43.191.103 true && echo "SSH OK"
```

## 5. Auto-reboot tras parches (Low)

```sh
sudo install -m 0644 deploy/host/apt/52-keni-auto-reboot.conf /etc/apt/apt.conf.d/52-keni-auto-reboot.conf
# Verifica: el reboot solo ocurre si /var/run/reboot-required aparece tras un upgrade.
```

---

### Notas

- **Deploy del CI por `docker.sock` (por diseño):** el step de deploy monta el sock del host. En un
  host unico donde CI y prod comparten maquina es lo natural; indireccionarlo por SSH a localhost no
  cierra el camino real (un commit malicioso en `main` -> `deploy.sh` corre como root igualmente), asi
  que no compensa la ceremonia. La imagen del step va pineada por digest (su imagen es TCB).

- **autoheal y el docker.sock (resuelto):** `autoheal` ya NO monta `/var/run/docker.sock`.
  Habla la API Docker por HTTP a `autoheal-docker-proxy` (`tecnativa/docker-socket-proxy`),
  filtrado a solo `CONTAINERS`+`POST` (lo unico que usa: `GET /containers/json` y `POST
  /containers/<id>/restart`), en la red interna sin egress `autoheal-proxy`. El proxy es el unico
  con el sock, montado en `:ro`. Mismo patron que el proxy del agente Woodpecker. Nota de version:
  `willfarrell/autoheal:1.2.0` mapeaba `tcp://`→HTTPS+mTLS (incompatible con un proxy HTTP plano);
  el soporte de `tcp://`→`http://` llego despues, asi que la imagen se fija por DIGEST de `latest`
  (ver `deploy/docker-compose.yml`). El cambio del compose es PROMOVIBLE (no requiere setup de host).
- **Cuenta `ubuntu` con password usable:** SSH es solo-clave, asi que el password solo sirve en
  consola/su. Se deja a proposito como break-glass de consola (Latitude OOB). Bloquearlo
  (`passwd -l ubuntu`) endurece un pelo a cambio de perder ese fallback; decision del operador.

## Acceso SSH: vias, fail2ban y rafagas de conexiones

Dos vias de entrada al servidor; la tailnet es la principal y la publica el fallback:

- **Tailnet (principal):** el servidor es el nodo `learn-01` (`100.72.242.71`) en la tailnet
  de Tailscale (`tailscaled` instalado como servicio; enrolado con `--accept-dns=false` para
  no tocar el resolv.conf del host). El rango `100.64.0.0/10` esta en el `ignoreip` de
  fail2ban: por aqui NO hay bans por rafagas. El alias `ssh latitude` de la maquina del
  operador apunta aqui.
- **Publica (fallback):** `ubuntu@162.43.191.103`, solo-clave. La protege **fail2ban**
  (jail `sshd` en `/etc/fail2ban/jail.d/keni-sshd.local`: maxretry 5 en 10 min -> ban 1 h).
  El `ignoreip` lleva, ademas de la tailnet, los prefijos del operador; las IPs dinamicas
  de ISP caducan, asi que ante un `Connection refused` con sshd vivo (verificable desde
  fuera: `https://check-host.net/check-tcp?host=<ip>:22`) lo primero es mirar
  `sudo fail2ban-client status sshd`. El servicio web no se ve afectado por estos bans.

Reglas para scripts/agentes sobre la via publica: multiplexar con ControlMaster en vez de
abrir N conexiones sueltas, y ante un rechazo NO insistir en bucle corto:

```sh
ssh -o ControlMaster=auto -o ControlPath=~/.ssh/cm/%r@%h -o ControlPersist=600 ...
```

(El sshd de este host es OpenSSH 9.6: las `PerSourcePenalties` de OpenSSH >= 9.8 NO aplican
aqui; los bloqueos por rafaga son de fail2ban.)
