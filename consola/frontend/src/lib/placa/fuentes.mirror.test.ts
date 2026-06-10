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

  // Montserrat = el equivalente OFL de la Gotham de los titulares deportivos de Claro Sports:
  // la versión titular (ExtraBold 800 / Black 900) y la Light 300 deben existir como caras
  // ESTÁTICAS reales en ambos lados (con sus itálicas, por el botón I).
  it("Montserrat incluye Light (300), ExtraBold (800) y Black (900) con sus itálicas", () => {
    for (const cara of [
      "Montserrat-Light.ttf",
      "Montserrat-ExtraBold.ttf",
      "Montserrat-Black.ttf",
      "Montserrat-LightItalic.ttf",
      "Montserrat-ExtraBoldItalic.ttf",
      "Montserrat-BlackItalic.ttf",
    ]) {
      expect(ttfs(front)).toContain(cara);
    }
  });

  // Skia (@napi-rs/canvas) NO instancia el eje `wght` de un TTF variable: lo registra como UNA
  // sola cara (la instancia por defecto) y pedir `300 …px` o `900 …px` pinta siempre lo mismo.
  // Por eso el catálogo solo admite caras ESTÁTICAS (un TTF por peso). Si esto falla, alguien
  // volvió a registrar una *-Variable.ttf: el export ignoraría el peso elegido en el editor.
  it("ninguna cara registrada es un TTF variable (Skia no instancia el eje wght)", () => {
    expect(ttfs(front).filter((t) => t.includes("Variable"))).toEqual([]);
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

// Las WEBFONTS del lienzo Konva (index.html) deben cubrir, por familia, EXACTAMENTE las caras
// (peso × estilo) que registran fuentes.ts (placa en navegador) y Skia en el servidor: el lienzo
// pinta el peso numérico real de la capa (`estiloFuente` en tipografia.ts) y el font-matching del
// navegador solo resuelve igual que Skia si ambos parten del MISMO juego de caras. Un peso de más
// enseñaría en la previa una cara que el export no tiene (p. ej. el Barlow 800 que se cargaba
// antes); uno de menos haría que el mismo peso resolviera a caras distintas en cada lado (p. ej.
// Montserrat Black 900 sin webfont caía a 800 en la previa).
describe("espejo de webfonts del lienzo Konva (index.html ↔ caras registradas)", () => {
  const aqui = dirname(fileURLToPath(import.meta.url));
  const srcFuentes = readFileSync(resolve(aqui, "fuentes.ts"), "utf-8");
  const html = readFileSync(resolve(aqui, "../../../index.html"), "utf-8");

  // Caras registradas, por familia: "<0|1>,<peso>" (0 = normal, 1 = italic; el formato de css2).
  const registradas = new Map<string, Set<string>>();
  for (const m of srcFuentes.matchAll(
    /\{ familia: "([^"]+)", archivo: "[^"]+", peso: "(\d+)"(, estilo: "italic")? \}/g,
  )) {
    const [, familia, peso, italic] = m;
    if (!registradas.has(familia)) registradas.set(familia, new Set());
    registradas.get(familia)!.add(`${italic ? 1 : 0},${peso}`);
  }

  // Webfonts del catálogo: la URL css2 que carga las familias del editor (no la de Geist).
  const url = (html.match(/href="(https:\/\/fonts\.googleapis\.com\/css2\?[^"]*Barlow[^"]*)"/) ?? [])[1];

  // Tuplas pedidas a Google, por familia. Formatos css2: "Familia" (una cara 400 normal),
  // "Familia:wght@400;700" (pesos normales) y "Familia:ital,wght@0,400;1,700" (eje itálica).
  const webfonts = new Map<string, Set<string>>();
  for (const cruda of new URL(url!).searchParams.getAll("family")) {
    const [nombre, ejes] = cruda.split(":");
    const caras = new Set<string>();
    if (!ejes) caras.add("0,400");
    else if (ejes.startsWith("ital,wght@")) for (const t of ejes.slice(10).split(";")) caras.add(t);
    else if (ejes.startsWith("wght@")) for (const t of ejes.slice(5).split(";")) caras.add(`0,${t}`);
    webfonts.set(nombre, caras);
  }

  it("la URL de webfonts del catálogo existe en index.html", () => {
    expect(url).toBeTruthy();
  });

  it("las webfonts cargan las MISMAS familias que fuentes.ts", () => {
    expect([...webfonts.keys()].sort()).toEqual([...registradas.keys()].sort());
  });

  it("cada familia carga EXACTAMENTE las caras (peso × estilo) registradas en fuentes.ts", () => {
    for (const [familia, caras] of registradas) {
      expect([...(webfonts.get(familia) ?? [])].sort(), familia).toEqual([...caras].sort());
    }
  });
});
