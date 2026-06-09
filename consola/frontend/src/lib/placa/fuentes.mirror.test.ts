import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// `fuentes.ts` (navegador, FontFace) declara ser un ESPEJO de `ARCHIVOS` en el `fuentes.mjs` del
// backend (Skia): los MISMOS archivos .ttf deben registrarse en ambos lados, o la previa del editor
// y el render del servidor usarían pesos distintos. Este guard falla si se añade/quita una fuente
// en un solo lado (p. ej. Lato-Black.ttf solo en el front). Cazar la divergencia aquí, no en prod.
describe("espejo del registro de fuentes (front FontFace ↔ back Skia)", () => {
  const aqui = dirname(fileURLToPath(import.meta.url));
  const front = resolve(aqui, "fuentes.ts");
  const back = resolve(
    aqui,
    "../../../../src/keni_consola/motores/estudio_imagen/render_node/fuentes.mjs",
  );

  // Conjunto ordenado de nombres de archivo .ttf citados en un fichero.
  const ttfs = (ruta: string): string[] =>
    [...new Set(readFileSync(ruta, "utf-8").match(/[\w-]+\.ttf/g) ?? [])].sort();

  it("los mismos archivos .ttf se registran en el front y en el backend", () => {
    expect(ttfs(front)).toEqual(ttfs(back));
  });

  it("Lato incluye el peso Black (Lato-Black.ttf), la negra de Claro Sports", () => {
    expect(ttfs(front)).toContain("Lato-Black.ttf");
  });
});
