import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
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
  it("pinta los hallazgos multi-dimensión con las cifras compactadas", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Análisis del periodo")).toBeInTheDocument();
    // El título de sección se pinta durante la carga; espera al dato para el resto.
    // Porcentaje con decimal → entero; un millar pequeño (4.400, <10.000) se queda tal cual.
    expect(
      await screen.findByText(/Claro Sports subió \+39% en vistas \(4\.400 en el periodo\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/TikTok fue la red que más aportó/)).toBeInTheDocument();
    // Cifra grande dentro de la prosa compactada al estilo de la app (12.400 → "12.4 k").
    expect(
      screen.getByText(/El 15-jun Instagram perdió 12\.4 k seguidores/),
    ).toBeInTheDocument();
  });

  it("enlaza la pieza que respalda un hallazgo en la línea ↳, sin «La explica»", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    // Red LEGIBLE ("TikTok", no "tiktok") y engagement redondeado a entero.
    expect(await screen.findByText(/TikTok · 6% eng\./)).toBeInTheDocument();
    expect(screen.queryByText(/La explica:/)).not.toBeInTheDocument();
    // Un título mixto normal no dispara el des-gritado: conserva su acrónimo ("MX").
    const enlace = screen.getByRole("link", { name: /Final de la Liga MX/ });
    expect(enlace).toHaveAttribute("href", "https://www.tiktok.com/@clarosports/video/1");
    // El título íntegro sobrevive en el `title` del enlace.
    expect(screen.getByTitle("Final de la Liga MX")).toBeInTheDocument();
  });

  it("baja a frase un título de pieza que viene gritado, sin tocar las palabras mixtas", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({
      ...RESP,
      hallazgos: [
        {
          ...RESP.hallazgos[0],
          pieza: {
            ...RESP.hallazgos[0].pieza!,
            titulo: '¡GOLAZO DE ÚLTIMA HORA! Con "And I Love Her" de fondo',
          },
        },
      ],
    });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/«¡Golazo de última hora! Con "And I Love Her" de fondo»/),
    ).toBeInTheDocument();
  });

  it("pliega la lista a los 3 primeros hallazgos y despliega el resto con el «…»", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({
      ...RESP,
      hallazgos: [
        ...RESP.hallazgos,
        {
          dimension: "formato",
          texto: "El formato reel se guarda o comparte al 4% de sus vistas.",
          direccion: "sube",
          pieza: null,
        },
        {
          dimension: "engagement",
          texto: "El formato link fue el de mejor engagement del periodo.",
          direccion: "sube",
          pieza: null,
        },
        {
          dimension: "periodo",
          texto: "El día más fuerte de la semana fue el 5-jul.",
          direccion: "estable",
          pieza: null,
        },
      ],
    });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    // Plegado: los 3 primeros a la vista; el resto, detrás del "…".
    expect(await screen.findByText(/Claro Sports subió/)).toBeInTheDocument();
    expect(screen.getByText(/Instagram perdió/)).toBeInTheDocument();
    expect(screen.queryByText(/El formato reel/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /3 hallazgos más/ }));
    expect(screen.getByText(/El formato reel/)).toBeInTheDocument();
    expect(screen.getByText(/El día más fuerte de la semana/)).toBeInTheDocument();

    // Y se puede volver a plegar.
    fireEvent.click(screen.getByRole("button", { name: /mostrar menos/i }));
    expect(screen.queryByText(/El formato reel/)).not.toBeInTheDocument();
  });

  it("no pliega cuando apenas escondería 1 hallazgo", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({
      ...RESP,
      hallazgos: [
        ...RESP.hallazgos,
        {
          dimension: "formato",
          texto: "El formato reel despunta este periodo.",
          direccion: "sube",
          pieza: null,
        },
      ],
    });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText(/El formato reel despunta/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /hallazgos más/ })).not.toBeInTheDocument();
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
