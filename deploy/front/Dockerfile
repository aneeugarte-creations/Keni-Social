# SPA de la Consola (React + Vite) servido por nginx. Traefik enruta /api al
# gateway (back) y TODO lo demas a este contenedor (fallback SPA -> index.html).
#
# Contexto de build: la RAIZ del repo (ver deploy/docker-compose.yml).

# --- build del bundle ---
FROM node:20-slim AS build
WORKDIR /app
COPY consola/frontend/package.json consola/frontend/package-lock.json ./
RUN npm ci
COPY consola/frontend/ ./
# El "build" del proyecto es `tsc -b && vite build` con outDir vendorizado dentro
# del paquete Python. Aqui queremos el bundle en una ruta limpia y conocida (/spa).
# El deploy se AUTO-VALIDA: corremos `tsc -b` ANTES del bundle para que un error de
# tipos tumbe la imagen (y, por tanto, el deploy) en vez de depender de que el gate
# externo `frontend-build` haya corrido antes. Asi la correccion de tipos no descansa
# en el orden de los pipelines de CI (elimina la posible condicion de carrera).
RUN npx tsc -b && npx vite build --outDir /spa --emptyOutDir

# --- runtime estatico ---
FROM nginx:1.27-alpine
COPY deploy/front/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /spa /usr/share/nginx/html
# 127.0.0.1 (no `localhost`): el busybox wget de alpine intenta ::1 (IPv6) primero
# y nginx solo escucha IPv4 -> falso "connection refused" -> unhealthy -> Traefik
# (que ignora contenedores no-sanos) no enrutaria al front.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:80/ || exit 1
