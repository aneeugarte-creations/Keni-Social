import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";

import { Descargas } from "./Descargas";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

/** Abre el menú de descargas (click izquierdo sobre el botón disparador). */
function abrirMenu() {
  fireEvent.click(screen.getByRole("button", { name: /descargar/i }));
  return screen.getByRole("menu", { name: "Descargar reporte" });
}

describe("Descargas", () => {
  it("ofrece los dos grupos (reporte y top/peores piezas) separados en un único menú", () => {
    vi.spyOn(api, "exportarMetricas").mockImplementation(() => {});
    vi.spyOn(api, "exportarPiezas").mockImplementation(() => {});
    render(<Descargas rango="semana" marca="unotv" />);

    abrirMenu();
    for (const etiqueta of ["CSV", "Markdown", "JSON"]) {
      expect(
        screen.getByRole("menuitem", { name: `Reporte (${etiqueta})` }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("menuitem", { name: `Top y peores piezas (${etiqueta})` }),
      ).toBeInTheDocument();
    }
  });

  it("descarga el top/peores de piezas con el combo activo (rango, marca)", () => {
    const espia = vi.spyOn(api, "exportarPiezas").mockImplementation(() => {});
    render(<Descargas rango="semana" marca="unotv" />);

    abrirMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Top y peores piezas (CSV)" }));

    expect(espia).toHaveBeenCalledWith("csv", { rango: "semana", marca: "unotv" });
  });

  it("el reporte sigue delegando en exportarMetricas (sin marca = todas)", () => {
    const reporte = vi.spyOn(api, "exportarMetricas").mockImplementation(() => {});
    const piezas = vi.spyOn(api, "exportarPiezas").mockImplementation(() => {});
    render(<Descargas rango="mes" />);

    abrirMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Reporte (Markdown)" }));

    expect(reporte).toHaveBeenCalledWith("md", { rango: "mes", marca: undefined });
    expect(piezas).not.toHaveBeenCalled();
  });
});
