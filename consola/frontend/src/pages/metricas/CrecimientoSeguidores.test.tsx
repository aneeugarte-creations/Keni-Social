import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { SerieSeguidores } from "@/types";

import { CrecimientoSeguidores } from "./CrecimientoSeguidores";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: SerieSeguidores = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  neto: 1234,
  neto_por_red: { instagram: 800, x: 434 },
  puntos: [
    { fecha: "2026-05-26", total: 10000, por_red: { instagram: 6000, x: 4000 } },
    { fecha: "2026-05-27", total: 10500, por_red: { instagram: 6300, x: 4200 } },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("CrecimientoSeguidores", () => {
  it("muestra el neto global y por red como KPIs", async () => {
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue(RESP);
    renderConProviders(<CrecimientoSeguidores marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Neto del periodo")).toBeInTheDocument();
    // REGRESIÓN: el neto de seguidores es un CONTEO, NUNCA un porcentaje (antes el bug
    // lo pintaba con `variacion()` -> "+1,234.0 %", incluso "−4,979,127.0 %").
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    // El KPI del neto lleva el conteo exacto en su tooltip ("1,234 seguidores").
    expect(screen.getByTitle("1,234 seguidores")).toBeInTheDocument();
    // un KPI por red presente en neto_por_red, con la etiqueta de red LEGIBLE
    // (instagram → "Instagram", x → "X"), no el id crudo.
    expect(screen.getByText("Instagram")).toBeInTheDocument();
    expect(screen.getByText("X")).toBeInTheDocument();
    expect(screen.queryByText("instagram")).not.toBeInTheDocument();
  });

  it("ofrece una alternativa textual del chart (role=img con el neto del periodo)", async () => {
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue(RESP);
    renderConProviders(<CrecimientoSeguidores marcaActual="__todas__" rangoActual="semana" />);

    // El gráfico lleva un wrapper role="img" cuyo aria-label resume el neto con signo.
    expect(
      await screen.findByRole("img", { name: /seguidores del periodo: neto \+/i }),
    ).toBeInTheDocument();
  });

  it("dice con honestidad cuando la fuente no expone seguidores", async () => {
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue({
      ...RESP,
      puntos: [],
      neto_por_red: {},
    });
    renderConProviders(<CrecimientoSeguidores marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/aún no hay datos de seguidores para este periodo/i),
    ).toBeInTheDocument();
  });
});
