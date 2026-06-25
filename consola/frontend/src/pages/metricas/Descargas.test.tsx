import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { MenuAcciones } from "@/components/layout/MenuAcciones";

import { ItemsDescarga } from "./Descargas";
import * as pdf from "./exportarPdf";

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
});

const PROPS_BASE = {
  rango: "mes",
  marca: "claro_sports",
  marcaEtiqueta: "Claro Sports",
  redEtiqueta: "Instagram",
  formatoEtiqueta: "Todos los formatos",
  periodoEtiqueta: "junio 2026",
};

/** Activa una query de métricas en la caché para que la exportación tenga algo que volcar. */
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

/** Renderiza los items dentro del menú "⋮" (como en Metricas) y lo abre. */
function renderYAbrir() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ActivarReporte />
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
  it("ofrece CSV y PDF (sin breve ni formatos antiguos)", () => {
    renderYAbrir();
    expect(screen.getByRole("menuitem", { name: /Descargar CSV/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Descargar PDF \(presentación\)/ })).toBeInTheDocument();
    expect(screen.queryByText(/breve/i)).not.toBeInTheDocument();
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

  it("PDF (presentación) genera el deck completo con los datasets activos y el contexto", async () => {
    const espia = vi.spyOn(pdf, "descargarPresentacion").mockResolvedValue();
    renderYAbrir();

    fireEvent.click(screen.getByRole("menuitem", { name: /Descargar PDF \(presentación\)/ }));

    await waitFor(() => expect(espia).toHaveBeenCalledTimes(1));
    const [entradas, ctx] = espia.mock.calls[0];
    expect(entradas.length).toBeGreaterThan(0);
    expect(ctx).toMatchObject({ marca: "Claro Sports", red: "Instagram", periodo: "junio 2026" });
    expect(espia.mock.calls[0]).toHaveLength(3);
  });
});
