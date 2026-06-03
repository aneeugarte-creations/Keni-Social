import { fireEvent, render, screen, within } from "@testing-library/react";
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

    // Nombres de red traducidos (aparecen también en el reparto, de ahí getAllByText).
    expect(screen.getAllByText("Instagram").length).toBeGreaterThan(0);
    expect(screen.getAllByText("TikTok").length).toBeGreaterThan(0);
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
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    // instagram.alcance sí se formatea (en su fila y, sumado, en la de totales).
    expect(screen.getAllByText("45,000").length).toBeGreaterThan(0);
  });

  it("muestra una fila de totales con suma de brutas y engagement global", () => {
    render(<TablaRedes redes={REDES} />);

    const filaTotal = screen.getByText("Total").closest("tr")!;
    const celdasTotal = within(filaTotal);
    // Suma de vistas (120k + 90k) e interacciones (6000 + 4500).
    expect(celdasTotal.getByText("210,000")).toBeInTheDocument();
    expect(celdasTotal.getByText("10,500")).toBeInTheDocument();
    // Engagement global = interacciones/vistas = 10500/210000 = 5.0 %.
    expect(celdasTotal.getByText("5.0 %")).toBeInTheDocument();
  });

  it("permite ordenar por una columna numérica al clicar su cabecera", () => {
    render(<TablaRedes redes={REDES} />);

    // Orden inicial = orden natural (IG primero). Tras ordenar por interacciones asc,
    // tiktok (4500) debe anteceder a instagram (6000) en el cuerpo de la tabla.
    const cabecera = screen.getByRole("button", { name: /Interacciones/ });
    fireEvent.click(cabecera); // 1er clic = desc
    fireEvent.click(cabecera); // 2º clic = asc
    const filas = screen.getAllByRole("row");
    // La primera fila de datos (índice 1, tras el header) ahora es TikTok (menor interac).
    const primeraDatos = filas.find((f) => within(f).queryByText("TikTok"));
    expect(primeraDatos).toBeTruthy();
    // aria-sort refleja la columna activa.
    const th = cabecera.closest("th")!;
    expect(th).toHaveAttribute("aria-sort", "ascending");
  });

  it("muestra el reparto de vistas por red", () => {
    render(<TablaRedes redes={REDES} />);

    expect(screen.getByText(/Reparto de vistas por red/i)).toBeInTheDocument();
    // 120000 / 210000 ≈ 57 %.
    expect(screen.getByText("57%")).toBeInTheDocument();
  });

  it("dice con honestidad cuando no hay redes", () => {
    render(<TablaRedes redes={[]} />);

    expect(screen.getByText(/No hay redes para mostrar/i)).toBeInTheDocument();
  });
});
