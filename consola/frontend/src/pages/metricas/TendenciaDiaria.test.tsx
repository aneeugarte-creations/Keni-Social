import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { TendenciaDiaria as TendenciaDiariaResp } from "@/types";

import { TendenciaDiaria } from "./TendenciaDiaria";

// Tremor/recharts requieren ResizeObserver, que jsdom no implementa.
beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

// Serie con HUECOS de calendario: solo el 1 y el 4 de junio traen datos. El componente
// debe rellenar el 2 y el 3 con ceros (días sin actividad, no datos perdidos).
const RESP: TendenciaDiariaResp = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-06-01", hasta: "2026-06-07" },
  fuente: "muestra",
  generado_en: "2026-06-08T00:00:00",
  puntos: [
    { fecha: "2026-06-01", visualizaciones: 120000, interacciones: 900 },
    { fecha: "2026-06-04", visualizaciones: 30000, interacciones: 100 },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("TendenciaDiaria", () => {
  it("rellena los huecos del calendario con ceros (días intermedios presentes)", async () => {
    vi.spyOn(api, "metricasTendencia").mockResolvedValue(RESP);
    renderConProviders(<TendenciaDiaria marcaActual="__todas__" rangoActual="semana" />);

    // 2 puntos de la fuente (01 y 04 jun) -> 4 días en la gráfica (02 y 03 a 0): el
    // aria-label del wrapper role="img" cuenta `datos.length`, no los puntos crudos.
    expect(
      await screen.findByRole("img", { name: /tendencia diaria de vistas: 4 días/i }),
    ).toBeInTheDocument();
  });

  it("formatea el total del aria-label con numeroCompleto es-MX (separador de miles)", async () => {
    vi.spyOn(api, "metricasTendencia").mockResolvedValue(RESP);
    renderConProviders(<TendenciaDiaria marcaActual="__todas__" rangoActual="semana" />);

    // 120,000 + 30,000 = 150,000 (con coma de miles, nunca "150000").
    expect(
      await screen.findByRole("img", {
        name: "Tendencia diaria de Vistas: 4 días, total 150,000",
      }),
    ).toBeInTheDocument();
  });

  it("dice con honestidad cuando la fuente no expone serie diaria", async () => {
    vi.spyOn(api, "metricasTendencia").mockResolvedValue({ ...RESP, puntos: [] });
    renderConProviders(<TendenciaDiaria marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/aún no hay datos día a día para este periodo/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
