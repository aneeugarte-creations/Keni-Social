import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { PiezaListado, PiezasListado } from "@/types";

import { COLOR_RED } from "./coloresRed";
import { EvolucionRedes, etiquetaIntervalo, granularidadParaSpan } from "./EvolucionRedes";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

function pieza(over: Partial<PiezaListado>): PiezaListado {
  return {
    id: "p1",
    plataforma: "facebook",
    titulo: "Pieza A",
    publicado: "2026-06-01",
    visualizaciones: 1000,
    interacciones: 50,
    engagement_pct: 5,
    url: null,
    likes: null,
    comentarios: null,
    compartidos: null,
    guardados: null,
    video_views: null,
    tiempo_medio_vis_s: null,
    clics_enlace: null,
    formato: null,
    cuenta: null,
    rendimiento_relativo: null,
    linea: null,
    ...over,
  };
}

function resp(piezas: PiezaListado[]): PiezasListado {
  return {
    rango: "mes",
    etiqueta_rango: "Últimos 30 días",
    marca: "",
    periodo: { desde: "2026-05-03", hasta: "2026-06-10" },
    fuente: "muestra",
    piezas,
    total: piezas.length,
    generado_en: "2026-06-10T00:00:00",
  };
}

// 2 redes con un span de 10 días → granularidad "día".
const DOS_REDES: PiezaListado[] = [
  pieza({ id: "a", plataforma: "facebook", publicado: "2026-06-01", visualizaciones: 1000 }),
  pieza({ id: "b", plataforma: "instagram", publicado: "2026-06-05", visualizaciones: 2000 }),
  pieza({ id: "c", plataforma: "facebook", publicado: "2026-06-10", visualizaciones: 500 }),
];

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("granularidadParaSpan", () => {
  it("adapta el intervalo al span real: día ≤45, semana ≤180, mes después", () => {
    expect(granularidadParaSpan(45)).toBe("dia");
    expect(granularidadParaSpan(46)).toBe("semana");
    expect(granularidadParaSpan(180)).toBe("semana");
    expect(granularidadParaSpan(181)).toBe("mes");
  });
});

describe("etiquetaIntervalo", () => {
  it("mes → «Jun 2026» (capitalizado, sin punto)", () => {
    expect(etiquetaIntervalo(new Date(2026, 5, 1, 12), "mes")).toBe("Jun 2026");
  });

  it("semana → «Sem del 1 jun»", () => {
    expect(etiquetaIntervalo(new Date(2026, 5, 1, 12), "semana")).toBe("Sem del 1 jun");
  });

  it("día → «1 jun»", () => {
    expect(etiquetaIntervalo(new Date(2026, 5, 1, 12), "dia")).toBe("1 jun");
  });
});

describe("EvolucionRedes", () => {
  it("ofrece una alternativa textual del chart (role=img con intervalos, granularidad y redes)", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(DOS_REDES));
    renderConProviders(<EvolucionRedes marcaActual="__todas__" rangoActual="mes" />);

    // Span de 10 días → 10 intervalos por día; las redes con su nombre LEGIBLE.
    const img = await screen.findByRole("img", { name: /Vistas por red/ });
    expect(img).toHaveAttribute(
      "aria-label",
      "Vistas por red en 10 intervalos por día: redes Facebook, Instagram",
    );
  });

  it("los swatches de la leyenda usan los hex canónicos de COLOR_RED (fuente única)", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(DOS_REDES));
    renderConProviders(<EvolucionRedes marcaActual="__todas__" rangoActual="mes" />);

    const leyendaFb = await screen.findByText("Facebook");
    const swatchFb = leyendaFb.querySelector("span");
    expect(swatchFb).not.toBeNull();
    expect(swatchFb).toHaveStyle({ backgroundColor: COLOR_RED.facebook });

    const swatchIg = screen.getByText("Instagram").querySelector("span");
    expect(swatchIg).toHaveStyle({ backgroundColor: COLOR_RED.instagram });
  });

  it("dice con honestidad cuando no hay piezas en el periodo", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp([]));
    renderConProviders(<EvolucionRedes marcaActual="__todas__" rangoActual="mes" />);

    expect(
      await screen.findByText(/Aún no hay piezas publicadas en este periodo/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
