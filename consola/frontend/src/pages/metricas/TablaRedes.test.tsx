import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RedMetrica } from "@/types";

import { TablaRedes } from "./TablaRedes";

const REDES: RedMetrica[] = [
  {
    red: "instagram",
    visualizaciones: 120000,
    alcance: 45000,
    interacciones: 6000,
    engagement_pct: 5,
  },
  {
    // tiktok no mide alcance (#138): null, no 0.
    red: "tiktok",
    visualizaciones: 90000,
    alcance: null,
    interacciones: 4500,
    engagement_pct: 5,
  },
];

describe("TablaRedes", () => {
  it("renderiza una fila por red con el nombre legible y las métricas formateadas", () => {
    render(<TablaRedes redes={REDES} />);

    // Nombres de red traducidos desde su id de plataforma.
    expect(screen.getByText("Instagram")).toBeInTheDocument();
    expect(screen.getByText("TikTok")).toBeInTheDocument();
    // Cabeceras de las columnas pedidas.
    expect(screen.getByText("Red")).toBeInTheDocument();
    expect(screen.getByText("Vistas")).toBeInTheDocument();
    expect(screen.getByText("Alcance")).toBeInTheDocument();
    expect(screen.getByText("Interacciones")).toBeInTheDocument();
    expect(screen.getByText("Engagement")).toBeInTheDocument();
    // Una métrica concreta formateada (vistas de instagram).
    expect(screen.getByText("120,000")).toBeInTheDocument();
  });

  it("muestra '—' cuando una red no mide alcance (null), no un 0 falso", () => {
    render(<TablaRedes redes={REDES} />);

    // tiktok.alcance === null -> "—"; ninguna celda debe pintar "0" para ese alcance.
    expect(screen.getByText("—")).toBeInTheDocument();
    // instagram.alcance sí se formatea.
    expect(screen.getByText("45,000")).toBeInTheDocument();
  });

  it("dice con honestidad cuando no hay redes", () => {
    render(<TablaRedes redes={[]} />);

    expect(screen.getByText(/No hay redes para mostrar/i)).toBeInTheDocument();
  });
});
