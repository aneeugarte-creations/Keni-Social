import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { HistoricoPieza, PiezaMetrica } from "@/types";

import { DetallePieza } from "./DetallePieza";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const PIEZA: PiezaMetrica = {
  id: "p1",
  plataforma: "instagram",
  titulo: "Reel viral",
  publicado: "2026-05-20",
  visualizaciones: 12000,
  interacciones: 600,
  engagement_pct: 5,
  url: "https://instagram.com/p/abc",
  likes: 500,
  comentarios: 60,
  compartidos: 30,
  guardados: 10,
  video_views: 11000,
  tiempo_medio_vis_s: 18,
  clics_enlace: null,
  formato: "reel",
  cuenta: "unotv",
  rendimiento_relativo: 2.3,
};

const CON_HISTORICO: HistoricoPieza = {
  pieza_id: "p1",
  puntos: [
    {
      ts: "2026-05-20T10:00:00",
      visualizaciones: 4000,
      interacciones: 200,
      engagement_pct: 5,
      alcance: 3800,
      likes: 150,
      comentarios: 20,
      compartidos: 10,
      guardados: 5,
      video_views: 3700,
      tiempo_medio_vis_s: 15,
      clics_enlace: 0,
    },
    {
      ts: "2026-05-22T10:00:00",
      visualizaciones: 12000,
      interacciones: 600,
      engagement_pct: 5,
      alcance: 11000,
      likes: 500,
      comentarios: 60,
      compartidos: 30,
      guardados: 10,
      video_views: 11000,
      tiempo_medio_vis_s: 18,
      clics_enlace: 0,
    },
  ],
  velocidad: {
    pct_en_primeras_24h: 33.3,
    delta_medio_por_dia: 4000,
    n_snapshots: 2,
  },
};

const SIN_HISTORICO: HistoricoPieza = { pieza_id: "p1", puntos: [], velocidad: null };

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DetallePieza", () => {
  it("muestra métricas, granulares y KPIs de velocidad cuando hay histórico", async () => {
    vi.spyOn(api, "metricasPiezaHistorico").mockResolvedValue(CON_HISTORICO);
    renderConProviders(
      <DetallePieza pieza={PIEZA} abierto onOpenChange={() => {}} />,
    );

    // Título + desglose granular (likes presentes; clics nulos -> "—").
    expect(screen.getByText("Reel viral")).toBeInTheDocument();
    expect(screen.getByText("Likes")).toBeInTheDocument();
    // KPIs de velocidad aparecen tras cargar el histórico.
    expect(await screen.findByText("En 24 h")).toBeInTheDocument();
    expect(screen.getByText("Snapshots")).toBeInTheDocument();
    expect(
      screen.queryByText(/sin histórico todavía/i),
    ).not.toBeInTheDocument();
  });

  it("dice honestamente 'sin histórico todavía' cuando no hay puntos", async () => {
    vi.spyOn(api, "metricasPiezaHistorico").mockResolvedValue(SIN_HISTORICO);
    renderConProviders(
      <DetallePieza pieza={PIEZA} abierto onOpenChange={() => {}} />,
    );

    expect(
      await screen.findByText(/sin histórico todavía \(esta pieza aún no se está siguiendo\)/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("En 24 h")).not.toBeInTheDocument();
  });

  it("no consulta el histórico mientras el modal está cerrado", () => {
    const espia = vi.spyOn(api, "metricasPiezaHistorico");
    renderConProviders(
      <DetallePieza pieza={PIEZA} abierto={false} onOpenChange={() => {}} />,
    );
    expect(espia).not.toHaveBeenCalled();
  });
});
