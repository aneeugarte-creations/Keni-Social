import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { AnaliticaPiezas, PiezaMetrica } from "@/types";

import { TraficoWeb } from "./TraficoWeb";

const MARCAS = [{ id: "unotv", nombre: "UnoTV" }];

const BASE: PiezaMetrica = {
  id: "p1",
  plataforma: "facebook",
  titulo: "Nota con enlace",
  publicado: "2026-05-27",
  visualizaciones: 50000,
  interacciones: 2000,
  engagement_pct: 4,
  url: "https://unotv.com/nota",
  likes: null,
  comentarios: null,
  compartidos: null,
  guardados: null,
  video_views: null,
  tiempo_medio_vis_s: null,
  clics_enlace: 1200,
  formato: "link",
  cuenta: "unotv",
  rendimiento_relativo: null,
};

function resp(top: PiezaMetrica[], peores: PiezaMetrica[] = []): AnaliticaPiezas {
  const est = { n: 0, media: 0, mediana: 0, p25: 0, p75: 0, minimo: 0, maximo: 0, desviacion: 0 };
  return {
    cuenta: null,
    rango: "semana",
    etiqueta_rango: "Últimos 7 días",
    periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
    total: top.length + peores.length,
    fuente: "muestra",
    engagement: est,
    visualizaciones: est,
    top,
    peores,
    distribucion: [],
    generado_en: "2026-06-02T00:00:00",
  };
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("TraficoWeb", () => {
  it("rankea las piezas por clics a enlace y enlaza al post real", async () => {
    const masClics: PiezaMetrica = { ...BASE, id: "p2", titulo: "La más clicada", clics_enlace: 5000 };
    vi.spyOn(api, "metricasPiezas").mockResolvedValue(resp([BASE], [masClics]));
    renderConProviders(
      <TraficoWeb marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    // El título enlaza al post (nueva pestaña).
    const enlace = await screen.findByRole("link", { name: /La más clicada/ });
    expect(enlace).toHaveAttribute("href", "https://unotv.com/nota");
    expect(enlace).toHaveAttribute("target", "_blank");

    // Orden por clics desc: "La más clicada" (5000) antes que "Nota con enlace" (1200).
    const filas = screen.getAllByRole("row").filter((f) => f.querySelector("a, td"));
    const idxMas = filas.findIndex((f) => f.textContent?.includes("La más clicada"));
    const idxBase = filas.findIndex((f) => f.textContent?.includes("Nota con enlace"));
    expect(idxMas).toBeGreaterThanOrEqual(0);
    expect(idxMas).toBeLessThan(idxBase);
  });

  it("muestra un vacío honesto cuando ninguna pieza trae clics", async () => {
    const sinClics: PiezaMetrica = { ...BASE, clics_enlace: null };
    vi.spyOn(api, "metricasPiezas").mockResolvedValue(resp([sinClics]));
    renderConProviders(
      <TraficoWeb marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    expect(
      await screen.findByText(/Ninguna pieza del periodo reporta clics a enlace/i),
    ).toBeInTheDocument();
  });
});
