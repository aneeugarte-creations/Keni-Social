import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { SerieAlcance as SerieAlcanceResp } from "@/types";

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

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("SerieAlcance", () => {
  it("pinta la tendencia de alcance cuando hay serie", async () => {
    vi.spyOn(api, "metricasSerieAlcance").mockResolvedValue(RESP);
    renderConProviders(<SerieAlcance marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Alcance de cuenta")).toBeInTheDocument();
    // El chart lleva un wrapper accesible (role=img) con el periodo en su aria-label.
    expect(
      await screen.findByRole("img", { name: /tendencia de alcance de cuenta/i }),
    ).toBeInTheDocument();
    // Deja claro que es alcance ÚNICO, distinto de las impresiones (volumen).
    expect(screen.getByText(/alcance ÚNICO/i)).toBeInTheDocument();
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
