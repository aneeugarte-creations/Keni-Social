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

Restore (Postgres, formato custom): `docker exec -i keni-social-db-1 sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < keni-XXXX.dump`.
Restore (volumen): `docker run --rm -v keni-social_keni-data:/v -v /var/backups/keni-social/volumes:/b alpine sh -c 'cd /v && tar xzf /b/keni-data-XXXX.tar.gz'` (con el stack parado).
Offsite (recomendado al escalar): instala `rclone`, configura un remoto y pon
`BACKUP_RCLONE_REMOTE=remoto:keni-social` en `/etc/keni-backup.conf`. El script lo usa solo.

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

- **autoheal y el docker.sock (H2):** `autoheal` monta `/var/run/docker.sock` en RW porque
  `willfarrell/autoheal:1.2.0` solo habla con el socket UNIX (su modo `tcp://` exige mTLS con
  certs cliente, incompatible con un socket-proxy HTTP como el de Woodpecker). Se deja como
  riesgo residual ACEPTADO (imagen fijada, minima, en red interna). Camino futuro: sustituir el
  healer por uno que hable HTTP a un `tecnativa/docker-socket-proxy` (CONTAINERS+POST) como el
  del stack de CI, o anadir mTLS. No se "arregla" con algo fragil que deje el auto-heal muerto.
- **Cuenta `ubuntu` con password usable:** SSH es solo-clave, asi que el password solo sirve en
  consola/su. Se deja a proposito como break-glass de consola (Latitude OOB). Bloquearlo
  (`passwd -l ubuntu`) endurece un pelo a cambio de perder ese fallback; decision del operador.
