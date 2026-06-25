# Guardián: daemon mínimo que resucita contenedores EXITED del stack (el hueco que
# willfarrell/autoheal —solo unhealthy-vivos— y `restart: unless-stopped` —no revive un
# stop deliberado— dejan). Solo necesita curl (hablar con el proxy Docker filtrado) y jq
# (parsear la respuesta). No monta el docker.sock: va siempre vía guardian-docker-proxy.
FROM alpine:3.20

RUN apk add --no-cache curl jq

COPY guardian.sh /usr/local/bin/guardian.sh
RUN chmod +x /usr/local/bin/guardian.sh

# No-root: el guardián solo hace HTTP al proxy y escribe su latido en /tmp.
RUN adduser -D -u 10002 guardian
USER guardian

ENTRYPOINT ["/usr/local/bin/guardian.sh"]
