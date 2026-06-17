import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Pieza } from "@/types";

import { PanelFiltrosLimpieza, type FiltrosLimpieza } from "./PanelFiltrosLimpieza";

function pieza(over: Partial<Pieza> = {}): Pieza {
  return { id: "p1", categoria: "", fuente_original: "", ...over } as Pieza;
}

function montar(valor: FiltrosLimpieza = {}, piezas: Pieza[] = []) {
  const onCambio = vi.fn();
  render(<PanelFiltrosLimpieza valor={valor} onCambio={onCambio} piezas={piezas} />);
  return { onCambio };
}

describe("PanelFiltrosLimpieza", () => {
  it("siempre ofrece los filtros fijos (antigüedad, fase, tipo)", () => {
    montar();
    expect(screen.getByLabelText("Filtrar por antigüedad")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por fase")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por tipo")).toBeInTheDocument();
  });

  it("categoría y fuente solo aparecen si las piezas cargadas las traen", () => {
    montar({}, []);
    expect(screen.queryByLabelText("Filtrar por categoría")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Filtrar por fuente")).not.toBeInTheDocument();

    montar({}, [pieza({ categoria: "breaking", fuente_original: "Infobae" })]);
    expect(screen.getByLabelText("Filtrar por categoría")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por fuente")).toBeInTheDocument();
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
