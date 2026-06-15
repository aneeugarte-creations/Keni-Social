#!/usr/bin/env bash
# Alertas de infra de keni-social SIN servicios externos (audit 2026-06, item M).
#
# Corre cada 10 min via systemd timer (keni-alertas.timer) y comprueba:
#   1) Salud de los contenedores del stack: back (su healthcheck ya es curl /healthz),
#      front, worker, mcp, files, daemons (healthcheck por fichero de latido desde
#      2026-06) y EN ESPECIAL db (Postgres esta EXCLUIDO del sidecar autoheal a
#      proposito, asi que sin esto un db unhealthy pasaria desapercibido).
#   2) Disco raiz > KENI_ALERTA_DISCO_MAX % (def 85).
#   3) Antiguedad del ultimo backup local (dump de Postgres en /var/backups/keni-social)
#      > KENI_ALERTA_BACKUP_MAX_H horas (def 26: el timer de backup es diario).
#   4) Certificado TLS de KENI_ALERTA_HOST (def social.kenitech.io) caduca en menos de
#      KENI_ALERTA_CERT_MIN_DIAS dias (def 15; Let's Encrypt renueva a los 30).
#
# NOTIFICACION: siempre escribe en el journal con prioridad `err` (visible en
# `journalctl -p err -t keni-alertas`). Si KENI_ALERTA_WEBHOOK esta definido (en
# /etc/keni-alertas.conf), ademas hace POST JSON {"texto": ...} a esa URL (formato
# compatible con webhooks tipo Slack/Mattermost via clave "text" duplicada).
#
# MODO OnFailure: `keni-alertas --fallo <unidad>` notifica directamente que una unidad
# systemd fallo (lo usa keni-alerta-fallo@.service, enganchado al OnFailure= del backup).
#
# Instalacion: ver deploy/host/README.md. NO se auto-instala desde el deploy.
set -uo pipefail

HOST_TLS="${KENI_ALERTA_HOST:-social.kenitech.io}"
DISCO_MAX="${KENI_ALERTA_DISCO_MAX:-85}"
BACKUP_MAX_H="${KENI_ALERTA_BACKUP_MAX_H:-26}"
CERT_MIN_DIAS="${KENI_ALERTA_CERT_MIN_DIAS:-15}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/keni-social}"
WEBHOOK="${KENI_ALERTA_WEBHOOK:-}"

PROBLEMAS=()

notificar() {
  local texto="$1"
  logger -p user.err -t keni-alertas "$texto"
  if [[ -n "$WEBHOOK" ]]; then
    # JSON seguro via jq si esta; fallback con escapado minimo. Best-effort: el webhook
    # caido no debe tumbar la alerta (ya quedo en el journal).
    local cuerpo
    if command -v jq >/dev/null 2>&1; then
      cuerpo="$(jq -nc --arg t "$texto" --arg h "$(hostname)" '{texto: $t, text: $t, host: $h}')"
    else
      cuerpo="{\"texto\": \"${texto//\"/\\\"}\", \"text\": \"${texto//\"/\\\"}\"}"
    fi
    curl -fsS -m 10 -X POST -H 'Content-Type: application/json' -d "$cuerpo" "$WEBHOOK" \
      >/dev/null 2>&1 || logger -p user.warning -t keni-alertas "webhook KO (la alerta queda solo en el journal)"
  fi
}

# --- Modo OnFailure: notificacion directa de una unidad fallida y salir. ---
if [[ "${1:-}" == "--fallo" ]]; then
  notificar "ALERTA keni-social: la unidad systemd '${2:-desconocida}' ha FALLADO. Revisa: journalctl -u '${2:-}' -n 50"
  exit 0
fi

# --- 1) Salud de contenedores (db incluido: esta fuera de autoheal a proposito). ---
salud() {  # estado de salud (o de ejecucion si no tiene healthcheck) de un contenedor
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null || echo "ausente"
}
for svc in back front db worker files mcp daemons; do
  estado="$(salud "keni-social-${svc}-1")"
  if [[ "$estado" != "healthy" ]]; then
    PROBLEMAS+=("contenedor keni-social-${svc}-1 NO healthy (estado: ${estado})")
  fi
done
for svc in traefik; do  # sin healthcheck: basta running
  estado="$(salud "keni-social-${svc}-1")"
  if [[ "$estado" != "running" && "$estado" != "healthy" ]]; then
    PROBLEMAS+=("contenedor keni-social-${svc}-1 NO esta corriendo (estado: ${estado})")
  fi
done

# --- 2) Disco raiz. ---
uso_disco="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
if [[ -n "$uso_disco" && "$uso_disco" -gt "$DISCO_MAX" ]]; then
  PROBLEMAS+=("disco raiz al ${uso_disco}% (umbral ${DISCO_MAX}%)")
fi

# --- 3) Antiguedad del ultimo backup local (dump de Postgres). ---
if [[ -d "$BACKUP_DIR/postgres" ]]; then
  reciente="$(find "$BACKUP_DIR/postgres" -name 'keni-*.dump' -mmin "-$((BACKUP_MAX_H * 60))" | head -n1)"
  if [[ -z "$reciente" ]]; then
    PROBLEMAS+=("ningun backup de Postgres en las ultimas ${BACKUP_MAX_H}h en $BACKUP_DIR/postgres")
  fi
else
  PROBLEMAS+=("no existe $BACKUP_DIR/postgres (¿backup local sin instalar?)")
fi

# --- 4) Caducidad del certificado TLS (via el Traefik local en :443). ---
cert="$(echo | timeout 15 openssl s_client -connect 127.0.0.1:443 -servername "$HOST_TLS" 2>/dev/null | openssl x509 2>/dev/null)"
if [[ -z "$cert" ]]; then
  PROBLEMAS+=("no se pudo leer el certificado TLS de ${HOST_TLS} en 127.0.0.1:443")
elif ! printf '%s' "$cert" | openssl x509 -noout -checkend "$((CERT_MIN_DIAS * 86400))" >/dev/null 2>&1; then
  caduca="$(printf '%s' "$cert" | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
  PROBLEMAS+=("certificado TLS de ${HOST_TLS} caduca en < ${CERT_MIN_DIAS} dias (notAfter: ${caduca})")
fi

# --- 5) Sonda HTTP de punta a punta (Traefik -> back) ---
# Pedimos /healthz del host publico a traves del Traefik LOCAL (:443): cubre ingress + routing +
# TLS + back en una sola sonda barata. 3 intentos para no alertar por un blip.
intentos=0; sonda_ok=0
while (( intentos < 3 )); do
  codigo="$(curl -sk -o /dev/null -w '%{http_code}' -m 10 --resolve "${HOST_TLS}:443:127.0.0.1" "https://${HOST_TLS}/healthz" 2>/dev/null)"
  if [[ "$codigo" == "200" ]]; then sonda_ok=1; break; fi
  intentos=$((intentos + 1)); sleep 5
done
if [[ "$sonda_ok" != 1 ]]; then
  PROBLEMAS+=("sonda HTTPS de punta a punta FALLO (https://${HOST_TLS}/healthz via Traefik local devolvio '${codigo:-sin respuesta}')")
fi

# --- Resultado. ---
if ((${#PROBLEMAS[@]} > 0)); then
  for p in "${PROBLEMAS[@]}"; do
    notificar "ALERTA keni-social: $p"
  done
  exit 1   # la unidad queda 'failed' -> visible en systemctl --failed
fi
exit 0
