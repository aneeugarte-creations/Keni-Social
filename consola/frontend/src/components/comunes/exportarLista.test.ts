import { describe, expect, it } from "vitest";

import {
  construirMarkdownLista,
  nombreArchivoLista,
  type ItemExportable,
} from "./exportarLista";

/**
 * Tests de los helpers PUROS de exportación de listas (tendencias / plan del día).
 * Cubren el armado del Markdown copiar-pegar y el slug del nombre de fichero.
 */
describe("construirMarkdownLista", () => {
  it("incluye el título de sección como encabezado", () => {
    const md = construirMarkdownLista("Tendencias", []);
    expect(md.startsWith("# Tendencias")).toBe(true);
  });

  it("avisa cuando la lista está vacía", () => {
    expect(construirMarkdownLista("X", [])).toContain("_Sin elementos._");
  });

  it("numera los ítems y pone el título en negrita", () => {
    const items: ItemExportable[] = [{ titulo: "Liga MX" }, { titulo: "Eurocopa" }];
    const md = construirMarkdownLista("Tendencias", items);
    expect(md).toContain("1. **Liga MX**");
    expect(md).toContain("2. **Eurocopa**");
  });

  it("añade señal y fuentes como meta entre paréntesis", () => {
    const items: ItemExportable[] = [
      { titulo: "Liga MX", senal: "50 mil+", fuentes: ["Google Trends", "ESPN"] },
    ];
    const md = construirMarkdownLista("T", items);
    expect(md).toContain("**Liga MX** _(50 mil+ · Google Trends, ESPN)_");
  });

  it("renderiza enlaces como Markdown con su medio", () => {
    const items: ItemExportable[] = [
      {
        titulo: "Final",
        enlaces: [{ titulo: "Crónica", url: "https://e.com/x", fuente: "ESPN" }],
      },
    ];
    const md = construirMarkdownLista("T", items);
    expect(md).toContain("- [Crónica](https://e.com/x) — ESPN");
  });

  it("usa la URL como etiqueta si el enlace no trae título", () => {
    const items: ItemExportable[] = [
      { titulo: "Tema", enlaces: [{ titulo: "", url: "https://e.com/y" }] },
    ];
    const md = construirMarkdownLista("T", items);
    expect(md).toContain("- [https://e.com/y](https://e.com/y)");
  });

  it("rinde enlaces sin URL como texto plano", () => {
    const items: ItemExportable[] = [
      { titulo: "Tema", enlaces: [{ titulo: "Solo título", url: "" }] },
    ];
    const md = construirMarkdownLista("T", items);
    expect(md).toContain("- Solo título");
    expect(md).not.toContain("](");
  });

  it("es determinista (misma entrada => misma salida)", () => {
    const items: ItemExportable[] = [{ titulo: "A", porQue: "porque sí" }];
    expect(construirMarkdownLista("T", items)).toBe(construirMarkdownLista("T", items));
  });
});

describe("nombreArchivoLista", () => {
  it("genera un slug ascii con la fecha de hoy y extensión .txt", () => {
    const nombre = nombreArchivoLista("Plan del día");
    expect(nombre).toMatch(/^plan-del-dia-\d{4}-\d{2}-\d{2}\.txt$/);
  });

  it("cae a 'lista' si el título no deja caracteres válidos", () => {
    expect(nombreArchivoLista("¿!¡?")).toMatch(/^lista-\d{4}-\d{2}-\d{2}\.txt$/);
  });
});
