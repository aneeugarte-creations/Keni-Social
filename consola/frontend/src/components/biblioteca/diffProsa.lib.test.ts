/**
 * Helpers del diff de prosa: proyección de markdown a texto plano legible (sin frontmatter,
 * sin markup crudo, whitespace normalizado) conservando las variables `{{VARIABLE}}`.
 */
import { describe, expect, it } from "vitest";

import { aProsaPlana, esSoloEspacios, quitarFrontmatter } from "./diffProsa.lib";

describe("quitarFrontmatter", () => {
  it("quita el bloque YAML inicial `---...---`", () => {
    const texto = "---\ntitulo: Hola\ntags: [a, b]\n---\nCuerpo real.";
    expect(quitarFrontmatter(texto)).toBe("Cuerpo real.");
  });

  it("no toca texto sin frontmatter", () => {
    expect(quitarFrontmatter("Solo cuerpo.")).toBe("Solo cuerpo.");
  });

  it("no confunde un `---` interior (regla horizontal) con frontmatter", () => {
    const texto = "Intro.\n\n---\n\nMas texto.";
    expect(quitarFrontmatter(texto)).toBe(texto);
  });
});

describe("aProsaPlana", () => {
  it("quita encabezados, negrita y citas (nada de markdown crudo)", () => {
    const md = "## Titular\n\n**Importante**: revisa.\n\n> una cita";
    const plano = aProsaPlana(md);
    expect(plano).not.toMatch(/[#*>]/);
    expect(plano).toContain("Titular");
    expect(plano).toContain("Importante: revisa.");
    expect(plano).toContain("una cita");
  });

  it("normaliza viñetas `*` y `-` al mismo marcador (sin diff fantasma)", () => {
    expect(aProsaPlana("* uno\n* dos")).toBe(aProsaPlana("- uno\n- dos"));
  });

  it("convierte enlaces a su texto visible", () => {
    expect(aProsaPlana("Ver [la guía](https://x.io/y)")).toBe("Ver la guía");
  });

  it("quita el frontmatter antes de limpiar", () => {
    const md = "---\nslug: x\n---\n# Hola";
    expect(aProsaPlana(md)).toBe("Hola");
  });

  it("conserva las variables `{{VAR}}` intactas (incluido `_`)", () => {
    expect(aProsaPlana("Habla de {{MARCA_X}} hoy")).toContain("{{MARCA_X}}");
  });

  it("colapsa espacios sobrantes y limita líneas en blanco", () => {
    expect(aProsaPlana("hola    mundo")).toBe("hola mundo");
    expect(aProsaPlana("a\n\n\n\nb")).toBe("a\n\nb");
  });
});

describe("esSoloEspacios", () => {
  it("detecta fragmentos de puro whitespace", () => {
    expect(esSoloEspacios(" ")).toBe(true);
    expect(esSoloEspacios("\n\n")).toBe(true);
    expect(esSoloEspacios("x")).toBe(false);
    expect(esSoloEspacios("")).toBe(false);
  });
});
