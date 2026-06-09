/// <reference types="vitest/config" />
import { writeFileSync } from "node:fs";
import path from "node:path";

import react from "@vitejs/plugin-react";
import { type Plugin, type ProxyOptions, defineConfig } from "vite";

// Identificador único de ESTE build. Cambia en cada `vite build` (cada deploy), así el
// SPA en una pestaña vieja detecta que hay una versión nueva comparando su `__BUILD_ID__`
// (horneado en el bundle) con `/version.json` (servido por nginx, `no-store`). Override
// opcional con VITE_BUILD_ID (p. ej. el commit en CI).
const BUILD_ID = process.env.VITE_BUILD_ID || String(Date.now());

/**
 * Escribe `version.json` (`{ "buildId": ... }`) en el outDir tras el bundle, con el MISMO
 * id que se hornea en el código. Es el "endpoint" barato de versión del front (sin backend):
 * `lib/version.ts` lo consulta para recargar sola tras un deploy. Solo en build.
 */
function pluginVersionJson(buildId: string): Plugin {
  let outDir = "dist";
  return {
    name: "keni-version-json",
    apply: "build",
    configResolved(cfg) {
      outDir = cfg.build.outDir;
    },
    closeBundle() {
      try {
        writeFileSync(path.join(outDir, "version.json"), `${JSON.stringify({ buildId })}\n`);
      } catch {
        // No romper el build por no poder escribir el manifiesto de versión.
      }
    },
  };
}

// La Consola Keni se sirve desde el mismo origen que el backend Starlette local
// (127.0.0.1:8765). En produccion el bundle vive dentro del paquete Python en
// `src/keni_consola/webapp/`; por eso `outDir` apunta alli y `base` es "/".
// En `npm run dev` proxeamos `/api` al backend para desarrollar contra datos reales.
export default defineConfig({
  plugins: [react(), pluginVersionJson(BUILD_ID)],
  // Horneado del id de build para que el bundle sepa qué versión ES (lo compara con
  // `/version.json`). En `vite serve` (dev) vale igual, pero el detector lo ignora.
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  base: "/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "../src/keni_consola/webapp",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      // Por defecto proxeamos `/api` al backend Starlette LOCAL (127.0.0.1:8765).
      // Para desarrollar el front contra un backend REMOTO (p. ej. el hosted
      // `https://social.kenitech.io`, que YA tiene Postgres y datos reales) sin
      // levantar Postgres en local, exporta `VITE_API_TARGET` al arrancar:
      //   VITE_API_TARGET=https://social.kenitech.io npm run dev
      // Cuando el target es remoto reescribimos el dominio de la cookie de sesión
      // a localhost y las cabeceras Origin/Referer al host remoto (por si el back
      // valida CSRF). Esto es SOLO para dev; no afecta al build de producción.
      "/api": ((): ProxyOptions => {
        const target = process.env.VITE_API_TARGET || "http://127.0.0.1:8765";
        const esRemoto = /^https:\/\//.test(target);
        const opciones: ProxyOptions = {
          target,
          changeOrigin: true,
          secure: esRemoto,
          cookieDomainRewrite: esRemoto ? "" : undefined,
        };
        if (esRemoto) {
          // Reescribe Origin/Referer al host remoto (por si el backend valida CSRF).
          opciones.configure = (proxy) => {
            proxy.on("proxyReq", (proxyReq) => {
              proxyReq.setHeader("origin", target);
              proxyReq.setHeader("referer", `${target}/`);
            });
          };
        }
        return opciones;
      })(),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
