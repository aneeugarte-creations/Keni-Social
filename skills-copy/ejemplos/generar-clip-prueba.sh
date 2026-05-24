#!/usr/bin/env bash
# Genera un clip de audio de prueba (sin binarios en el repo) para ensayar la
# skill clip-a-copy. Usa la voz mexicana de macOS (`say`) + ffmpeg.
#
#   bash generar-clip-prueba.sh            # crea /tmp/keni-clip/declaracion.m4a
#   bash generar-clip-prueba.sh salida.m4a # ruta a elección
#
# Luego:
#   bash ../.claude/skills/clip-a-copy/transcribir.sh /tmp/keni-clip/declaracion.m4a
# o pídele a Claude: "usa clip-a-copy con /tmp/keni-clip/declaracion.m4a para claro-sports".
set -euo pipefail

SALIDA="${1:-/tmp/keni-clip/declaracion.m4a}"
mkdir -p "$(dirname "$SALIDA")"

TXT='Fue un partido muy complicado, la verdad. En el primer tiempo nos costó entrar al juego, pero el equipo nunca dejó de creer. El gol del empate al minuto ochenta y ocho nos cambió todo. Le dedico este triunfo a la afición que siempre nos apoya. Ahora pensamos en la final, vamos a darlo todo.'

# voz mexicana si está disponible
VOZ="$(say -v '?' 2>/dev/null | awk -F'  ' '/es_MX/{print $1; exit}')"
aiff="$(mktemp -t clip).aiff"
if [ -n "$VOZ" ]; then say -v "$VOZ" -o "$aiff" "$TXT"; else say -o "$aiff" "$TXT"; fi
ffmpeg -nostdin -loglevel error -y -i "$aiff" -c:a aac "$SALIDA"
rm -f "$aiff"
echo "Clip de prueba: $SALIDA  (voz: ${VOZ:-default})"
echo "Nota: es voz sintética; whisper cometerá errores de ASR a propósito útiles para probar la verificación."
