import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { DesgloseInteracciones as DesgloseResp } from "@/types";

import { DesgloseInteracciones } from "./DesgloseInteracciones";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const MARCAS = [{ id: "unotv", nombre: "UnoTV" }];

// `marca`/`red` llegan como IDS CRUDOS de la fuente; la UI los resuelve a nombre.
const RESP: DesgloseResp = {
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  celdas: [
    {
      marca: "unotv",
      red: "instagram",
      likes: 5000,
      comentarios: 300,
      compartidos: 120,
      guardados: 80,
      video_views: 90000,
      interacciones: 5500,
      visualizaciones: 90000,
      engagement_pct: 6.1,
      n_piezas: 10,
    },
  ],
  totales: {
    likes: 5000,
    comentarios: 300,
    compartidos: 120,
    guardados: 80,
    video_views: 90000,
    n_piezas: 10,
  },
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DesgloseInteracciones", () => {
  it("muestra la tabla por marca×red LEGIBLE con la fila de totales", async () => {
    vi.spyOn(api, "metricasDesglose").mockResolvedValue(RESP);
    renderConProviders(
      <DesgloseInteracciones marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    // marca (unotv → "UnoTV") y red (instagram → "Instagram") legibles, no el id crudo.
    expect(await screen.findByText("UnoTV")).toBeInTheDocument();
    expect(screen.getAllByText("Instagram").length).toBeGreaterThan(0);
    expect(screen.queryByText("instagram")).not.toBeInTheDocument();
    // fila de totales.
    expect(screen.getByText("Total")).toBeInTheDocument();
    // valor sin compactar (comentarios = 300) presente en celda y total.
    expect(screen.getAllByText("300").length).toBeGreaterThan(0);
  });

  it("dice con honestidad cuando no hay celdas", async () => {
    vi.spyOn(api, "metricasDesglose").mockResolvedValue({ ...RESP, celdas: [] });
    renderConProviders(
      <DesgloseInteracciones marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    expect(await screen.findByText(/no expone el desglose/i)).toBeInTheDocument();
  });
});
