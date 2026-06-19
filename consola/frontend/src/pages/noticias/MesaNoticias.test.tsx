/**
 * Tests del agrupamiento por macro-evento en la Mesa (`agruparPorMacro`):
 *   - Sin `tema_macro` → todo suelto, en su orden.
 *   - Macro compartido por ≥2 historias → un grupo (caja con sub-encabezado) anclado en la
 *     posición de la primera.
 *   - Macro con UNA sola historia → suelta: tarjeta normal, sin caja (y, sin badge suelto en
 *     la tarjeta, sin ninguna marca visual de macro-evento).
 *   - El orden de ranking del resto NO se altera.
 */
import { describe, expect, it } from "vitest";

import type { Historia } from "@/types";

import { agruparPorMacro, historiasDelGrupo } from "./MesaNoticias";

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

  it("un macro con UNA sola historia no forma caja: queda suelta (tarjeta normal, sin grupo)", () => {
    const bloques = agruparPorMacro([
      historia("a", { tema_macro: "Evento solitario" }),
      historia("b"),
    ]);
    expect(bloques).toHaveLength(2);
    // Sin hermanas en la sección NO se crea ningún bloque "grupo" para el macro-evento:
    // la historia con tema_macro se pinta como una tarjeta suelta más (sin caja).
    expect(bloques.every((b) => b.tipo === "suelta")).toBe(true);
    expect(bloques.some((b) => b.tipo === "grupo")).toBe(false);
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

describe("historiasDelGrupo", () => {
  const lista = [
    historia("a", { grupo: "Fútbol" }),
    historia("b", { grupo: "Motor" }),
    historia("c", { grupo: "Fútbol" }),
    historia("d", { grupo: "" }),
  ];

  it("'' (Todas) no filtra: devuelve todas en orden", () => {
    expect(historiasDelGrupo(lista, "").map((h) => h.id)).toEqual(["a", "b", "c", "d"]);
  });

  it("un grupo concreto deja solo sus candidatas, conservando el orden", () => {
    expect(historiasDelGrupo(lista, "Fútbol").map((h) => h.id)).toEqual(["a", "c"]);
    expect(historiasDelGrupo(lista, "Motor").map((h) => h.id)).toEqual(["b"]);
  });

  it("un grupo sin candidatas devuelve lista vacía", () => {
    expect(historiasDelGrupo(lista, "Boxeo")).toEqual([]);
  });
});
