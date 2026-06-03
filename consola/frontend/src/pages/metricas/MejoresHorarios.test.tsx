import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { Horarios } from "@/types";

import { MejoresHorarios } from "./MejoresHorarios";

// jsdom no implementa ResizeObserver; lo stubbeamos por si algún hijo lo requiere al montar.
beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: Horarios = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  celdas: [
    // Lunes (0) a las 09:00.
    { dia_semana: 0, hora: 9, n_piezas: 4, visualizaciones: 120000, interacciones: 9000, engagement_pct: 7.5 },
    // Miércoles (2) a las 20:00 — la mejor.
    { dia_semana: 2, hora: 20, n_piezas: 6, visualizaciones: 300000, interacciones: 30000, engagement_pct: 10.0 },
  ],
  mejor: { dia_semana: 2, hora: 20, n_piezas: 6, visualizaciones: 300000, interacciones: 30000, engagement_pct: 10.0 },
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("MejoresHorarios (heatmap día×hora)", () => {
  it("pinta el heatmap y resalta la mejor franja", async () => {
    vi.spyOn(api, "metricasHorarios").mockResolvedValue(RESP);
    const { container } = renderConProviders(
      <MejoresHorarios marcaActual="__todas__" rangoActual="semana" />,
    );

    // Etiquetas de días en español y horas a dos dígitos.
    expect(await screen.findByText("Lun")).toBeInTheDocument();
    expect(screen.getByText("Dom")).toBeInTheDocument();
    expect(screen.getByText("00")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();

    // La mejor franja se anuncia (Miércoles 20:00) y se marca una celda como `mejor`.
    expect(screen.getByText(/Mié 20:00/)).toBeInTheDocument();
    expect(container.querySelector('[data-mejor="true"]')).not.toBeNull();
  });

  it("muestra un vacío honesto cuando la fuente no aporta hora", async () => {
    vi.spyOn(api, "metricasHorarios").mockResolvedValue({ ...RESP, celdas: [], mejor: null });
    renderConProviders(<MejoresHorarios marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/no aporta la hora de publicación/i),
    ).toBeInTheDocument();
  });
});
