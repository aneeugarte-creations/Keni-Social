#!/bin/sh
# Entrypoint del servicio TRANSCRIPTOR: asegura el modelo de whisper en /data y arranca el worker.
#
# El modelo `ggml-large-v3-turbo.bin` (~1.6 GB) NO se bakea en la imagen: se descarga UNA vez al
# volumen /data (persistente entre reinicios). Va EN SEGUNDO PLANO para NO bloquear el arranque del
# servicio ni la cola: el worker arranca ya y las primeras transcripciones degradan con un mensaje
# claro hasta que el .bin esta listo. Descarga ATOMICA (.part -> mv) e idempotente: si falla o el
# contenedor reinicia a medias, reintenta en el siguiente arranque.
set -e

destino="${KENI_WHISPER_MODEL:-/data/models/ggml-large-v3-turbo.bin}"
export KENI_WHISPER_MODEL="$destino"

if [ ! -f "$destino" ]; then
  (
    url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
    mkdir -p "$(dirname "$destino")"
    echo "keni-transcriptor: descargando modelo whisper v3 turbo (~1.6 GB) a $destino…"
    if curl -fSL --retry 3 -o "$destino.part" "$url"; then
      mv "$destino.part" "$destino"
      echo "keni-transcriptor: modelo whisper listo."
    else
      echo "keni-transcriptor: fallo la descarga del modelo whisper; se reintenta al proximo arranque." >&2
      rm -f "$destino.part"
    fi
  ) &
fi

exec "$@"
