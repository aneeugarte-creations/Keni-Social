import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { Crosstab as CrosstabResp } from "@/types";

import { Crosstab } from "./Crosstab";

// Tremor/recharts no se usan aquí, pero jsdom no implementa ResizeObserver: lo stubbeamos
// por seguridad para cualquier hijo que lo requiera al montar.
beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

// Catálogo de marcas {id, nombre} para resolver el id crudo de cada celda.
const MARCAS = [
  { id: "unotv", nombre: "UnoTV" },
  { id: "claro_sports", nombre: "Claro Sports" },
];

// `marca`/`red`/`formato` llegan como IDS CRUDOS de la fuente.
const RESP: CrosstabResp = {
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  celdas: [
    {
      marca: "unotv",
      red: "instagram",
      formato: "feed_image",
      n_piezas: 12,
      visualizaciones: 120000,
      interacciones: 8000,
      engagement_pct: 6.7,
      rendimiento_relativo_medio: 1.4,
    },
    {
      marca: "claro_sports",
      red: "x",
      formato: null,
      n_piezas: 5,
      visualizaciones: 30000,
      interacciones: 900,
      engagement_pct: 3.0,
      rendimiento_relativo_medio: 0.6,
    },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("Crosstab (rendimiento por formato)", () => {
  it("pinta las celdas marca×red×formato LEGIBLES con su rendimiento relativo", async () => {
    vi.spyOn(api, "metricasCrosstab").mockResolvedValue(RESP);
    renderConProviders(
      <Crosstab marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    // marca (unotv → "UnoTV"), red (instagram → "Instagram"), formato (feed_image → "Feed image").
    // Cada marca/red aparece varias veces: el cruce pinta TODAS las redes canónicas por marca
    // (la fila real + las filas "—"), así que usamos getAllByText para los nombres.
    expect((await screen.findAllByText("UnoTV")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Claro Sports").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Instagram").length).toBeGreaterThan(0);
    expect(screen.getByText("Feed image")).toBeInTheDocument();
    // no muestra ids crudos.
    expect(screen.queryByText("unotv")).not.toBeInTheDocument();
    expect(screen.queryByText("feed_image")).not.toBeInTheDocument();
    // formato null se muestra como "Sin formato".
    expect(screen.getByText("Sin formato")).toBeInTheDocument();
    // rendimiento relativo formateado con sufijo "×" (rendimientoRel, 1 decimal).
    expect(screen.getByText("1.4×")).toBeInTheDocument();
    expect(screen.getByText("0.6×")).toBeInTheDocument();
    // la celda de Vistas muestra el número COMPLETO (no compacto).
    expect(screen.getByText("120,000")).toBeInTheDocument();
    expect(screen.getByText("30,000")).toBeInTheDocument();
  });

  it("ordena por rendimiento desc por defecto y permite reordenar por otra columna", async () => {
    vi.spyOn(api, "metricasCrosstab").mockResolvedValue(RESP);
    renderConProviders(
      <Crosstab marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    // Orden por defecto = rendimiento desc: la celda de UnoTV (1.4×) va antes que la de
    // Claro Sports (0.6×).
    await screen.findAllByText("UnoTV");
    // Solo las filas CON datos (rendimiento "×"); las filas "—" canónicas van al final y no
    // deben contar para el aserto de orden.
    const filasDatos = () =>
      screen
        .getAllByRole("row")
        .filter((f) => within(f).queryByText(/UnoTV|Claro Sports/) && within(f).queryByText(/×/));
    expect(within(filasDatos()[0]).getByText("UnoTV")).toBeInTheDocument();

    // Reordenar por Piezas asc (Claro Sports tiene 5 piezas, UnoTV 12): clic = desc, otro = asc.
    const cabPiezas = screen.getByRole("button", { name: /Piezas/ });
    fireEvent.click(cabPiezas); // desc -> UnoTV (12) primero
    fireEvent.click(cabPiezas); // asc -> Claro Sports (5) primero
    expect(within(filasDatos()[0]).getByText("Claro Sports")).toBeInTheDocument();
    expect(cabPiezas.closest("th")).toHaveAttribute("aria-sort", "ascending");
  });

  it("muestra un vacío honesto cuando la fuente no expone celdas", async () => {
    vi.spyOn(api, "metricasCrosstab").mockResolvedValue({ ...RESP, celdas: [] });
    renderConProviders(
      <Crosstab marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    expect(
      await screen.findByText(/Aún no hay cruce por formato para este periodo/i),
    ).toBeInTheDocument();
  });
});
