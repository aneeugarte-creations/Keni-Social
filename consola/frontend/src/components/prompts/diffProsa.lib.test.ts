/**
 * Helpers del diff de prosa: proyección de markdown a texto plano legible (sin frontmatter,
 * sin markup crudo, whitespace normalizado) conservando las variables `{{VARIABLE}}`.
 */
import { describe, expect, it } from "vitest";

import {
  aProsaPlana,
  desescaparMarkdown,
  esSoloEspacios,
  normalizarEspacios,
  quitarFrontmatter,
} from "./diffProsa.lib";

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

  it("elimina los fences ``` conservando el contenido del bloque", () => {
    const md = "Ejemplo:\n\n```json\n{ \"a\": 1 }\n```\n\nFin.";
    const plano = aProsaPlana(md);
    expect(plano).not.toContain("```");
    expect(plano).toContain("Ejemplo:");
    expect(plano).toContain('{ "a": 1 }');
    expect(plano).toContain("Fin.");
  });

  it("limpia los pipes de tabla y borra la fila separadora", () => {
    const md = "| Col A | Col B |\n| --- | --- |\n| uno | dos |";
    const plano = aProsaPlana(md);
    expect(plano).not.toContain("|");
    expect(plano).not.toMatch(/---/);
    expect(plano).toContain("Col A");
    expect(plano).toContain("Col B");
    expect(plano).toContain("uno");
    expect(plano).toContain("dos");
  });

  it("quita el hard-break por backslash al final de línea", () => {
    const plano = aProsaPlana("primera línea\\\nsegunda línea");
    expect(plano).not.toContain("\\");
    expect(plano).toContain("primera línea");
    expect(plano).toContain("segunda línea");
  });

  it("convierte autolinks `<https://...>` a su URL (sin `<` ni `>`)", () => {
    const plano = aProsaPlana("Más en <https://keni.io/guia> ahora");
    expect(plano).not.toMatch(/[<>]/);
    expect(plano).toContain("https://keni.io/guia");
  });

  it("elimina tags HTML inline simples (`<br>`, `<sub>`)", () => {
    const plano = aProsaPlana("Texto<br>con un <sub>índice</sub> aquí");
    expect(plano).not.toMatch(/[<>]/);
    expect(plano).toContain("índice");
  });

  it("no genera diff fantasma entre markdown canónico y sobre-escapado (JSON con corchetes)", () => {
    const canonico = 'Config {"grupos": [["id1","id2"]]} final.';
    const sobreEscapado = 'Config {"grupos": \\[\\["id1","id2"\\]\\]} final.';
    expect(aProsaPlana(sobreEscapado)).toBe(aProsaPlana(canonico));
  });

  it("trata igual un fence ```json y su versión sobre-escapada", () => {
    const canonico = "Ejemplo:\n\n```json\n{ \"a\": 1 }\n```\n\nFin.";
    const sobreEscapado = "Ejemplo:\n\n\\`\\`\\`json\n{ \"a\": 1 }\n\\`\\`\\`\n\nFin.";
    expect(aProsaPlana(sobreEscapado)).toBe(aProsaPlana(canonico));
  });
});

describe("desescaparMarkdown (defensa en el diff)", () => {
  it("quita el backslash espurio y es idempotente", () => {
    expect(desescaparMarkdown('\\[\\["id1"\\]\\]')).toBe('[["id1"]]');
    const una = desescaparMarkdown('\\`\\`\\`json');
    expect(una).toBe("```json");
    expect(desescaparMarkdown(una)).toBe(una);
  });

  it("no toca los saltos de línea", () => {
    expect(desescaparMarkdown("a\nb\n\nc")).toBe("a\nb\n\nc");
  });
});

describe("normalizarEspacios", () => {
  it("conserva el markup pero quita frontmatter y colapsa espacios", () => {
    expect(normalizarEspacios("---\nx: 1\n---\n**Hola**   mundo")).toBe("**Hola** mundo");
  });

  it("da el mismo resultado si solo cambia el whitespace", () => {
    expect(normalizarEspacios("Hola   mundo.")).toBe(normalizarEspacios("Hola mundo."));
  });

  it("difiere cuando cambia el markup (negrita)", () => {
    expect(normalizarEspacios("Hola mundo.")).not.toBe(normalizarEspacios("**Hola** mundo."));
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
