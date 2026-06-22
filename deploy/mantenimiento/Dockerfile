# Página de mantenimiento de keni-social (red de seguridad del deploy). Sirve un cascarón de la
# Consola CONGELADO que es PÍXEL-IDÉNTICO a la app: se hornea del MISMO frontend (entry
# `mantenimiento.html`, ver consola/frontend/vite.config.ts), reutilizando los componentes reales
# (Sidebar data-driven, primitivas) y el CSS compilado (Tailwind). Así no es una réplica que
# derive del diseño real, sino el propio shell.
#
# Lo sirve un contenedor APARTE (no el front), siempre vivo, para cubrir la ventana en que el
# front se recrea/cae (su router Traefik desaparece): el router catch-all del file-provider cae a
# este servicio y devuelve la página en vez de un 404. Su VERSIÓN es un hash de consola/frontend +
# deploy/mantenimiento (ver deploy.sh): se reconstruye cuando cambia el shell, en sincronía con él.
#
# Contexto de build: la RAÍZ del repo (ver deploy/docker-compose.yml).

# --- build del bundle (emite también mantenimiento.html + sus assets) ---
FROM node:20-slim AS build
WORKDIR /app
COPY consola/frontend/package.json consola/frontend/package-lock.json ./
RUN npm ci
COPY consola/frontend/ ./
# `tsc -b` antes del bundle: un error de tipos tumba la imagen (y el deploy), igual que el front.
# vite build (multi-página) deja index.html + mantenimiento.html + /assets en /spa.
RUN npx tsc -b && npx vite build --outDir /spa --emptyOutDir

# --- runtime estatico (nginx NO-ROOT) ---
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY deploy/mantenimiento/nginx.conf /etc/nginx/conf.d/default.conf
# El bundle entero: mantenimiento.html (cuerpo del 503) + /assets (JS/CSS que la página carga,
# servidos 200). index.html viene también pero nginx nunca lo sirve (el catch-all da mantenimiento).
COPY --from=build /spa /usr/share/nginx/html
# 127.0.0.1 (no `localhost`): el busybox wget de alpine intenta ::1 (IPv6) primero y nginx solo
# escucha IPv4 -> falso "connection refused" -> unhealthy -> Traefik no enrutaría la red de
# seguridad a este contenedor. /healthz responde 200 (el resto de rutas dan 503 a propósito).
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
