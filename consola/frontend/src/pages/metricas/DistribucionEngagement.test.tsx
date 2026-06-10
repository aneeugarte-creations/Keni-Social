import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { AnaliticaPiezas, EstadisticasNumericas } from "@/types";

import { DistribucionEngagement } from "./DistribucionEngagement";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const ENGAGEMENT: EstadisticasNumericas = {
  n: 42,
  media: 2.4,
  mediana: 1.8,
  p25: 0.9,
  p75: 3.2,
  minimo: 0.1,
  maximo: 12.5,
  desviacion: 1.6,
};

const VISTAS: EstadisticasNumericas = {
  n: 42,
  media: 52_000,
  mediana: 18_400,
  p25: 5_200,
  p75: 61_000,
  minimo: 120,
  maximo: 1_200_000,
  desviacion: 90_000,
};

/** Estadísticas sin base de cálculo: todo `null` salvo `n` (la UI debe pintar "—"). */
const SIN_BASE: EstadisticasNumericas = {
  n: 0,
  media: null,
  mediana: null,
  p25: null,
  p75: null,
  minimo: null,
  maximo: null,
  desviacion: null,
};

const RESP: AnaliticaPiezas = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-06-01", hasta: "2026-06-07" },
  total: 42,
  fuente: "muestra",
  engagement: ENGAGEMENT,
  visualizaciones: VISTAS,
  top: [],
  peores: [],
  distribucion: [
    { etiqueta: "0–1%", inicio: 0, fin: 1, n: 12 },
    { etiqueta: "1–3%", inicio: 1, fin: 3, n: 22 },
    { etiqueta: "3%+", inicio: 3, fin: null, n: 8 },
  ],
  generado_en: "2026-06-08T00:00:00",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DistribucionEngagement", () => {
  it("muestra los KPIs del servidor con porcentajes es-MX", async () => {
    vi.spyOn(api, "metricasPiezas").mockResolvedValue(RESP);
    renderConProviders(<DistribucionEngagement marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Mediana")).toBeInTheDocument();
    // Mediana del engagement con formato porcentaje es-MX (1 decimal + " %").
    expect(screen.getByText("1.8 %")).toBeInTheDocument();
    // El tooltip de la mediana lleva la desviación típica (no cabe como KPI propio).
    expect(screen.getByTitle("Mediana: 1.8 % · Desviación típica: 1.6 %")).toBeInTheDocument();
    // Conteo de piezas (n del conjunto COMPLETO del servidor) y rangos intercuartílico/total.
    expect(screen.getByText("Piezas")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("0.9 % – 3.2 %")).toBeInTheDocument();
    expect(screen.getByText("0.1 % – 12.5 %")).toBeInTheDocument();
  });

  it("ofrece una alternativa textual del histograma (role=img con el tramo a tramo)", async () => {
    vi.spyOn(api, "metricasPiezas").mockResolvedValue(RESP);
    renderConProviders(<DistribucionEngagement marcaActual="__todas__" rangoActual="semana" />);

    // El resumen incluye el total y CADA etiqueta de tramo con su conteo: es la única
    // representación accesible del chart (los ticks SVG no se renderizan en jsdom).
    const img = await screen.findByRole("img");
    expect(img).toHaveAttribute(
      "aria-label",
      "Distribución del engagement de 42 piezas: 0–1%: 12, 1–3%: 22, 3%+: 8",
    );
  });

  it("muestra la línea de vistas por pieza con números compactos", async () => {
    vi.spyOn(api, "metricasPiezas").mockResolvedValue(RESP);
    renderConProviders(<DistribucionEngagement marcaActual="__todas__" rangoActual="semana" />);

    // El símbolo compacto de miles depende del ICU del entorno ("k" o "mil");
    // validamos estructura y cifras sin atarnos a él.
    const linea = await screen.findByText(/Vistas por pieza: mediana 18.4\s*(k|mil)/i);
    expect(linea).toHaveTextContent(/p25 5.2\s*(k|mil)/i);
    expect(linea).toHaveTextContent(/mín 120/);
    expect(linea).toHaveTextContent(/máx 1.2\s*M/);
  });

  it("pinta «—» cuando faltan campos estadísticos (null) sin reventar", async () => {
    vi.spyOn(api, "metricasPiezas").mockResolvedValue({
      ...RESP,
      total: 1,
      engagement: {
        ...ENGAGEMENT,
        n: 1,
        p25: null,
        p75: null,
        desviacion: null,
      },
      visualizaciones: SIN_BASE,
      distribucion: [{ etiqueta: "0–1%", inicio: 0, fin: 1, n: 1 }],
    });
    renderConProviders(<DistribucionEngagement marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Mediana")).toBeInTheDocument();
    // p25/p75 null → "— – —"; desviación null → "—" en el tooltip de la mediana.
    expect(screen.getByText("— – —")).toBeInTheDocument();
    expect(screen.getByTitle("Mediana: 1.8 % · Desviación típica: —")).toBeInTheDocument();
    // Las vistas sin base de cálculo se degradan a "—" campo a campo.
    expect(
      screen.getByText(/Vistas por pieza: mediana — · p25 — · p75 — · mín — · máx —/),
    ).toBeInTheDocument();
  });

  it("dice con honestidad cuando no hay piezas en el periodo", async () => {
    vi.spyOn(api, "metricasPiezas").mockResolvedValue({
      ...RESP,
      total: 0,
      engagement: SIN_BASE,
      visualizaciones: SIN_BASE,
      distribucion: [],
    });
    renderConProviders(<DistribucionEngagement marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText(/Sin piezas en este periodo/i)).toBeInTheDocument();
  });

  it("muestra el error de carga sin tumbar la sección", async () => {
    vi.spyOn(api, "metricasPiezas").mockRejectedValue(new Error("boom"));
    renderConProviders(<DistribucionEngagement marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/No se pudo cargar la distribución de engagement/i),
    ).toBeInTheDocument();
  });
});
