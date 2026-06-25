import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import type { RedMetrica } from "@/types";

import { TablaRedes } from "./TablaRedes";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  useVistaConfig.getState().reset();
});

const REDES: RedMetrica[] = [
  {
    red: "instagram",
    visualizaciones: 120000,
    impresiones: 145000,
    alcance: 45000,
    interacciones: 6000,
    engagement_pct: 5,
  },
  {
    // tiktok no mide alcance: null, no 0.
    red: "tiktok",
    visualizaciones: 90000,
    impresiones: 108000,
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
    // Métricas de instagram (vistas y alcance) acotadas a SU fila: el alcance total
    // coincide con el de IG (45k, único que lo mide), así que sin acotar chocaría.
    const filaIG = screen
      .getAllByRole("row")
      .find((f) => within(f).queryByText("120,000"))!;
    expect(filaIG).toBeTruthy();
    expect(within(filaIG).getByText("120,000")).toBeInTheDocument();
    expect(within(filaIG).getByText("45,000")).toBeInTheDocument();
  });

  it("muestra '—' en el alcance de una red que no lo mide (TikTok)", () => {
    render(<TablaRedes redes={REDES} />);

    const filaTikTok = screen
      .getAllByRole("row")
      .find((f) => within(f).queryByText("TikTok"))!;
    expect(filaTikTok).toBeTruthy();
    expect(within(filaTikTok).getByText("—")).toBeInTheDocument();
  });

  it("muestra una fila de totales con suma de brutas y engagement global", () => {
    render(<TablaRedes redes={REDES} />);

    const filaTotal = screen.getByText("Total").closest("tr")!;
    const celdasTotal = within(filaTotal);
    // Suma de vistas (120k + 90k) e interacciones (6000 + 4500).
    expect(celdasTotal.getByText("210,000")).toBeInTheDocument();
    expect(celdasTotal.getByText("10,500")).toBeInTheDocument();
    // Alcance total = solo IG lo mide (45k); TikTok es null y no suma.
    expect(celdasTotal.getByText("45,000")).toBeInTheDocument();
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

  it("con foco de red global solo muestra las redes seleccionadas (quita el resto)", () => {
    // Foco = solo Instagram: TikTok desaparece por completo (ni fila de datos ni "—").
    useVistaConfig.getState().setRed("instagram");
    render(<TablaRedes redes={REDES} />);

    expect(screen.getAllByText("Instagram").length).toBeGreaterThan(0);
    expect(screen.queryByText("TikTok")).not.toBeInTheDocument();
    expect(screen.queryByText("Facebook")).not.toBeInTheDocument();
    // El total refleja solo Instagram (no la suma de todas las redes).
    const filaTotal = screen.getByText("Total").closest("tr")!;
    expect(within(filaTotal).getByText("120,000")).toBeInTheDocument();
  });

  it("no pinta redes sin datos: una red sin filas no aparece (sin '—' de relleno)", () => {
    // Una red sin datos en el foco (p. ej. la que no publica el formato filtrado) se OMITE,
    // no se rellena con una fila "—". Con `redes` solo de Instagram, el resto no sale.
    render(<TablaRedes redes={[REDES[0]]} />);

    expect(screen.getAllByText("Instagram").length).toBeGreaterThan(0);
    for (const nombre of ["Facebook", "TikTok", "YouTube", "X"]) {
      expect(screen.queryByText(nombre)).not.toBeInTheDocument();
    }
  });
});
