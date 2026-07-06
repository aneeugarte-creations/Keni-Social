import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { AnalisisDiario } from "@/types";

import { AnalisisNarrativo } from "./AnalisisNarrativo";

const RESP: AnalisisDiario = {
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  marca: "",
  fuente: "metricool",
  hallazgos: [
    {
      dimension: "vistas",
      texto: "Claro Sports subió +39.0% en vistas (4.400 en el periodo), con 1.8% de engagement.",
      direccion: "sube",
      pieza: {
        titulo: "Final de la Liga MX",
        plataforma: "tiktok",
        engagement_pct: 6.2,
        url: "https://www.tiktok.com/@clarosports/video/1",
      },
    },
    {
      dimension: "red",
      texto: "TikTok fue la red que más aportó: 62% de las vistas del periodo (18.500.000).",
      direccion: "estable",
      pieza: null,
    },
    {
      dimension: "seguidores",
      texto:
        "El 15-jun Instagram perdió 12.400 seguidores, muy por encima del ritmo diario habitual del periodo.",
      direccion: "baja",
      pieza: null,
    },
  ],
  cobertura_parcial: [],
  siguiente_paso: {
    marca_id: "claro_sports",
    marca: "Claro Sports",
    engagement_pct: 6.2,
    pieza: {
      titulo: "Final de la Liga MX",
      plataforma: "tiktok",
      engagement_pct: 6.2,
      url: "https://www.tiktok.com/@clarosports/video/1",
    },
    texto: "Replica el formato de la pieza ganadora esta semana.",
  },
  generado_en: "2026-06-09T00:00:00",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("AnalisisNarrativo", () => {
  it("pinta los hallazgos multi-dimensión como frases completas del backend", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Análisis del periodo")).toBeInTheDocument();
    // El título de sección se pinta durante la carga; espera al dato para el resto.
    expect(
      await screen.findByText(/Claro Sports subió \+39\.0% en vistas/),
    ).toBeInTheDocument();
    // Dimensión de red y de seguidores (señal representativa), tal cual las redacta el backend.
    expect(screen.getByText(/TikTok fue la red que más aportó/)).toBeInTheDocument();
    expect(
      screen.getByText(/El 15-jun Instagram perdió 12\.400 seguidores/),
    ).toBeInTheDocument();
  });

  it("enlaza la pieza que explica un hallazgo, con su red legible", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText(/La explica:/)).toBeInTheDocument();
    // Red LEGIBLE ("TikTok", no "tiktok").
    expect(screen.getByText(/TikTok · 6\.2 % de engagement/)).toBeInTheDocument();
    const enlace = screen.getByRole("link", { name: /Final de la Liga MX/i });
    expect(enlace).toHaveAttribute("href", "https://www.tiktok.com/@clarosports/video/1");
  });

  it("pinta el siguiente paso tal cual lo redacta el backend, con enlace a la pieza", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText("Replica el formato de la pieza ganadora esta semana."),
    ).toBeInTheDocument();
    expect(screen.getByText("Siguiente paso")).toBeInTheDocument();
    const enlace = screen.getByRole("link", { name: /ver la pieza/i });
    expect(enlace).toHaveAttribute("href", "https://www.tiktok.com/@clarosports/video/1");
  });

  it("dice con honestidad cuando no hay datos suficientes", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({
      ...RESP,
      hallazgos: [],
      siguiente_paso: null,
    });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/sin datos suficientes para una lectura del periodo/i),
    ).toBeInTheDocument();
  });

  it("avisa de cobertura parcial sin romper", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({
      ...RESP,
      cobertura_parcial: ["UnoTV"],
    });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText(/Datos parciales de: UnoTV/)).toBeInTheDocument();
  });

  it("avisa sin romper cuando la API falla", async () => {
    vi.spyOn(api, "metricasAnalisis").mockRejectedValue(new Error("boom"));
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText("No se pudo cargar el análisis del periodo."),
    ).toBeInTheDocument();
  });
});
