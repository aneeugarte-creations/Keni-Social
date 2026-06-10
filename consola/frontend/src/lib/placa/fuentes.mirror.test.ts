import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { FAMILIAS_CON_CURSIVA } from "./dibujar.mjs";

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

  // CURSIVA real end-to-end: cada familia de FAMILIAS_CON_CURSIVA (dibujar.mjs, la lista que
  // habilita el botón del editor) debe registrar una cara *Italic* en AMBOS lados. Si este guard
  // falla, el editor ofrecería una cursiva que el export no puede pintar (o al revés).
  it("cada familia con cursiva registra su cara itálica en el front y en el backend", () => {
    const srcFront = readFileSync(front, "utf-8");
    const srcBack = readFileSync(back, "utf-8");
    const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    for (const familia of FAMILIAS_CON_CURSIVA) {
      // Front (fuentes.ts): { familia: "X", archivo: "...Italic....ttf", …, estilo: "italic" }.
      expect(srcFront).toMatch(new RegExp(`familia: "${esc(familia)}", archivo: "[\\w-]*Italic[\\w-]*\\.ttf"`));
      // Back (fuentes.mjs): ["X", "...Italic....ttf"].
      expect(srcBack).toMatch(new RegExp(`\\["${esc(familia)}", "[\\w-]*Italic[\\w-]*\\.ttf"\\]`));
    }
  });
});
