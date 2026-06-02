import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// `dibujar.mjs` (frontend) es un ESPEJO BYTE A BYTE del motor de render del backend, para que la
// previa en vivo del editor coincida EXACTAMENTE con lo que compone el servidor (auto-gen). Este
// guard falla si divergen: al tocar el render hay que actualizar AMBOS (copiar el del backend).
describe("espejo del render de placa", () => {
  const aqui = dirname(fileURLToPath(import.meta.url));
  const espejo = resolve(aqui, "dibujar.mjs");
  const original = resolve(
    aqui,
    "../../../../src/keni_consola/motores/estudio_imagen/render_node/dibujar.mjs",
  );

  it("dibujar.mjs del front es idéntico al del backend (render_node)", () => {
    const a = readFileSync(espejo, "utf-8");
    const b = readFileSync(original, "utf-8");
    expect(a).toBe(b);
  });
});
