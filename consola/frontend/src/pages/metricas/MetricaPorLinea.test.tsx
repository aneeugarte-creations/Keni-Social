import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { MetricasLineas } from "@/types";

import { MetricaPorLinea } from "./MetricaPorLinea";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: MetricasLineas = {
  marca: "unotv",
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  lineas: [
    {
      id: "deportes",
      nombre: "Deportes",
      piezas: 12,
      visualizaciones: 120000,
      interacciones: 8000,
      engagement_pct: 6.7,
    },
    {
      id: "noticias",
      nombre: "Noticias",
      piezas: 5,
      visualizaciones: 30000,
      interacciones: 900,
      engagement_pct: 3.0,
    },
  ],
  origenes: [
    {
      id: "interno",
      nombre: "Interno",
      piezas: 14,
      visualizaciones: 140000,
      interacciones: 8500,
      engagement_pct: 6.1,
    },
    {
      id: "peticion_externa",
      nombre: "Petición externa",
      piezas: 3,
      visualizaciones: 10000,
      interacciones: 400,
      engagement_pct: 4.0,
    },
  ],
  total: {
    id: "total",
    nombre: "Total",
    piezas: 17,
    visualizaciones: 150000,
    interacciones: 8900,
    engagement_pct: 5.9,
  },
  fuente: "muestra",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("MetricaPorLinea", () => {
  it("muestra las dos tablas (por línea y por origen) con sus encabezados y filas", async () => {
    vi.spyOn(api, "metricasLineas").mockResolvedValue(RESP);
    renderConProviders(<MetricaPorLinea marcaActual="__todas__" rangoActual="semana" />);

    // Espera al dato cargado (el título de la sección ya se pinta durante la carga).
    expect(await screen.findByText("Por línea de contenido")).toBeInTheDocument();
    expect(screen.getByText("Rendimiento por línea y origen")).toBeInTheDocument();
    expect(screen.getByText("Por origen")).toBeInTheDocument();

    // Cada tabla con la primera columna propia + las columnas comunes (en ambas).
    expect(screen.getByText("Línea")).toBeInTheDocument();
    expect(screen.getByText("Origen")).toBeInTheDocument();
    expect(screen.getAllByText("Piezas").length).toBe(2);
    expect(screen.getAllByText("Vistas").length).toBe(2);
    expect(screen.getAllByText("Interacciones").length).toBe(2);
    expect(screen.getAllByText("Engagement (promedio por pieza)").length).toBe(2);

    // Filas de datos legibles con cifras es-MX y fila Total en ambas tablas.
    expect(screen.getByText("Deportes")).toBeInTheDocument();
    expect(screen.getByText("Noticias")).toBeInTheDocument();
    expect(screen.getByText("Interno")).toBeInTheDocument();
    expect(screen.getByText("Petición externa")).toBeInTheDocument();
    expect(screen.getByText("120,000")).toBeInTheDocument();
    expect(screen.getAllByText("Total").length).toBe(2);
    expect(screen.getAllByText("150,000").length).toBe(2);
  });

  it("dice con honestidad cuando un corte no trae filas pero el otro sí", async () => {
    vi.spyOn(api, "metricasLineas").mockResolvedValue({ ...RESP, origenes: [] });
    renderConProviders(<MetricaPorLinea marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Deportes")).toBeInTheDocument();
    // La tabla "Por origen" sigue presente, con su vacío local honesto.
    const bloqueOrigen = screen.getByText("Por origen").parentElement as HTMLElement;
    expect(
      within(bloqueOrigen).getByText("Sin datos para este corte en el periodo."),
    ).toBeInTheDocument();
  });

  it("muestra el vacío global honesto cuando no hay líneas ni orígenes", async () => {
    vi.spyOn(api, "metricasLineas").mockResolvedValue({
      ...RESP,
      lineas: [],
      origenes: [],
    });
    renderConProviders(<MetricaPorLinea marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/aún no hay rendimiento por línea u origen para este periodo/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Por línea de contenido")).not.toBeInTheDocument();
  });
});
