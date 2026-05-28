# Despliegue local por persona

El MCP corre en la máquina/entorno de cada persona. Aquí están las formas de instalarlo, pensadas para **máquinas corporativas bloqueadas** (sin permisos de admin). La alternativa —un MCP **alojado por Keni** por HTTP (System User tokens, OAuth centralizado)— está en `despliegue-hosted.md`; ambos modos conviven (arquitectura híbrida).

> **Consola Keni en local:** la operacional de la consola (tareas, comercial, rota, usuarios, sesiones, cola de jobs) vive en **Postgres** (ADR 0004; ya no SQLite). Para arrancar `keni-consola` en la máquina hace falta un Postgres y `DATABASE_URL`. El monorepo trae un compose dev de un comando:
>
> ```bash
> docker compose -f deploy/dev/docker-compose.yml up -d
> export DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/keni_social
> ```
>
> El Postgres queda atado a `127.0.0.1` (no expuesto a la red); la privacidad del perfil local se preserva (ningún dato sale de la máquina). El MCP de métricas y su histórico SQLite local son otro almacén distinto y no se ven afectados.

## Opción 1 — `uv` (recomendada, sin admin)

`uv`/`uvx` se instala en espacio de usuario (no requiere admin):

```bash
# instalar uv una vez (espacio de usuario)
curl -LsSf https://astral.sh/uv/install.sh | sh

# correr el MCP directamente desde el repo (keni-shared es dependencia local)
uvx --with /ruta/a/keni-social/keni-shared --from /ruta/a/keni-social/mcp-metricas keni-metricas

# registrarlo en Claude Code
claude mcp add keni-metricas -- uvx --with /ruta/a/keni-social/keni-shared --from /ruta/a/keni-social/mcp-metricas keni-metricas
```

## Opción 2 — entorno virtual

```bash
cd /ruta/a/keni-social
python3 -m venv .venv
.venv/bin/pip install -e ./keni-shared   # dependencia local (no está en PyPI)
.venv/bin/pip install -e ./mcp-metricas
claude mcp add keni-metricas -- /ruta/a/keni-social/.venv/bin/keni-metricas
```

O en `.mcp.json` del proyecto:

```json
{
  "mcpServers": {
    "keni-metricas": {
      "command": "/ruta/a/keni-social/mcp-metricas/.venv/bin/keni-metricas",
      "env": { "KENI_METRICAS_FUENTE": "muestra" }
    }
  }
}
```

## Opción 3 — Claude Code en la nube de Keni (máquina muy bloqueada)

Quien no pueda instalar nada localmente usa el Claude Code en la nube de Keni desde el navegador, con el MCP corriendo **dentro de su propio entorno** en ese servidor (mismo comando que la opción 1/2). Las credenciales siguen siendo **por persona** dentro de su entorno.

## Configuración

- Por defecto (`fuente = "muestra"`) no hace falta configurar nada.
- Para datos reales: `~/.config/keni-metricas/config.toml` (ver `docs/credenciales.md`). Variables útiles:
  - `KENI_METRICAS_FUENTE=muestra|real`
  - `KENI_METRICAS_CONFIG=/ruta/al/config.toml`

## Comprobar que funciona

```bash
claude mcp list                      # debe aparecer keni-metricas
# en una sesión de Claude:
> usa listar_cuentas
> usa metricas_resumen con cuenta claro_sports y rango semana
```

## Transcripción local (skill `clip-a-copy`)

La skill `clip-a-copy` (video/audio → copy) transcribe **en la máquina**, sin nube: el audio no sale del equipo. Necesita tres cosas en un Mac (Apple Silicon):

```bash
# 1) whisper.cpp (motor de transcripción) y ffmpeg (extrae el audio)
brew install whisper-cpp ffmpeg

# 2) el modelo large-v3-turbo en español (~1.6 GB), una sola vez
mkdir -p ~/models
curl -L -o ~/models/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

# 3) comprobar
whisper-cli --help >/dev/null && echo "whisper-cli ok"
```

El script `skills-copy/.claude/skills/clip-a-copy/transcribir.sh` busca el modelo en `KENI_WHISPER_MODEL`, luego en `~/models/` y `~/.cache/whisper/`. Velocidad de referencia: en un M4 de 16 GB, `large-v3-turbo` transcribe **mucho más rápido que tiempo real** (un podcast de 1 h tarda unos minutos). Hay Macs del equipo con 24 GB y un Mac Studio, que pueden hacer de "caja de transcripción" compartida si hiciera falta.

Ensayo rápido sin video real:

```bash
cd skills-copy/ejemplos && bash generar-clip-prueba.sh
# luego, en una sesión de Claude desde skills-copy/:
> usa clip-a-copy con /tmp/keni-clip/declaracion.m4a para claro-sports
```

> **Máquinas de community bloqueadas:** si no pueden instalar Homebrew, la transcripción se corre en un Mac con permisos (el de la persona de datos, o el Mac Studio como caja compartida) y el copy se redacta a partir del `.txt`/`.srt` resultante.
