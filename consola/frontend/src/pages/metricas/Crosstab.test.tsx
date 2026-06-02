import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { Crosstab as CrosstabResp } from "@/types";

import { Crosstab } from "./Crosstab";

// Tremor/recharts no se usan aquí, pero jsdom no implementa ResizeObserver: lo stubbeamos
// por seguridad para cualquier hijo que lo requiera al montar.
beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: CrosstabResp = {
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  celdas: [
    {
      marca: "UnoTV",
      red: "instagram",
      formato: "reel",
      n_piezas: 12,
      visualizaciones: 120000,
      interacciones: 8000,
      engagement_pct: 6.7,
      rendimiento_relativo_medio: 1.4,
    },
    {
      marca: "Claro Sports",
      red: "x",
      formato: null,
      n_piezas: 5,
      visualizaciones: 30000,
      interacciones: 900,
      engagement_pct: 3.0,
      rendimiento_relativo_medio: 0.6,
    },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("Crosstab (rendimiento por formato)", () => {
  it("pinta las celdas marca×red×formato con su rendimiento relativo", async () => {
    vi.spyOn(api, "metricasCrosstab").mockResolvedValue(RESP);
    renderConProviders(<Crosstab marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("UnoTV")).toBeInTheDocument();
    expect(screen.getByText("reel")).toBeInTheDocument();
    // formato null se muestra como "Sin formato".
    expect(screen.getByText("Sin formato")).toBeInTheDocument();
    // rendimiento relativo formateado con sufijo "×".
    expect(screen.getByText("1.4×")).toBeInTheDocument();
    expect(screen.getByText("0.6×")).toBeInTheDocument();
  });

  it("muestra un vacío honesto cuando la fuente no expone celdas", async () => {
    vi.spyOn(api, "metricasCrosstab").mockResolvedValue({ ...RESP, celdas: [] });
    renderConProviders(<Crosstab marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/no expone el cruce por formato/i),
    ).toBeInTheDocument();
  });
});
