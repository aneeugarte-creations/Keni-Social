import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { MenuAcciones } from "@/components/layout/MenuAcciones";
import { api } from "@/lib/api";

import { ItemsDescargas } from "./Descargas";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

/** Renderiza los items dentro del menú "⋮" de página (como en Metricas) y lo abre. */
function renderYAbrir(props: { rango: string; marca?: string }) {
  render(
    <MenuAcciones>
      <ItemsDescargas {...props} />
    </MenuAcciones>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Acciones" }));
  return screen.getByRole("menu");
}

describe("ItemsDescargas (menú ⋮ de Métricas)", () => {
  it("ofrece los dos grupos (reporte y top/peores piezas) separados", () => {
    vi.spyOn(api, "exportarMetricas").mockImplementation(() => {});
    vi.spyOn(api, "exportarPiezas").mockImplementation(() => {});
    renderYAbrir({ rango: "semana", marca: "unotv" });

    for (const etiqueta of ["CSV", "Markdown", "JSON"]) {
      expect(
        screen.getByRole("menuitem", { name: `Reporte (${etiqueta})` }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("menuitem", { name: `Top y peores piezas (${etiqueta})` }),
      ).toBeInTheDocument();
    }
    expect(screen.getByRole("separator")).toBeInTheDocument();
  });

  it("descarga el top/peores de piezas con el combo activo (rango, marca)", () => {
    const espia = vi.spyOn(api, "exportarPiezas").mockImplementation(() => {});
    renderYAbrir({ rango: "semana", marca: "unotv" });

    fireEvent.click(screen.getByRole("menuitem", { name: "Top y peores piezas (CSV)" }));

    expect(espia).toHaveBeenCalledWith("csv", { rango: "semana", marca: "unotv" });
  });

  it("el reporte sigue delegando en exportarMetricas (sin marca = todas)", () => {
    const reporte = vi.spyOn(api, "exportarMetricas").mockImplementation(() => {});
    const piezas = vi.spyOn(api, "exportarPiezas").mockImplementation(() => {});
    renderYAbrir({ rango: "mes" });

    fireEvent.click(screen.getByRole("menuitem", { name: "Reporte (Markdown)" }));

    expect(reporte).toHaveBeenCalledWith("md", { rango: "mes", marca: undefined });
    expect(piezas).not.toHaveBeenCalled();
  });
});
