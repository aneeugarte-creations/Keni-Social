#!/usr/bin/env bash
# Cierra el bypass estructural Docker <-> UFW. Docker inserta sus cadenas en FORWARD por
# DELANTE de UFW, asi que un contenedor publicado a 0.0.0.0 (`-p 0.0.0.0:X`) queda
# accesible desde internet AUNQUE UFW lo "deniegue". La cadena DOCKER-USER (que Docker
# respeta y NO reescribe) es el sitio para imponer politica. Hoy NADA se publica a
# 0.0.0.0 (solo 127.0.0.1:5432 y Traefik en host-mode), asi que esto es defensa ante un
# `-p` publico FUTURO por descuido: por defecto, ninguna conexion entrante NUEVA desde la
# interfaz publica llega a un contenedor.
#
# Seguro por construccion:
#  - El ingress real (80/443) lo sirve Traefik en network_mode: host => cadena INPUT, no
#    FORWARD => NO se ve afectado. SSH idem (INPUT). No hay riesgo de autobloqueo.
#  - El egress de los contenedores sale por la iface publica (out=IFACE), no entra por
#    ella (in=IFACE): no coincide con la regla. Sus respuestas son ESTABLISHED => RETURN.
#  - Trafico inter-contenedor va por las bridges (in=br-*), no por IFACE: intacto.
#
# Idempotente: reescribe DOCKER-USER en cada arranque (oneshot systemd After=docker).
set -euo pipefail

IFACE="$(ip -o -4 route show to default | awk '{print $5; exit}')"
[ -n "${IFACE:-}" ] || { echo "keni-firewall: no se detecto la iface por defecto" >&2; exit 1; }
echo "keni-firewall: iface publica = $IFACE"

# Reescribe nuestra politica (flush + reinsercion deterministica).
iptables -F DOCKER-USER
# 1) Respuestas a conexiones iniciadas por contenedores (egress): permitir.
iptables -A DOCKER-USER -i "$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN
# 2) Conexiones NUEVAS/INVALID entrantes desde internet hacia contenedores: bloquear.
iptables -A DOCKER-USER -i "$IFACE" -m conntrack --ctstate NEW,INVALID -j DROP
# 3) Resto (inter-contenedor, host->contenedor, loopback): seguir el flujo normal.
iptables -A DOCKER-USER -j RETURN

echo "keni-firewall: DOCKER-USER aplicada:"
iptables -S DOCKER-USER
