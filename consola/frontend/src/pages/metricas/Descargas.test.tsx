import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";

import { BotonesDescarga } from "./Descargas";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const PROPS_BASE = {
  marcaEtiqueta: "UnoTV",
  redEtiqueta: "Todas las redes",
  periodoEtiqueta: "junio 2026",
};

describe("BotonesDescarga (acciones de Métricas)", () => {
  it("muestra exactamente dos botones: CSV y PDF", () => {
    render(<BotonesDescarga rango="semana" marca="unotv" {...PROPS_BASE} />);

    expect(screen.getByRole("button", { name: /CSV/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /PDF/ })).toBeInTheDocument();
    // Sin rastro de los formatos antiguos.
    expect(screen.queryByText(/Markdown/)).not.toBeInTheDocument();
    expect(screen.queryByText(/JSON/)).not.toBeInTheDocument();
  });

  it("CSV delega en exportarMetricas con el combo activo (rango, marca)", () => {
    const espia = vi.spyOn(api, "exportarMetricas").mockImplementation(() => {});
    render(<BotonesDescarga rango="semana" marca="unotv" {...PROPS_BASE} />);

    fireEvent.click(screen.getByRole("button", { name: /CSV/ }));

    expect(espia).toHaveBeenCalledWith("csv", { rango: "semana", marca: "unotv" });
  });

  it("CSV sin marca exporta el agregado (marca = undefined)", () => {
    const espia = vi.spyOn(api, "exportarMetricas").mockImplementation(() => {});
    render(
      <BotonesDescarga rango="mes" {...PROPS_BASE} marcaEtiqueta="Todas las marcas" />,
    );

    fireEvent.click(screen.getByRole("button", { name: /CSV/ }));

    expect(espia).toHaveBeenCalledWith("csv", { rango: "mes", marca: undefined });
  });
});
