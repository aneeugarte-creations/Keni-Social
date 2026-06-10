import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import { porcentaje } from "@/lib/formato";
import type { PiezasPorEtiqueta } from "@/types";

import { GraficaPorSerie } from "./GraficaPorSerie";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: PiezasPorEtiqueta = {
  marca: "",
  rango: "mes",
  etiqueta_rango: "Últimos 30 días",
  series: [
    {
      eje: "tipo",
      etiqueta: "Tipo de contenido",
      grupos: [
        { valor: "Reel", n: 6, visualizaciones: 90000, engagement_pct: 5.2 },
        { valor: "Foto", n: 4, visualizaciones: 12000, engagement_pct: 3.1 },
      ],
    },
    {
      eje: "campania",
      etiqueta: "Campaña",
      grupos: [
        { valor: "Mundial 2026", n: 3, visualizaciones: 70000, engagement_pct: 7.4 },
        { valor: "Sin clasificar", n: 7, visualizaciones: 32000, engagement_pct: 2.9 },
      ],
    },
  ],
  total: 10,
  enlazadas: 6,
  enlazadas_titulo: 2,
  sin_enlace: 2,
  fuente: "muestra",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("GraficaPorSerie", () => {
  it("pinta un tab por eje y la alternativa textual del chart activo (role=img)", async () => {
    vi.spyOn(api, "metricasPiezasPorEtiqueta").mockResolvedValue(RESP);
    renderConProviders(<GraficaPorSerie marcaActual="__todas__" rangoActual="mes" />);

    // Un tab por eje de la respuesta.
    expect(await screen.findByRole("tab", { name: "Tipo de contenido" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Campaña" })).toBeInTheDocument();

    // El chart del tab activo lleva role=img con cada grupo y su engagement FORMATEADO.
    const img = screen.getByRole("img", { name: /Engagement por Tipo de contenido/ });
    expect(img).toHaveAttribute(
      "aria-label",
      `Engagement por Tipo de contenido: Reel ${porcentaje(5.2)}, Foto ${porcentaje(3.1)}`,
    );
  });

  it("muestra la línea de cobertura del enlace con el tablero (honestidad)", async () => {
    vi.spyOn(api, "metricasPiezasPorEtiqueta").mockResolvedValue(RESP);
    renderConProviders(<GraficaPorSerie marcaActual="__todas__" rangoActual="mes" />);

    expect(
      await screen.findByText(
        /10 piezas · 6 vinculadas al tablero · 2 por título \(aproximado\) · 2 sin clasificar/,
      ),
    ).toBeInTheDocument();
  });

  it("dice con honestidad cuando no hay piezas en el periodo", async () => {
    vi.spyOn(api, "metricasPiezasPorEtiqueta").mockResolvedValue({
      ...RESP,
      series: [],
      total: 0,
      enlazadas: 0,
      enlazadas_titulo: 0,
      sin_enlace: 0,
    });
    renderConProviders(<GraficaPorSerie marcaActual="__todas__" rangoActual="mes" />);

    expect(await screen.findByText(/Sin piezas en este periodo/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
