import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CategoriaPlanOpcion, Pieza } from "@/types";

import { PanelFiltrosLimpieza, type FiltrosLimpieza } from "./PanelFiltrosLimpieza";

function pieza(over: Partial<Pieza> = {}): Pieza {
  return { id: "p1", categoria: "", fuente_original: "", ...over } as Pieza;
}

function montar(
  valor: FiltrosLimpieza = {},
  piezas: Pieza[] = [],
  categorias: CategoriaPlanOpcion[] = [],
) {
  const onCambio = vi.fn();
  render(
    <PanelFiltrosLimpieza
      valor={valor}
      onCambio={onCambio}
      categorias={categorias}
      piezas={piezas}
    />,
  );
  return { onCambio };
}

describe("PanelFiltrosLimpieza", () => {
  it("siempre ofrece los filtros fijos (antigüedad, fase, tipo)", () => {
    montar();
    expect(screen.getByLabelText("Filtrar por antigüedad")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por fase")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por tipo")).toBeInTheDocument();
  });

  it("categoría sale del CATÁLOGO; fuente, de las piezas cargadas", () => {
    montar({}, [], []);
    expect(screen.queryByLabelText("Filtrar por categoría")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Filtrar por fuente")).not.toBeInTheDocument();

    // La categoría YA NO se deriva de los ids crudos de las piezas: viene del catálogo del
    // plan (`{id, nombre}`). La fuente sí sigue derivándose de las piezas cargadas.
    montar(
      {},
      [pieza({ categoria: "breaking", fuente_original: "Infobae" })],
      [{ id: "breaking", nombre: "Última hora" }],
    );
    expect(screen.getByLabelText("Filtrar por categoría")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por fuente")).toBeInTheDocument();
  });

  it("sin catálogo de categorías no se ofrece el dropdown aunque las piezas traigan una", () => {
    montar({}, [pieza({ categoria: "breaking" })], []);
    expect(screen.queryByLabelText("Filtrar por categoría")).not.toBeInTheDocument();
  });

  it("«Limpiar filtros» solo se ofrece con algún filtro activo y lo resetea", () => {
    const { onCambio } = montar({});
    expect(screen.queryByText("Limpiar filtros")).not.toBeInTheDocument();

    const { onCambio: onCambio2 } = montar({ fase: "incompleto" });
    fireEvent.click(screen.getByText("Limpiar filtros"));
    expect(onCambio2).toHaveBeenCalledWith({});
    expect(onCambio).not.toHaveBeenCalled();
  });
});
