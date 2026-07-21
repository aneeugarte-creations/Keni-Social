#!/bin/sh
# GUARDIÁN de contenedores EXITED del stack keni-social.
#
# El hueco que cubre: willfarrell/autoheal solo REINICIA contenedores unhealthy-pero-VIVOS, y
# `restart: unless-stopped` NO revive un contenedor parado a propósito (un deploy que hace `stop`
# y luego falla deja el servicio EXITED indefinidamente — el incidente que motivó esto). Este
# daemon sondea la API Docker (vía proxy filtrado) y hace `POST /containers/<id>/start` a los
# contenedores del stack que quedan `exited`, complementando a autoheal sin sustituirlo.
#
# REGLA DE DOS CICLOS (evita pelearse con la política de reinicio de Docker): solo resucita un
# contenedor que sigue `exited` en DOS sondeos consecutivos. Un crash que Docker va a reiniciar
# por su cuenta deja de estar `exited` en el ciclo siguiente, así que no lo tocamos; solo
# actuamos sobre los que quedan parados de verdad. Latencia de resurrección ≈ 2 × intervalo.
#
# RESPETA EL DEPLOY: si existe el flag KENI_GUARDIAN_FLAG_DEPLOY, no actúa (stops/recreaciones
# del deploy son churn esperado, no una avería).
#
# ANTIFLAPPING: máx KENI_GUARDIAN_MAX_ARRANQUES arranques por servicio en KENI_GUARDIAN_VENTANA s;
# superado el tope deja de intentar, lo registra y ESCALA (deja el incidente en el buzón).
set -u

DOCKER="${KENI_GUARDIAN_DOCKER:-http://guardian-docker-proxy:2375}"
SERVICIOS="${KENI_GUARDIAN_SERVICIOS:-back front mantenimiento daemons worker transcriptor worker-dev worker-ralph mcp db files}"
INTERVALO="${KENI_GUARDIAN_INTERVALO:-5}"
MAX_ARRANQUES="${KENI_GUARDIAN_MAX_ARRANQUES:-5}"
VENTANA="${KENI_GUARDIAN_VENTANA:-600}"
FLAG_DEPLOY="${KENI_GUARDIAN_FLAG_DEPLOY:-/estado/desplegando}"
# TTL del flag de deploy (min). deploy.sh lo borra al salir (trap), pero si el deploy MUERE sin
# salir limpio (SIGKILL/OOM/agente de CI caído) el trap no corre y el flag queda RANCIO: el front
# mentiría "actualizando" para siempre y el guardián no curaría nunca. Pasado el TTL lo tratamos
# como rancio. Holgado (un deploy real son minutos) para no borrarlo a mitad de un deploy lento.
FLAG_TTL_MIN="${KENI_GUARDIAN_FLAG_TTL_MIN:-45}"
PROYECTO="${KENI_GUARDIAN_PROYECTO:-keni-social}"
# Escalada: cuando un servicio FLAPEA (el autoheal no basta), el guardián recoge la evidencia
# (logs) y la escribe en $TRIGGER. Quien la recoge es OTRO stack (keni-guardian), que monta este
# directorio y lanza un agente que lo arregla de fondo. Aquí solo se escribe el buzón: si ese
# stack no está delante, el fichero se queda sin leer y no pasa nada. ESCALAR=0 lo desactiva.
# Rate-limit: 1 por ventana.
ESCALAR="${KENI_GUARDIAN_ESCALAR:-1}"
TRIGGER="${KENI_GUARDIAN_TRIGGER:-/estado/incidente.json}"
VENTANA_MIN=$(( VENTANA / 60 )); [ "$VENTANA_MIN" -lt 1 ] && VENTANA_MIN=1

LATIDO=/tmp/keni-guardian.latido
ARRANQUES=/tmp/keni-guardian.arranques   # líneas "<epoch> <servicio>" de arranques recientes
VISTOS_PREV=/tmp/keni-guardian.vistos     # ids exited del ciclo anterior

# Registro de eventos. PLUGGABLE: hoy solo a stdout (=> `docker logs keni-social-guardian-1`,
# el "journal" del contenedor). Enchufar Telegram/ntfy/email es cambiar SOLO este cuerpo.
notificar() { echo "keni-guardian: $*"; }

en_lista() {  # $1 = servicio ; 0 si está en SERVICIOS
  case " $SERVICIOS " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

# Arranques del servicio en la ventana reciente (poda los viejos de paso).
arranques_recientes() {  # $1 = servicio -> imprime el conteo
  ahora="$(date +%s)"
  corte=$((ahora - VENTANA))
  if [ -f "$ARRANQUES" ]; then
    awk -v c="$corte" '$1 >= c' "$ARRANQUES" > "$ARRANQUES.tmp" 2>/dev/null && mv "$ARRANQUES.tmp" "$ARRANQUES"
    awk -v s="$1" '$2 == s' "$ARRANQUES" | wc -l | tr -d ' '
  else
    echo 0
  fi
}

registrar_arranque() {  # $1 = servicio
  echo "$(date +%s) $1" >> "$ARRANQUES"
}

# Resucita un contenedor exited. POST /containers/<id>/start: 204 = arrancado, 304 = ya corría.
arrancar() {  # $1 = id ; $2 = servicio
  codigo="$(curl -s -m 10 -o /dev/null -w '%{http_code}' -X POST "$DOCKER/containers/$1/start" 2>/dev/null)"
  case "$codigo" in
    204) notificar "RESUCITADO '$2' (estaba EXITED) -> start OK"; registrar_arranque "$2" ;;
    304) : ;;  # ya estaba corriendo: nada que decir
    *)   notificar "FALLO al arrancar '$2' (HTTP ${codigo:-sin-respuesta})" ;;
  esac
}

# Escala: recoge la evidencia (logs del contenedor caído, vía el proxy) y escribe $TRIGGER para
# que el guardián externo diagnostique y, si es de código, commitee el fix. Rate-limit 1/ventana
# por servicio (marca con TTL=ventana): no inunda de triggers mientras un servicio flapea.
escalar() {  # $1 = id ; $2 = servicio
  [ "$ESCALAR" = 1 ] || return 0
  m="/tmp/keni-guardian.escalado.$2"
  [ -z "$(find "$m" -mmin "-$VENTANA_MIN" 2>/dev/null)" ] || return 0   # ya escalado en la ventana
  : > "$m" 2>/dev/null || true
  # Logs recientes: el stream de /logs viene multiplexado (cabeceras de 8 bytes por frame); lo
  # pasamos a texto legible quitando lo no imprimible. Suficiente para que el agente diagnostique.
  logs="$(curl -sG -m 10 "$DOCKER/containers/$1/logs" \
            --data-urlencode 'stdout=true' --data-urlencode 'stderr=true' \
            --data-urlencode 'tail=200' 2>/dev/null | tr -cd '[:print:]\n\t' | tail -c 8000)"
  {
    echo "Servicio caído (flapping): $2"
    echo "Contenedor: $1"
    echo "Detección: el guardián lo resucitó $MAX_ARRANQUES veces en ${VENTANA}s y sigue cayendo."
    echo "Proyecto compose: $PROYECTO"
    echo ""
    echo "## Logs recientes (docker logs --tail 200, desmultiplexado):"
    echo "$logs"
  } > "$TRIGGER.tmp" 2>/dev/null && mv "$TRIGGER.tmp" "$TRIGGER" 2>/dev/null \
    && notificar "ESCALADO: '$2' (evidencia en $TRIGGER)" \
    || notificar "no pude escribir el trigger de escalada $TRIGGER"
}

notificar "arranca (proyecto=$PROYECTO intervalo=${INTERVALO}s servicios=[$SERVICIOS])"

while :; do
  : > "$LATIDO" 2>/dev/null || true   # latido para el healthcheck

  if [ -f "$FLAG_DEPLOY" ]; then
    if [ -z "$(find "$FLAG_DEPLOY" -mmin "-$FLAG_TTL_MIN" 2>/dev/null)" ]; then
      # Flag RANCIO: un deploy murió sin limpiar (su trap EXIT no llegó a correr). Lo borramos —
      # esto también arregla el mensaje del front, que lee el MISMO fichero— y retomamos el
      # autoheal para resucitar lo que ese deploy dejó EXITED (justo el enganche deploy->autoheal).
      notificar "flag de deploy RANCIO (>${FLAG_TTL_MIN}min): un deploy no limpió al salir; lo borro y retomo el autoheal"
      rm -f "$FLAG_DEPLOY" 2>/dev/null || notificar "no pude borrar el flag rancio $FLAG_DEPLOY (¿permisos del dir estado?)"
    else
      # Deploy en curso (flag fresco): el churn (stops/recreaciones) es esperado. No tocamos nada
      # y reseteamos la memoria de "vistos" para no resucitar al primer ciclo tras el deploy un
      # contenedor que el propio deploy estaba recreando.
      : > "$VISTOS_PREV" 2>/dev/null || true
      sleep "$INTERVALO"
      continue
    fi
  fi

  # Contenedores del stack en estado `exited` AHORA (filtro empujado a Docker).
  filtro='{"label":["com.docker.compose.project='"$PROYECTO"'"],"status":["exited"]}'
  resp="$(curl -sG -m 10 "$DOCKER/containers/json" \
            --data-urlencode 'all=true' \
            --data-urlencode "filters=$filtro" 2>/dev/null)"

  # "<id> <servicio>" por contenedor exited (jq tolera respuesta vacía/no-array).
  actuales="$(printf '%s' "$resp" | jq -r 'if type=="array" then .[] | "\(.Id) \(.Labels["com.docker.compose.service"] // "")" else empty end' 2>/dev/null)"

  if [ -n "$actuales" ]; then
    printf '%s\n' "$actuales" | while IFS=' ' read -r id svc; do
      [ -n "$id" ] || continue
      en_lista "$svc" || continue
      # Regla de dos ciclos: solo si también estaba exited el ciclo anterior.
      if [ -f "$VISTOS_PREV" ] && grep -q "^$id\$" "$VISTOS_PREV" 2>/dev/null; then
        n="$(arranques_recientes "$svc")"
        if [ "$n" -ge "$MAX_ARRANQUES" ]; then
          # Flapping: el autoheal no basta. Aviso rate-limitado (1/min) y ESCALA (1/ventana) para
          # que un agente lo arregle de fondo (lee logs+commits, commitea el fix).
          marca="/tmp/keni-guardian.flap.$svc"
          if [ -z "$(find "$marca" -mmin -1 2>/dev/null)" ]; then
            notificar "'$svc' FLAPEA (${n} arranques en ${VENTANA}s): dejo de reintentar; escalo"
            : > "$marca" 2>/dev/null || true
          fi
          escalar "$id" "$svc"
        else
          arrancar "$id" "$svc"
        fi
      fi
    done
  fi

  # Memoriza los exited de ESTE ciclo (solo ids) para la regla de dos ciclos del siguiente.
  if [ -n "$actuales" ]; then
    printf '%s\n' "$actuales" | awk '{print $1}' > "$VISTOS_PREV"
  else
    : > "$VISTOS_PREV"
  fi

  sleep "$INTERVALO"
done
