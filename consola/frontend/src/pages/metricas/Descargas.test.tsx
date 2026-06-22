import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { BotonesDescarga } from "./Descargas";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  // jsdom no implementa la creación de object URLs: la stubeamos para la descarga blob.
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
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
    queryFn: async () => ({ total: { visualizaciones: 1000, interacciones: 50 } }),
    // `initialData` deja el dato disponible y la query ACTIVA desde el primer render.
    initialData: { total: { visualizaciones: 1000, interacciones: 50 } },
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return null;
}

function renderConCache() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ActivarReporte />
      <BotonesDescarga {...PROPS_BASE} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("BotonesDescarga (acciones de Métricas)", () => {
  it("muestra exactamente dos botones: CSV y PDF (sin formatos antiguos)", () => {
    renderConCache();
    expect(screen.getByRole("button", { name: /CSV/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /PDF/ })).toBeInTheDocument();
    expect(screen.queryByText(/Markdown/)).not.toBeInTheDocument();
    expect(screen.queryByText(/JSON/)).not.toBeInTheDocument();
  });

  it("CSV vuelca las queries activas a un archivo descargado", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderConCache();

    fireEvent.click(screen.getByRole("button", { name: /CSV/ }));

    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});
