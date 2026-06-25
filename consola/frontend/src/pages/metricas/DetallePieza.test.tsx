import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { HistoricoPieza, PiezaConImpulso, PiezaMetrica } from "@/types";

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
  alcance: 9000,
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

    // Título + desglose granular (me gusta presentes; clics nulos -> "—").
    expect(screen.getByText("Reel viral")).toBeInTheDocument();
    expect(screen.getByText("Me gusta")).toBeInTheDocument();
    // Alcance único (solo Meta lo mide): se pinta con su valor.
    expect(screen.getByText("Alcance único")).toBeInTheDocument();
    // Transparencia de "Vistas": en Meta (instagram) la nota aclara que excluye repeticiones.
    expect(
      screen.getByRole("button", { name: /no incluye repeticiones \(loops\)/i }),
    ).toBeInTheDocument();
    // KPIs de velocidad aparecen tras cargar el histórico.
    expect(await screen.findByText("% en las primeras 24 h")).toBeInTheDocument();
    expect(screen.getByText("Mediciones")).toBeInTheDocument();
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
      await screen.findByText(/sin histórico todavía/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("% en las primeras 24 h")).not.toBeInTheDocument();
  });

  it("en TikTok la nota de Vistas es genérica (no afirma el matiz de loops de Meta)", async () => {
    vi.spyOn(api, "metricasPiezaHistorico").mockResolvedValue(SIN_HISTORICO);
    renderConProviders(
      <DetallePieza
        pieza={{ ...PIEZA, plataforma: "tiktok" }}
        abierto
        onOpenChange={() => {}}
      />,
    );

    // Nota honesta genérica para redes no-Meta; NO afirma "repeticiones (loops)".
    expect(
      screen.getByRole("button", { name: /la definición de vistas\/reproducciones varía por red/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /repeticiones \(loops\)/i }),
    ).not.toBeInTheDocument();
  });

  it("no consulta el histórico mientras el modal está cerrado", () => {
    const espia = vi.spyOn(api, "metricasPiezaHistorico");
    renderConProviders(
      <DetallePieza pieza={PIEZA} abierto={false} onOpenChange={() => {}} />,
    );
    expect(espia).not.toHaveBeenCalled();
  });

  it("muestra el bloque de impulso e inversión cuando la fuente trae los granulares", () => {
    vi.spyOn(api, "metricasPiezaHistorico").mockResolvedValue(SIN_HISTORICO);
    const conImpulso: PiezaConImpulso = {
      ...PIEZA,
      impresiones: 50000,
      impresiones_pagadas: 30000,
      impresiones_organicas: 20000,
      gasto: 12.5,
      // fracción 0–1: se pinta como porcentaje (×100).
      tasa_visionado_completo: 0.42,
      marcadores: 17,
    };
    renderConProviders(
      <DetallePieza pieza={conImpulso} abierto onOpenChange={() => {}} />,
    );

    expect(screen.getByText("Impulso e inversión")).toBeInTheDocument();
    // El operador ve el reparto pagado/orgánico, el gasto, el visionado y los marcadores.
    expect(screen.getByText("Impresiones pagadas")).toBeInTheDocument();
    expect(screen.getByText("30,000")).toBeInTheDocument();
    expect(screen.getByText("Impresiones orgánicas")).toBeInTheDocument();
    expect(screen.getByText("20,000")).toBeInTheDocument();
    expect(screen.getByText("Gasto")).toBeInTheDocument();
    expect(screen.getByText("Visionado completo")).toBeInTheDocument();
    expect(screen.getByText("42.0 %")).toBeInTheDocument();
    expect(screen.getByText("Marcadores")).toBeInTheDocument();
    expect(screen.getByText("17")).toBeInTheDocument();
  });

  it("pinta '—' en un granular de impulso que viene null (no un 0 falso)", () => {
    vi.spyOn(api, "metricasPiezaHistorico").mockResolvedValue(SIN_HISTORICO);
    const conGastoNulo: PiezaConImpulso = { ...PIEZA, impresiones: 50000, gasto: null };
    renderConProviders(
      <DetallePieza pieza={conGastoNulo} abierto onOpenChange={() => {}} />,
    );

    // El gasto viene en la respuesta pero es null: su celda muestra "—", no "$0".
    const celdaGasto = screen.getByText("Gasto").closest("div")!;
    expect(within(celdaGasto).getByText("—")).toBeInTheDocument();
  });

  it("oculta el bloque de impulso cuando la pieza no trae esos granulares", () => {
    vi.spyOn(api, "metricasPiezaHistorico").mockResolvedValue(SIN_HISTORICO);
    renderConProviders(
      <DetallePieza pieza={PIEZA} abierto onOpenChange={() => {}} />,
    );

    expect(screen.queryByText("Impulso e inversión")).not.toBeInTheDocument();
  });
});
