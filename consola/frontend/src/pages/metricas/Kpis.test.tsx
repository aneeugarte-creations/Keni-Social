import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import { hoyCDMX } from "@/lib/fecha";
import type { CompararMetricas, TotalMetricas } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { Kpis } from "./Kpis";

// "Hoy" fijo (corte CDMX) para que la guarda de comparabilidad sea determinista:
// 10 de junio de 2026 → mes:2026-06 está EN CURSO con 10 días transcurridos.
vi.mock("@/lib/fecha", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/fecha")>();
  return { ...real, hoyCDMX: vi.fn(() => "2026-06-10") };
});

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

beforeEach(() => {
  vi.mocked(hoyCDMX).mockReturnValue("2026-06-10");
});

const TOTAL: TotalMetricas = {
  visualizaciones: 950,
  alcance: 0,
  interacciones: 500,
  engagement_pct: 1.8,
  publicaciones: 1234,
};

/** Comparativa A (antes) vs B (actual) con los tres criterios de insignia:
 * conteo normal, conteo desde cero y engagement en puntos. */
const COMPARAR: CompararMetricas = {
  marca: "",
  rango_a: "rango:2026-04-12_2026-05-11",
  rango_b: "mes",
  etiqueta_a: "Periodo anterior",
  etiqueta_b: "Últimos 30 días",
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  total: {
    metricas: [
      { metrica: "visualizaciones", a: 100, b: 139, diferencia: 39, variacion_pct: 39 },
      // Base 0: el backend emite variacion_pct=0.0 (división imposible) → badge "Nuevo".
      { metrica: "interacciones", a: 0, b: 50, diferencia: 50, variacion_pct: 0 },
      // Engagement: SIEMPRE en puntos (diferencia), nunca variación relativa (+20 %).
      { metrica: "engagement_pct", a: 2.0, b: 2.4, diferencia: 0.4, variacion_pct: 20 },
    ],
  },
  por_marca: [],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("Kpis", () => {
  it("pinta los 4 KPIs con sus totales formateados es-MX", async () => {
    vi.spyOn(api, "metricasComparar").mockResolvedValue(COMPARAR);
    renderConProviders(<Kpis total={TOTAL} marcaActual={MARCA_TODAS} rangoActual="mes" />);

    expect(screen.getByText("Piezas publicadas")).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument(); // separador de miles es-MX
    expect(screen.getByText("Vistas")).toBeInTheDocument();
    expect(screen.getByText("950")).toBeInTheDocument();
    expect(screen.getByText("Interacciones")).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(screen.getByText("Engagement")).toBeInTheDocument();
    expect(screen.getByText("1.8 %")).toBeInTheDocument();
  });

  it("muestra la variación vs periodo anterior: conteos en % y engagement en pts", async () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue(COMPARAR);
    renderConProviders(<Kpis total={TOTAL} marcaActual={MARCA_TODAS} rangoActual="mes" />);

    // Conteo (vistas 100→139): variación relativa con signo.
    expect(await screen.findByText("+39.0 %")).toBeInTheDocument();
    // Engagement (2.0 %→2.4 %): diferencia en PUNTOS; la variación relativa del
    // porcentaje ("+20.0 %") es engañosa para un ratio y no se muestra jamás.
    expect(screen.getByText("+0.4 pts")).toBeInTheDocument();
    expect(screen.queryByText(/\+20/)).not.toBeInTheDocument();
    // El tooltip explica contra qué se compara (etiqueta del periodo A).
    expect(screen.getAllByTitle("vs periodo anterior (Periodo anterior)").length).toBeGreaterThan(0);
    // A = periodo inmediatamente anterior adyacente; B = el periodo visible.
    const { rango_a = "", rango_b = "" } = espia.mock.calls[0][0];
    expect(rango_b).toBe("mes");
    expect(rango_a).toMatch(/^rango:\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}$/);
  });

  it("marca como 'Nuevo' el crecimiento desde cero (a=0, b>0) en vez de '0.0 %'", async () => {
    vi.spyOn(api, "metricasComparar").mockResolvedValue(COMPARAR);
    renderConProviders(<Kpis total={TOTAL} marcaActual={MARCA_TODAS} rangoActual="mes" />);

    expect(await screen.findByText("Nuevo")).toBeInTheDocument();
    expect(screen.queryByText("0.0 %")).not.toBeInTheDocument();
  });

  it("mes EN CURSO: compara los días transcurridos con los mismos días del mes anterior", async () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue({
      ...COMPARAR,
      rango_a: "rango:2026-05-01_2026-05-10",
      rango_b: "rango:2026-06-01_2026-06-10",
      etiqueta_a: "1 may – 10 may 2026",
      etiqueta_b: "1 jun – 10 jun 2026",
    });
    renderConProviders(
      <Kpis total={TOTAL} marcaActual={MARCA_TODAS} rangoActual="mes:2026-06" />,
    );

    expect(await screen.findByText("+39.0 %")).toBeInTheDocument();
    // NUNCA 10 días contra los 31 de mayo: tramos de la MISMA duración (1–10 vs 1–10).
    const { rango_a = "", rango_b = "" } = espia.mock.calls[0][0];
    expect(rango_b).toBe("rango:2026-06-01_2026-06-10");
    expect(rango_a).toBe("rango:2026-05-01_2026-05-10");
    // El contexto es visible (leyenda) y accesible (tooltip de la insignia).
    expect(
      screen.getByText(/Periodo en curso: las variaciones comparan los días transcurridos/),
    ).toBeInTheDocument();
    expect(
      screen.getAllByTitle(/Periodo en curso: se comparan los días transcurridos/).length,
    ).toBeGreaterThan(0);
  });

  it("mes CERRADO: compara contra los primeros N días del mes anterior, sin leyenda de en curso", async () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue({
      ...COMPARAR,
      rango_a: "rango:2026-03-01_2026-03-30",
      rango_b: "mes:2026-04",
      etiqueta_a: "1 mar – 30 mar 2026",
      etiqueta_b: "Abril 2026",
    });
    renderConProviders(
      <Kpis total={TOTAL} marcaActual={MARCA_TODAS} rangoActual="mes:2026-04" />,
    );

    expect(await screen.findByText("+39.0 %")).toBeInTheDocument();
    // Abril (30 d) vs 1–30 de marzo: misma duración, nunca 30 vs 31 días.
    const { rango_a = "", rango_b = "" } = espia.mock.calls[0][0];
    expect(rango_b).toBe("mes:2026-04");
    expect(rango_a).toBe("rango:2026-03-01_2026-03-30");
    expect(screen.queryByText(/Periodo en curso/)).not.toBeInTheDocument();
    expect(
      screen.getAllByTitle("vs periodo anterior (1 mar – 30 mar 2026)").length,
    ).toBeGreaterThan(0);
  });

  it("semana CERRADA: compara contra la semana natural anterior (7 vs 7 días)", async () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue(COMPARAR);
    renderConProviders(
      <Kpis total={TOTAL} marcaActual={MARCA_TODAS} rangoActual="semana_cerrada" />,
    );

    expect(await screen.findByText("+39.0 %")).toBeInTheDocument();
    // Hoy mié 10 jun → semana cerrada = 1–7 jun; anterior = 25–31 may (7 días).
    const { rango_a = "", rango_b = "" } = espia.mock.calls[0][0];
    expect(rango_b).toBe("semana_cerrada");
    expect(rango_a).toBe("rango:2026-05-25_2026-05-31");
    expect(screen.queryByText(/Periodo en curso/)).not.toBeInTheDocument();
  });

  it("mes FUTURO (sin datos): ni insignias ni consulta — nunca un porcentaje espurio", () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue(COMPARAR);
    renderConProviders(
      <Kpis total={TOTAL} marcaActual={MARCA_TODAS} rangoActual="mes:2026-07" />,
    );

    expect(screen.getByText("Vistas")).toBeInTheDocument();
    expect(screen.queryByText("+39.0 %")).not.toBeInTheDocument();
    expect(screen.queryByText(/pts/)).not.toBeInTheDocument();
    expect(espia).not.toHaveBeenCalled();
  });

  it("sin rangoActual: pinta los KPIs sin insignias y NO consulta la comparativa", () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue(COMPARAR);
    renderConProviders(<Kpis total={TOTAL} />);

    // Los KPIs nunca se bloquean por el delta: se ven igual que siempre.
    expect(screen.getByText("Vistas")).toBeInTheDocument();
    expect(screen.getByText("950")).toBeInTheDocument();
    // Ninguna insignia: ni variación, ni puntos, ni "Nuevo" (el "1.8 %" del KPI
    // de engagement es el VALOR, no un badge).
    expect(screen.queryByText("+39.0 %")).not.toBeInTheDocument();
    expect(screen.queryByText(/pts/)).not.toBeInTheDocument();
    expect(screen.queryByText("Nuevo")).not.toBeInTheDocument();
    expect(espia).not.toHaveBeenCalled();
  });
});
