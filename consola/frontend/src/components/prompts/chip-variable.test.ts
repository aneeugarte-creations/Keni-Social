/**
 * Round-trip de los chips de variables: el cuerpo se PERSISTE como markdown, así que
 * `{{VARIABLE}}` -> chip -> `{{VARIABLE}}` debe ser EXACTO (sin pérdida ni escapado).
 * Se prueba con un Editor tiptap real (jsdom): mismas extensiones que `EditorWysiwyg`
 * con `conVariables` y que `LectorProsa`.
 */
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { describe, expect, it } from "vitest";

import { ChipVariable } from "./chip-variable";

function crearEditor(contenido: string): Editor {
  return new Editor({
    element: document.createElement("div"),
    extensions: [
      StarterKit,
      Markdown.configure({ html: false, linkify: true, breaks: true }),
      ChipVariable,
    ],
    content: contenido,
  });
}

function aMarkdown(editor: Editor): string {
  const storage = editor.storage as unknown as { markdown: { getMarkdown: () => string } };
  return storage.markdown.getMarkdown();
}

/** Nombres de los nodos chip presentes en el doc (en orden). */
function chips(editor: Editor): string[] {
  const nombres: string[] = [];
  editor.state.doc.descendants((node) => {
    if (node.type.name === "chipVariable") nombres.push(node.attrs.nombre as string);
  });
  return nombres;
}

describe("ChipVariable: round-trip markdown sin pérdida", () => {
  it("convierte {{VAR}} en chip y serializa de vuelta el markdown EXACTO", () => {
    const md = "Escribe un copy para {{MARCA}} en {{RED_SOCIAL}} sobre {{TEMA}}.";
    const editor = crearEditor(md);
    expect(chips(editor)).toEqual(["MARCA", "RED_SOCIAL", "TEMA"]);
    expect(aMarkdown(editor)).toBe(md);
    editor.destroy();
  });

  it("respeta las variables dentro de estructura markdown (títulos y listas)", () => {
    const md = "## Reglas de {{MARCA}}\n\n- usa {{TONO}}\n- evita {{TABU}}";
    const editor = crearEditor(md);
    expect(chips(editor)).toEqual(["MARCA", "TONO", "TABU"]);
    expect(aMarkdown(editor)).toBe(md);
    editor.destroy();
  });

  it("NO chipifica dentro de código (queda literal) y el round-trip se conserva", () => {
    const md = "Plantilla:\n\n```\nHola {{MARCA}}\n```";
    const editor = crearEditor(md);
    expect(chips(editor)).toEqual([]);
    expect(aMarkdown(editor)).toBe(md);
    editor.destroy();
  });

  it("NO chipifica lo que no casa con {{[A-Z_]+}} y lo conserva tal cual", () => {
    const md = "Esto {{minusculas}} y {{con espacios}} no son variables.";
    const editor = crearEditor(md);
    expect(chips(editor)).toEqual([]);
    expect(aMarkdown(editor)).toBe(md);
    editor.destroy();
  });

  it("variables pegadas a puntuación y entre sí sobreviven el viaje", () => {
    const md = "({{MARCA}}/{{RED}}): {{TEMA}}, fin.";
    const editor = crearEditor(md);
    expect(chips(editor)).toEqual(["MARCA", "RED", "TEMA"]);
    expect(aMarkdown(editor)).toBe(md);
    editor.destroy();
  });
});
