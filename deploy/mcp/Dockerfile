# MCP de metricas (keni-metricas) en transporte HTTP (streamable-http en /mcp).
# Es el deployable #3 de ADR 0002: ya era un proceso aparte con su propio contrato.
# Pensado para que clientes Claude del equipo lo consuman por HTTP con bearer
# DELANTE (Traefik). Por defecto arranca con la fuente `muestra` (sin credenciales).
#
# Contexto de build: la RAIZ del repo (ver deploy/docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY keni-shared/ ./keni-shared/
COPY mcp-metricas/ ./mcp-metricas/
RUN pip install ./keni-shared ./mcp-metricas

EXPOSE 8000

# El endpoint /mcp (streamable-http) no responde 200 a un GET simple; comprobamos
# que el puerto acepta conexiones (python ya esta en la imagen).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket;socket.create_connection(('127.0.0.1',8000),2)" || exit 1

CMD ["keni-metricas"]
