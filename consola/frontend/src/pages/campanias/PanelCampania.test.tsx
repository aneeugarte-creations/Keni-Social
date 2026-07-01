/**
 * Tests del bloque "Orgánico vs pagado" del panel de una campaña.
 *
 * Se pasa la analítica ya cargada (`datos`) para no montar la query: el panel solo la
 * pinta. La gráfica de tendencia (recharts) se mockea: aquí se prueba la lógica del
 * bloque de pauta, no el render del SVG.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { useVistaConfig } from "@/pages/metricas/vistaConfig";
import type { AnaliticaCampania, ComparativaKpi } from "@/types";

import { PanelCampania } from "./PanelCampania";

vi.mock("./GraficaTendencia", () => ({ GraficaTendencia: () => null }));

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

afterEach(() => {
  useVistaConfig.getState().reset();
});

const COMP: ComparativaKpi = { actual: 0, anterior: 0, delta: 0, variacion_pct: null };

function datos(
  visualizacionesPagadas: number,
  campaniaOverrides: Partial<AnaliticaCampania["campania"]> = {},
): AnaliticaCampania {
  return {
    campania: {
      id: "c1",
      marcas: ["uno_tv"],
      marcas_nombres: ["UnoTV"],
      nombre: "Mundial 2026",
      hashtags: ["Mundial2026"],
      etiqueta_web: "",
      precio_venta: 0,
      margen_objetivo_pct: 40,
      activa: true,
      fecha_creacion: "2026-06-01T00:00:00Z",
      fecha_actualizacion: "2026-06-01T00:00:00Z",
      ...campaniaOverrides,
    },
    rango: "mes",
    periodo: { desde: "2026-05-26", hasta: "2026-06-25" },
    fuente: "metricool",
    kpis: { visualizaciones: 500000, interacciones: 23000, engagement_pct: 4.6, piezas: 12, alcance: null },
    comparativa: { visualizaciones: COMP, interacciones: COMP, engagement_pct: COMP, piezas: COMP },
    tendencia: { puntos: [] },
    desglose_red: [],
    cross_posts: 0,
    inorganico: { visualizaciones: visualizacionesPagadas, gasto: 12000, clics: 4200, campanias: 2, moneda: "MXN" },
    piezas: [],
    generado_en: "2026-06-25T12:00:00Z",
  };
}

function renderPanel(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("PanelCampania · orgánico vs pagado", () => {
  it("muestra el bloque con ambos lados cuando hubo inversión con entrega", () => {
    renderPanel(<PanelCampania datos={datos(180000)} />);

    expect(screen.getAllByText("Orgánico vs pagado").length).toBeGreaterThan(0);
    expect(screen.getByText("Orgánico")).toBeInTheDocument();
    expect(screen.getByText("Pagado (Meta Ads)")).toBeInTheDocument();
    // Lado pagado: gasto con separador es-MX y su moneda.
    expect(screen.getByText("12,000 MXN")).toBeInTheDocument();
  });

  it("NO muestra el bloque sin inversión con entrega (degrada)", () => {
    renderPanel(<PanelCampania datos={datos(0)} />);

    expect(screen.queryByText("Orgánico vs pagado")).not.toBeInTheDocument();
    expect(screen.queryByText("Pagado (Meta Ads)")).not.toBeInTheDocument();
  });

  it("oculta TODO lo de pauta en modo cliente (ocultarAds)", () => {
    renderPanel(<PanelCampania datos={datos(180000)} ocultarAds />);

    expect(screen.queryByText("Orgánico vs pagado")).not.toBeInTheDocument();
    expect(screen.queryByText("Pagado (Meta Ads)")).not.toBeInTheDocument();
  });
});

describe("PanelCampania · rentabilidad", () => {
  it("muestra el tope de pauta cuando la campaña tiene precio de venta", () => {
    renderPanel(<PanelCampania datos={datos(0, { precio_venta: 1200000, margen_objetivo_pct: 40 })} />);

    expect(screen.getByText("Rentabilidad")).toBeInTheDocument();
    // Tope = 1,200,000 * (1 - 0.4) = 720,000.
    expect(screen.getByText("720,000 MXN")).toBeInTheDocument();
  });

  it("NO se muestra sin precio de venta definido", () => {
    renderPanel(<PanelCampania datos={datos(0, { precio_venta: 0 })} />);

    expect(screen.queryByText("Rentabilidad")).not.toBeInTheDocument();
  });

  it("no avisa cuando el gasto del periodo está dentro del tope", () => {
    renderPanel(
      <PanelCampania datos={datos(180000, { precio_venta: 1000000, margen_objetivo_pct: 40 })} />,
    );

    // Tope = 600,000; gasto (mock) = 12,000 -> dentro del tope, no hay aviso.
    expect(screen.queryByText(/ya superó el tope/i)).not.toBeInTheDocument();
  });

  it("avisa cuando el gasto del periodo ya superó el tope", () => {
    // Gasto (mock) = 12,000; tope = 10,000 * (1 - 0) = 10,000 -> por encima del tope.
    renderPanel(
      <PanelCampania datos={datos(0, { precio_venta: 10000, margen_objetivo_pct: 0 })} />,
    );

    expect(screen.getByText(/ya superó el tope/i)).toBeInTheDocument();
    expect(screen.getByText("Por encima del tope")).toBeInTheDocument();
  });

  it("oculta la rentabilidad en modo cliente (ocultarAds)", () => {
    renderPanel(
      <PanelCampania datos={datos(0, { precio_venta: 1200000 })} ocultarAds />,
    );

    expect(screen.queryByText("Rentabilidad")).not.toBeInTheDocument();
  });
});
