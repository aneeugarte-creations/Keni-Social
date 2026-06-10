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
  es_muestra: false,
  movimientos: [
    {
      marca_id: "claro_sports",
      marca: "Claro Sports",
      variacion_vis_pct: 39,
      direccion: "sube",
      visualizaciones: 4400,
      engagement_pct: 1.8,
      pieza: {
        titulo: "Final de la Liga MX",
        plataforma: "tiktok",
        engagement_pct: 6.2,
        url: "https://www.tiktok.com/@clarosports/video/1",
      },
    },
  ],
  movimientos_resto: 2,
  marcas_estables: 1,
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
  it("narra un movimiento al alza con la variación es-MX y la pieza con su red legible", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Qué cambió y por qué")).toBeInTheDocument();
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    // Variación formateada con `variacion()` (signo explícito + 1 decimal, es-MX).
    expect(screen.getByText(/subió \+39\.0 % en vistas/)).toBeInTheDocument();
    expect(screen.getByText(/4\.4 k vistas en el periodo/)).toBeInTheDocument();
    // La pieza que explica el movimiento, con su red LEGIBLE ("TikTok", no "tiktok").
    expect(screen.getByText(/La explica:/)).toBeInTheDocument();
    expect(screen.getByText(/TikTok · 6\.2 % de engagement/)).toBeInTheDocument();
    expect(screen.queryByText("tiktok")).not.toBeInTheDocument();
    // Pie con los movimientos menores y las marcas estables, pluralizados.
    expect(
      screen.getByText(/2 movimientos menores más · 1 marca estable/),
    ).toBeInTheDocument();
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

  it("marca con un badge cuando los datos son de muestra", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({ ...RESP, es_muestra: true });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Datos de muestra")).toBeInTheDocument();
  });

  it("muestra «Nuevo» (no «0.0 %») cuando una marca arranca desde base cero", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({
      ...RESP,
      movimientos: [
        {
          marca_id: "unotv",
          marca: "UnoTV",
          variacion_vis_pct: 0,
          direccion: "sube",
          visualizaciones: 250,
          engagement_pct: null,
          pieza: null,
        },
      ],
      siguiente_paso: null,
    });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Nuevo")).toBeInTheDocument();
    expect(screen.queryByText(/0\.0 %/)).not.toBeInTheDocument();
  });

  it("dice con honestidad cuando no hay movimientos destacables", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({
      ...RESP,
      movimientos: [],
      movimientos_resto: 0,
      marcas_estables: 2,
      siguiente_paso: null,
    });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/sin movimientos destacables en este periodo/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 marcas estables/)).toBeInTheDocument();
  });

  it("avisa sin romper cuando la API falla", async () => {
    vi.spyOn(api, "metricasAnalisis").mockRejectedValue(new Error("boom"));
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText("No se pudo cargar el análisis del periodo."),
    ).toBeInTheDocument();
  });
});
