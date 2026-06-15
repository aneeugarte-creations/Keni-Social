/**
 * `desescaparMarkdown`: quita el backslash espurio que tiptap-markdown antepone a la
 * puntuación escapable de CommonMark al serializar, para persistir markdown canónico.
 */
import { describe, expect, it } from "vitest";

import { desescaparMarkdown } from "./EditorWysiwyg";

describe("desescaparMarkdown", () => {
  it("desescapa la puntuación escapable de CommonMark", () => {
    expect(desescaparMarkdown("\\[")).toBe("[");
    expect(desescaparMarkdown("\\]")).toBe("]");
    expect(desescaparMarkdown("\\`")).toBe("`");
    expect(desescaparMarkdown("\\*")).toBe("*");
    expect(desescaparMarkdown("\\_")).toBe("_");
    expect(desescaparMarkdown("\\#")).toBe("#");
    expect(desescaparMarkdown("\\>")).toBe(">");
    expect(desescaparMarkdown("\\|")).toBe("|");
    expect(desescaparMarkdown("\\~")).toBe("~");
  });

  it("desescapa el propio backslash (`\\\\` -> `\\`)", () => {
    expect(desescaparMarkdown("\\\\")).toBe("\\");
  });

  it("es idempotente (aplicarlo dos veces = una)", () => {
    const escapado = '\\[\\["id1","id2"\\]\\]';
    const una = desescaparMarkdown(escapado);
    const dos = desescaparMarkdown(una);
    expect(una).toBe('[["id1","id2"]]');
    expect(dos).toBe(una);
  });

  it("deja intacto el texto sin escapes", () => {
    const limpio = 'Un párrafo con JSON {"grupos": [["id1","id2"]]} y nada más.';
    expect(desescaparMarkdown(limpio)).toBe(limpio);
  });

  it("no toca los saltos de línea ni la estructura de listas", () => {
    const md = "- uno\n- dos\n\nPárrafo.";
    expect(desescaparMarkdown(md)).toBe(md);
    expect(desescaparMarkdown("a\nb")).toBe("a\nb");
  });

  it("desescapa un párrafo real con JSON y fences (caso del usuario)", () => {
    const escapado =
      'Config: `{"grupos": \\[\\["id1","id2"\\]\\]}`\n\n\\`\\`\\`json\n{ "x": 1 }\n\\`\\`\\`';
    const esperado = 'Config: `{"grupos": [["id1","id2"]]}`\n\n```json\n{ "x": 1 }\n```';
    expect(desescaparMarkdown(escapado)).toBe(esperado);
  });
});
