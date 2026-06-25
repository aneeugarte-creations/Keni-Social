import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type {
  SerieAlcance as SerieAlcanceResp,
  SerieSeguidores,
  TendenciaDiaria,
} from "@/types";

import { SerieAlcance } from "./SerieAlcance";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: SerieAlcanceResp = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  puntos: [
    { fecha: "2026-05-26", total: 12000, por_red: { instagram: 12000 } },
    { fecha: "2026-05-27", total: 13500, por_red: { instagram: 13500 } },
  ],
};

// Impresiones IG diarias: insumo de la frecuencia (impresiones ÷ alcance).
const TENDENCIA: TendenciaDiaria = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  puntos: [
    { fecha: "2026-05-26", visualizaciones: 18000, interacciones: 0 },
    { fecha: "2026-05-27", visualizaciones: 20250, interacciones: 0 },
  ],
  generado_en: "2026-06-01T00:00:00Z",
};

// Seguidores IG: base de la amplificación (alcance medio ÷ seguidores).
const SEGUIDORES: SerieSeguidores = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  puntos: [
    { fecha: "2026-05-26", total: 25000, por_red: { instagram: 25000 } },
    { fecha: "2026-05-27", total: 25500, por_red: { instagram: 25500 } },
  ],
  neto: 500,
  generado_en: "2026-06-01T00:00:00Z",
  neto_por_red: { instagram: 500 },
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("SerieAlcance", () => {
  beforeEach(() => {
    vi.spyOn(api, "metricasTendencia").mockResolvedValue(TENDENCIA);
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue(SEGUIDORES);
  });

  it("pinta alcance + ratios de frecuencia y amplificación cuando hay serie", async () => {
    vi.spyOn(api, "metricasSerieAlcance").mockResolvedValue(RESP);
    renderConProviders(<SerieAlcance marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Alcance y frecuencia")).toBeInTheDocument();
    // El chart lleva un wrapper accesible (role=img) con el periodo en su aria-label.
    expect(
      await screen.findByRole("img", { name: /alcance e impresiones/i }),
    ).toBeInTheDocument();
    // Los dos ratios accionables son el titular del bloque.
    expect(await screen.findByText("Frecuencia media diaria")).toBeInTheDocument();
    expect(screen.getByText("Amplificación")).toBeInTheDocument();
    // Frecuencia = Σ impresiones ÷ Σ alcance = 38250 ÷ 25500 = 1.5×.
    expect(await screen.findByText("1.5×")).toBeInTheDocument();
  });

  it("muestra '—' en amplificación cuando no hay seguidores de Instagram", async () => {
    vi.spyOn(api, "metricasSerieAlcance").mockResolvedValue(RESP);
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue({
      ...SEGUIDORES,
      puntos: [],
      neto: 0,
      neto_por_red: {},
    });
    renderConProviders(<SerieAlcance marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Amplificación")).toBeInTheDocument();
    expect(await screen.findByText("—")).toBeInTheDocument();
  });

  it("degrada con honestidad cuando la fuente no expone alcance (solo IG lo mide)", async () => {
    vi.spyOn(api, "metricasSerieAlcance").mockResolvedValue({ ...RESP, puntos: [] });
    renderConProviders(<SerieAlcance marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/no hay alcance de cuenta para este periodo/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
