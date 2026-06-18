import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { PiezaListado, PiezasListado } from "@/types";

import { PanoramaPiezas, ticksLog, yLog } from "./PanoramaPiezas";

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
    alcance: null,
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
    rango: "2025-06-11_2026-06-10",
    etiqueta_rango: "Periodo personalizado",
    marca: "",
    periodo: { desde: "2025-06-11", hasta: "2026-06-10" },
    fuente: "muestra",
    piezas,
    total: piezas.length,
    generado_en: "2026-06-10T00:00:00",
  };
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("yLog", () => {
  it("aplica el suelo en 1: 0 vistas no rompe la escala log (REGRESIÓN max(1, v))", () => {
    expect(yLog(0)).toBe(0);
    expect(yLog(1)).toBe(0);
    expect(yLog(1000)).toBe(3);
  });
});

describe("ticksLog", () => {
  it("potencias de 10 hasta cubrir el máximo de vistas", () => {
    expect(ticksLog(50000)).toEqual([0, 1, 2, 3, 4, 5]);
    // Mínimo dos ticks (0 y 1) aunque el máximo sea minúsculo.
    expect(ticksLog(5)).toEqual([0, 1]);
  });
});

describe("PanoramaPiezas", () => {
  it("avisa de las piezas con 0 vistas y ofrece la alternativa textual (role=img)", async () => {
    const piezas = [
      pieza({ id: "a", plataforma: "facebook", visualizaciones: 9000 }),
      pieza({ id: "b", plataforma: "instagram", visualizaciones: 0 }),
    ];
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(piezas));
    renderConProviders(<PanoramaPiezas marcaActual="__todas__" />);

    // La pieza con 0 vistas no se lee como "1 vista": la leyenda lo aclara.
    expect(await screen.findByText(/con 0 vistas se apoya/)).toBeInTheDocument();

    // Alternativa textual con DATOS: total y clave de lectura.
    const img = screen.getByRole("img", { name: /Panorama de 2 piezas del periodo/ });
    expect(img).toHaveAttribute(
      "aria-label",
      "Panorama de 2 piezas del periodo; cada punto es una pieza, altura = vistas, tamaño = engagement",
    );
  });

  it("sin piezas a 0 vistas no pinta el aviso", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(
      resp([pieza({ id: "a", visualizaciones: 9000 })]),
    );
    renderConProviders(<PanoramaPiezas marcaActual="__todas__" />);

    await screen.findByRole("img", { name: /Panorama de 1 pieza del periodo/ });
    expect(screen.queryByText(/con 0 vistas/)).not.toBeInTheDocument();
  });

  it("dice con honestidad cuando no hay piezas en el periodo", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp([]));
    renderConProviders(<PanoramaPiezas marcaActual="__todas__" />);

    expect(
      await screen.findByText(/Aún no hay piezas publicadas en este periodo/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
