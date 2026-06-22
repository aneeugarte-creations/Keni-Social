import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { MenuAcciones } from "@/components/layout/MenuAcciones";

import { ItemsDescarga } from "./Descargas";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
  // jsdom no implementa print: lo stubeamos para el PDF (motor de impresión del navegador).
  window.print = vi.fn();
});

const PROPS_BASE = {
  rango: "mes",
  marca: "claro_sports",
  marcaEtiqueta: "Claro Sports",
  redEtiqueta: "Instagram",
  periodoEtiqueta: "junio 2026",
};

/** Activa una query de métricas en la caché para que el CSV tenga algo que volcar. */
function ActivarReporte() {
  useQuery({
    queryKey: ["metricas", "reporte", "mes", "claro_sports"],
    queryFn: async () => ({ total: { visualizaciones: 1000 } }),
    initialData: { total: { visualizaciones: 1000 } },
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return null;
}

/** Renderiza los items dentro del menú "⋮" (como en Metricas) + un deck simulado, y lo abre. */
function renderYAbrir() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ActivarReporte />
      <div data-deck-root>
        <div data-slide="Resumen">contenido</div>
      </div>
      <MenuAcciones>
        <ItemsDescarga {...PROPS_BASE} />
      </MenuAcciones>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Acciones" }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ItemsDescarga (menú ⋮ de Métricas)", () => {
  it("ofrece CSV y PDF (sin formatos antiguos)", () => {
    renderYAbrir();
    expect(screen.getByRole("menuitem", { name: /Descargar CSV/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Descargar PDF/ })).toBeInTheDocument();
    expect(screen.queryByText(/Markdown/)).not.toBeInTheDocument();
    expect(screen.queryByText(/JSON/)).not.toBeInTheDocument();
  });

  it("CSV vuelca las queries activas a un archivo descargado", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderYAbrir();

    fireEvent.click(screen.getByRole("menuitem", { name: /Descargar CSV/ }));

    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it("PDF lanza la impresión del navegador", async () => {
    renderYAbrir();

    fireEvent.click(screen.getByRole("menuitem", { name: /Descargar PDF/ }));

    await waitFor(() => expect(window.print).toHaveBeenCalledTimes(1));
  });
});
