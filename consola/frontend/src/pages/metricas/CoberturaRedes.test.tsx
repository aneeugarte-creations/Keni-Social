import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";

import type { MarcaCobertura } from "@/types";

import { CoberturaRedes } from "./CoberturaRedes";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

// Universo COMPLETO de redes de una marca, cada una con su estado y motivo (la
// auditoría siempre lista todas las redes medibles, aunque no aporten datos).
const MARCAS: MarcaCobertura[] = [
  {
    marca_id: "unotv",
    marca: "UnoTV",
    redes: [
      {
        red: "facebook",
        estado: "con_datos",
        visualizaciones: 120000,
        alcance: 110000,
        interacciones: 8000,
        engagement_pct: 6.7,
        stories: 12,
        motivo: "Respondió con métricas en el rango.",
      },
      {
        red: "instagram",
        estado: "sin_metricas",
        visualizaciones: null,
        alcance: null,
        interacciones: null,
        engagement_pct: null,
        stories: 5,
        motivo: "Conectada, pero sin métricas en el periodo.",
      },
      {
        red: "tiktok",
        estado: "sin_lectura",
        visualizaciones: null,
        alcance: null,
        interacciones: null,
        engagement_pct: null,
        stories: null,
        motivo: "No se pudo leer la red en Metricool.",
      },
      {
        red: "youtube",
        estado: "no_configurada",
        visualizaciones: null,
        alcance: null,
        interacciones: null,
        engagement_pct: null,
        stories: null,
        motivo: "La marca no tiene esta red dada de alta en Metricool.",
      },
      {
        red: "x",
        estado: "no_conectada",
        visualizaciones: null,
        alcance: null,
        interacciones: null,
        engagement_pct: null,
        stories: null,
        motivo: "Red no contratada en el piloto.",
      },
    ],
  },
  {
    marca_id: "claro_sports",
    marca: "Claro Sports",
    redes: [
      {
        red: "tiktok",
        estado: "con_datos",
        visualizaciones: 30000,
        alcance: 28000,
        interacciones: 900,
        engagement_pct: 3.0,
        stories: null,
        motivo: "Respondió con métricas en el rango.",
      },
    ],
  },
];

describe("CoberturaRedes", () => {
  it("pinta cada red LEGIBLE con su estado, motivo y conteo de cobertura por marca", () => {
    render(<CoberturaRedes marcas={MARCAS} />);

    // Marcas y redes con nombre legible (tiktok -> "TikTok"), nunca el id crudo.
    expect(screen.getByText("UnoTV")).toBeInTheDocument();
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    expect(screen.getAllByText("TikTok").length).toBeGreaterThan(0);
    expect(screen.getByText("Facebook")).toBeInTheDocument();
    expect(screen.queryByText("tiktok")).not.toBeInTheDocument();
    expect(screen.queryByText("facebook")).not.toBeInTheDocument();

    // Estados con su etiqueta legible (ver ESTADO en CoberturaRedes.tsx).
    expect(screen.getAllByText("Con datos").length).toBe(2);
    expect(screen.getByText("Sin métricas")).toBeInTheDocument();
    expect(screen.getByText("Sin lectura")).toBeInTheDocument();
    expect(screen.getByText("No configurada")).toBeInTheDocument();
    expect(screen.getByText("No conectada")).toBeInTheDocument();

    // El motivo explica POR QUÉ una red no aporta datos (no se oculta).
    expect(screen.getByText("Red no contratada en el piloto.")).toBeInTheDocument();

    // Conteo de cobertura por marca sobre su universo completo de redes.
    expect(screen.getByText("1/5 con datos")).toBeInTheDocument();
    expect(screen.getByText("1/1 con datos")).toBeInTheDocument();

    // Métricas es-MX completas para la red con datos; "—" cuando la red no respondió.
    expect(screen.getByText("120,000")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("expone los filtros client-side por red y por marca (aria-label)", () => {
    render(<CoberturaRedes marcas={MARCAS} />);

    expect(screen.getByRole("combobox", { name: "Filtrar por red" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Filtrar por marca" })).toBeInTheDocument();
  });

  it("no renderiza nada sin marcas en el reporte", () => {
    const { container } = render(<CoberturaRedes marcas={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
