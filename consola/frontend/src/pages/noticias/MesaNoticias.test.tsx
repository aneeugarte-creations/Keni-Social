/**
 * Tests del agrupamiento por macro-evento en la Mesa (`agruparPorMacro`):
 *   - Sin `tema_macro` → todo suelto, en su orden.
 *   - Macro compartido por ≥2 historias → un grupo anclado en la posición de la primera.
 *   - Macro con UNA sola historia → suelta (no forma grupo redundante).
 *   - El orden de ranking del resto NO se altera.
 */
import { describe, expect, it } from "vitest";

import type { Historia } from "@/types";

import { agruparPorMacro } from "./MesaNoticias";

function historia(id: string, overrides: Partial<Historia> = {}): Historia {
  return {
    id,
    titulo: `Historia ${id}`,
    resumen: "",
    marca: "unotv",
    marca_nombre: "UnoTV",
    categoria: "mx",
    geo: "MX",
    n_items: 1,
    n_fuentes: 1,
    idiomas: ["es"],
    senal: 1,
    score: 0.5,
    breaking: 0,
    primer_visto: "2026-06-05T09:00:00",
    ultimo_visto: "2026-06-05T10:00:00",
    estado: "nuevo",
    publicacion_id: "",
    enlaces: [],
    ...overrides,
  };
}

describe("agruparPorMacro", () => {
  it("sin tema_macro: todas sueltas en orden", () => {
    const bloques = agruparPorMacro([historia("a"), historia("b"), historia("c")]);
    expect(bloques).toHaveLength(3);
    expect(bloques.every((b) => b.tipo === "suelta")).toBe(true);
  });

  it("≥2 historias con el mismo tema_macro forman un grupo en la posición de la primera", () => {
    const bloques = agruparPorMacro([
      historia("a"),
      historia("b", { tema_macro: "Cumbre del G7" }),
      historia("c"),
      historia("d", { tema_macro: "Cumbre del G7" }),
    ]);
    // a (suelta), grupo G7 [b, d] anclado donde apareció b, c (suelta).
    expect(bloques).toHaveLength(3);
    expect(bloques[0]).toMatchObject({ tipo: "suelta" });
    expect(bloques[1].tipo).toBe("grupo");
    const grupo = bloques[1] as { tipo: "grupo"; tema: string; historias: Historia[] };
    expect(grupo.tema).toBe("Cumbre del G7");
    expect(grupo.historias.map((h) => h.id)).toEqual(["b", "d"]);
    expect(bloques[2]).toMatchObject({ tipo: "suelta" });
  });

  it("un macro con UNA sola historia no forma grupo (queda suelta)", () => {
    const bloques = agruparPorMacro([
      historia("a", { tema_macro: "Evento solitario" }),
      historia("b"),
    ]);
    expect(bloques).toHaveLength(2);
    expect(bloques.every((b) => b.tipo === "suelta")).toBe(true);
  });

  it("varios macros distintos cada uno con sus sub-historias", () => {
    const bloques = agruparPorMacro([
      historia("a", { tema_macro: "G7" }),
      historia("b", { tema_macro: "Mundial" }),
      historia("c", { tema_macro: "G7" }),
      historia("d", { tema_macro: "Mundial" }),
    ]);
    expect(bloques).toHaveLength(2);
    expect(bloques.map((b) => (b.tipo === "grupo" ? b.tema : null))).toEqual(["G7", "Mundial"]);
  });

  it("trata el tema_macro en blanco como ausente", () => {
    const bloques = agruparPorMacro([
      historia("a", { tema_macro: "   " }),
      historia("b", { tema_macro: "" }),
    ]);
    expect(bloques.every((b) => b.tipo === "suelta")).toBe(true);
  });
});
