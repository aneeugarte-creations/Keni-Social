import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
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
      texto: "Claro Sports sumó 4.400 vistas frente al periodo anterior.",
      direccion: "sube",
      cifra: "+39.0%",
      etiqueta: "vistas",
      grupo: "positivo",
      pieza: {
        titulo: "Final de la Liga MX",
        plataforma: "tiktok",
        engagement_pct: 6.2,
        url: "https://www.tiktok.com/@clarosports/video/1",
      },
    },
    {
      dimension: "seguidores",
      texto:
        "Instagram perdió seguidores el 15-jun, muy por encima del ritmo diario habitual del periodo.",
      direccion: "baja",
      cifra: "-12.400",
      etiqueta: "seguidores",
      grupo: "vigilar",
      pieza: null,
    },
    {
      dimension: "red",
      texto: "TikTok concentró el 62% de las vistas del periodo (18.500.000).",
      direccion: "estable",
      cifra: null,
      etiqueta: null,
      grupo: "contexto",
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
    texto:
      "Claro Sports tuvo el mejor rendimiento del periodo, con 6.2% de engagement; su pieza más destacada fue «Final de la Liga MX» en TikTok. Si quieren dar continuidad a esa línea, pueden pedir a Claude un copy o un clip de referencia. Qué publicar y cuándo es decisión del equipo.",
  },
  generado_en: "2026-06-09T00:00:00",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("AnalisisNarrativo", () => {
  it("reparte los hallazgos por grupo: positivos a «Qué funcionó», negativos a «Qué vigilar»", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Análisis del periodo")).toBeInTheDocument();
    const funciono = await screen.findByRole("region", { name: "Qué funcionó" });
    expect(within(funciono).getByText(/Claro Sports sumó 4\.400 vistas/)).toBeInTheDocument();
    const vigilar = screen.getByRole("region", { name: "Qué vigilar" });
    expect(within(vigilar).getByText(/Instagram perdió seguidores el 15-jun/)).toBeInTheDocument();
  });

  it("pinta la cifra ancla con su micro-etiqueta, compactada al estilo de la app", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    // "+39.0%" → "+39%" (porcentaje a entero) y "-12.400" → "-12.4 k" (miles compactos).
    expect(await screen.findByText("+39%")).toBeInTheDocument();
    expect(screen.getByText("vistas")).toBeInTheDocument();
    expect(screen.getByText("-12.4 k")).toBeInTheDocument();
    expect(screen.getByText("seguidores")).toBeInTheDocument();
  });

  it("agrupa los hallazgos sin valencia en la franja de contexto, con las cifras compactadas", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByText("Contexto")).toBeInTheDocument();
    // 18.500.000 → "18.5 M" dentro de la prosa del contexto.
    expect(
      screen.getByText(/TikTok concentró el 62% de las vistas del periodo \(18\.5 M\)/),
    ).toBeInTheDocument();
  });

  it("enlaza la pieza que respalda un hallazgo en la línea ↳, con su red legible", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    // Red LEGIBLE ("TikTok", no "tiktok") y engagement redondeado a entero.
    expect(await screen.findByText(/TikTok · 6% eng\./)).toBeInTheDocument();
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

  it("oculta la columna «Qué vigilar» cuando no hay hallazgos negativos", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue({
      ...RESP,
      hallazgos: RESP.hallazgos.filter((h) => h.grupo !== "vigilar"),
    });
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(await screen.findByRole("region", { name: "Qué funcionó" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Qué vigilar" })).not.toBeInTheDocument();
  });

  it("pinta el siguiente paso tal cual lo redacta el backend, con enlace a la pieza", async () => {
    vi.spyOn(api, "metricasAnalisis").mockResolvedValue(RESP);
    renderConProviders(<AnalisisNarrativo marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/Claro Sports tuvo el mejor rendimiento del periodo/),
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
