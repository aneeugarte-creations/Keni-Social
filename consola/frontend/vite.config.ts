/// <reference types="vitest/config" />
import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// La Consola Keni se sirve desde el mismo origen que el backend Starlette local
// (127.0.0.1:8765). En produccion el bundle vive dentro del paquete Python en
// `src/keni_consola/webapp/`; por eso `outDir` apunta alli y `base` es "/".
// En `npm run dev` proxeamos `/api` al backend para desarrollar contra datos reales.
export default defineConfig({
  plugins: [react()],
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
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
