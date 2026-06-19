/**
 * Tests del agrupamiento por macro-evento en la Mesa (`agruparPorMacro`):
 *   - Sin `tema_macro` → todo suelto, en su orden.
 *   - Macro compartido por ≥2 historias → un grupo (caja con sub-encabezado) anclado en la
 *     posición de la primera.
 *   - Macro con UNA sola historia → suelta: tarjeta normal, sin caja (y, sin badge suelto en
 *     la tarjeta, sin ninguna marca visual de macro-evento).
 *   - El orden de ranking del resto NO se altera.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { GrupoMesa, Historia, MesaLinea } from "@/types";

import {
  agruparPorMacro,
  chipsDeLineas,
  historiasDelGrupo,
  NavGruposLineas,
} from "./MesaNoticias";

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
    historia("a", { grupo: "Fútbol", linea: "fut-mundial" }),
    historia("b", { grupo: "Motor", linea: "mot-f1" }),
    historia("c", { grupo: "Fútbol", linea: "fut-liga-mx" }),
    historia("d", { grupo: "", linea: "" }),
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

  it("una línea afina dentro del grupo (2º nivel)", () => {
    expect(historiasDelGrupo(lista, "Fútbol", "fut-mundial").map((h) => h.id)).toEqual(["a"]);
    expect(historiasDelGrupo(lista, "Fútbol", "fut-liga-mx").map((h) => h.id)).toEqual(["c"]);
  });

  it("una línea sin candidatas en el grupo devuelve lista vacía", () => {
    expect(historiasDelGrupo(lista, "Fútbol", "fut-bundesliga")).toEqual([]);
  });
});

describe("NavGruposLineas", () => {
  const grupos: GrupoMesa[] = [
    {
      grupo: "Fútbol",
      en_pool: 3,
      lineas: [
        { linea: "fut-mundial", nombre: "Mundial", en_pool: 2 },
        { linea: "fut-liga-mx", nombre: "Liga MX", en_pool: 1 },
        { linea: "fut-bundesliga", nombre: "Bundesliga", en_pool: 0 },
      ],
    },
    { grupo: "Motor", en_pool: 1, lineas: [{ linea: "mot-f1", nombre: "F1", en_pool: 1 }] },
  ];

  it("pulsar un grupo lo selecciona y despliega sus líneas (2º nivel)", () => {
    const onSelGrupo = vi.fn();
    render(
      <NavGruposLineas
        grupos={grupos}
        total={4}
        grupoSel=""
        lineaSel=""
        onSelGrupo={onSelGrupo}
        onSelLinea={vi.fn()}
      />,
    );
    // Cerrado: el menú no está en el DOM.
    expect(screen.queryByTestId("menu-lineas-Fútbol")).toBeNull();
    fireEvent.click(screen.getByTestId("chip-grupo-Fútbol"));
    expect(onSelGrupo).toHaveBeenCalledWith("Fútbol");
    expect(screen.getByTestId("menu-lineas-Fútbol")).toBeTruthy();
    // "Todas las de Fútbol" + una entrada por línea (incluida la vacía).
    expect(screen.getByText("Mundial")).toBeTruthy();
    expect(screen.getByText("Liga MX")).toBeTruthy();
    expect(screen.getByText("Bundesliga")).toBeTruthy();
  });

  it("elegir una línea emite (grupo, línea) y cierra el menú", () => {
    const onSelLinea = vi.fn();
    render(
      <NavGruposLineas
        grupos={grupos}
        total={4}
        grupoSel="Fútbol"
        lineaSel=""
        onSelGrupo={vi.fn()}
        onSelLinea={onSelLinea}
      />,
    );
    fireEvent.click(screen.getByTestId("chip-grupo-Fútbol"));
    fireEvent.click(screen.getByText("Mundial"));
    expect(onSelLinea).toHaveBeenCalledWith("Fútbol", "fut-mundial");
    expect(screen.queryByTestId("menu-lineas-Fútbol")).toBeNull();
  });

  it("con una línea activa muestra el indicador y permite quitarla", () => {
    const onSelLinea = vi.fn();
    render(
      <NavGruposLineas
        grupos={grupos}
        total={4}
        grupoSel="Fútbol"
        lineaSel="fut-mundial"
        onSelGrupo={vi.fn()}
        onSelLinea={onSelLinea}
      />,
    );
    expect(screen.getByTestId("filtro-linea").textContent).toContain("Mundial");
    fireEvent.click(screen.getByLabelText("Quitar filtro de línea"));
    expect(onSelLinea).toHaveBeenCalledWith("Fútbol", "");
  });

  it("un chip SIN líneas (marca plana) solo filtra, sin desplegable", () => {
    const onSelGrupo = vi.fn();
    const planos: GrupoMesa[] = [
      { grupo: "Nacional", en_pool: 6 },
      { grupo: "Internacional", en_pool: 2 },
    ];
    render(
      <NavGruposLineas
        grupos={planos}
        total={8}
        grupoSel=""
        lineaSel=""
        onSelGrupo={onSelGrupo}
        onSelLinea={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("chip-grupo-Nacional"));
    expect(onSelGrupo).toHaveBeenCalledWith("Nacional");
    // No hay 2º nivel: ningún menú se despliega.
    expect(screen.queryByTestId("menu-lineas-Nacional")).toBeNull();
  });
});

describe("chipsDeLineas", () => {
  const linea = (
    clave: string,
    etiqueta: string,
    en_pool: number,
    cupo: number,
    historias: Historia[] = [],
  ): MesaLinea => ({
    linea: clave,
    etiqueta,
    cupo,
    generados: 0,
    publicados: 0,
    restante: cupo,
    en_pool,
    historias,
  });

  it("deriva un chip por línea con cupo o candidatas y etiqueta cada historia con su línea", () => {
    const { chips, browse } = chipsDeLineas(
      [
        linea("breaking", "Última hora", 9, 2, [historia("a")]),
        linea("nac", "Nacional", 6, 4, [historia("b"), historia("c")]),
        linea("int", "Internacional", 2, 4, [historia("d")]),
        linea("evergreen", "Evergreen", 0, 1, []), // sin candidatas pero con cupo: aparece igual
        linea("vacia", "Vacía", 0, 0, []), // sin cupo ni candidatas: NO aparece
      ],
      { en_pool: 1, historias: [historia("e")] },
    );
    expect(chips.map((c) => c.grupo)).toEqual([
      "Última hora",
      "Nacional",
      "Internacional",
      "Evergreen",
      "Fuera del plan",
    ]);
    expect(chips.map((c) => c.en_pool)).toEqual([9, 6, 2, 0, 1]);
    // Sin sub-líneas: chips planos (sin desplegable).
    expect(chips.every((c) => c.lineas === undefined)).toBe(true);
    // Cada historia queda etiquetada con su línea -> el filtro por chip funciona.
    expect(historiasDelGrupo(browse, "Nacional").map((h) => h.id)).toEqual(["b", "c"]);
    expect(historiasDelGrupo(browse, "Fuera del plan").map((h) => h.id)).toEqual(["e"]);
  });
});
