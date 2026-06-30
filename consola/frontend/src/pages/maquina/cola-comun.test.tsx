import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Backlog } from "@/types";

import { TablaBacklog } from "./cola-comun";

const BACKLOG: Backlog = {
  marcas: [
    {
      marca: "claro-sports",
      nombre: "Claro Sports",
      etapas: {
        pool_sin_admitir: 3,
        pipeline_en_proceso: 1,
        esperando_copy: 600,
        generando_copy: 4,
        generando_arte: 2,
        lista_para_revisar: 5,
      },
      total: 615,
    },
    {
      marca: "unotv",
      nombre: "UnoTV",
      etapas: {
        pool_sin_admitir: 0,
        pipeline_en_proceso: 0,
        esperando_copy: 0,
        generando_copy: 0,
        generando_arte: 0,
        lista_para_revisar: 0,
      },
      total: 0,
    },
  ],
};

describe("TablaBacklog", () => {
  it("pinta una fila por marca y las 6 etapas en orden de cadena + total", () => {
    render(<TablaBacklog backlog={BACKLOG} />);

    // Una fila por marca.
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    expect(screen.getByText("UnoTV")).toBeInTheDocument();

    // Las 6 etapas como cabeceras, EN ORDEN de cadena (entrada → salida) + Total.
    const cabeceras = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(cabeceras).toEqual([
      "Marca",
      "Pool",
      "En proceso",
      "Esperando copy",
      "Generando copy",
      "Generando arte",
      "Lista para revisar",
      "Total",
    ]);

    // La fila de Claro Sports muestra el "embalse oculto" de 600 esperando copy y su total.
    const filaClaro = screen.getByText("Claro Sports").closest("tr");
    expect(filaClaro).not.toBeNull();
    expect(within(filaClaro as HTMLElement).getByText("600")).toBeInTheDocument();
    expect(within(filaClaro as HTMLElement).getByText("615")).toBeInTheDocument();
  });

  it("usa el título por defecto, y lo enmarca por página cuando se le pasa `titulo`", () => {
    const { rerender } = render(<TablaBacklog backlog={BACKLOG} />);
    expect(screen.getByText("Embalse del tablero (antes de la cola)")).toBeInTheDocument();

    rerender(<TablaBacklog backlog={BACKLOG} titulo="Trabajo pendiente (backlog que costará)" />);
    expect(screen.getByText("Trabajo pendiente (backlog que costará)")).toBeInTheDocument();
    expect(screen.queryByText("Embalse del tablero (antes de la cola)")).toBeNull();
  });
});
