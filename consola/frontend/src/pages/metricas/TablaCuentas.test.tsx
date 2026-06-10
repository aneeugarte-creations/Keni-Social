import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { CuentaMetrica } from "@/types";

import { TablaCuentas } from "./TablaCuentas";

const CUENTAS: CuentaMetrica[] = [
  {
    marca_id: "unotv",
    marca: "UnoTV",
    visualizaciones: 100000,
    alcance: 40000,
    interacciones: 5000,
    engagement_pct: 5,
  },
  {
    marca_id: "claro_sports",
    marca: "Claro Sports",
    visualizaciones: 300000,
    alcance: 90000,
    interacciones: 9000,
    engagement_pct: 3,
  },
];

function renderTabla(props?: { onVerPiezas?: (id: string) => void }) {
  return render(
    <MemoryRouter>
      <TablaCuentas cuentas={CUENTAS} onVerPiezas={props?.onVerPiezas} />
    </MemoryRouter>,
  );
}

describe("TablaCuentas", () => {
  it("muestra una fila por cuenta y una fila de totales", () => {
    renderTabla();

    expect(screen.getByText("UnoTV")).toBeInTheDocument();
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();

    const filaTotal = screen.getByText("Total").closest("tr")!;
    const total = within(filaTotal);
    // Suma de vistas (100k + 300k), interacciones (5000 + 9000).
    expect(total.getByText("400,000")).toBeInTheDocument();
    expect(total.getByText("14,000")).toBeInTheDocument();
    // Engagement global = 14000/400000 = 3.5 %.
    expect(total.getByText("3.5 %")).toBeInTheDocument();
  });

  it("ordena por una columna al clicar su cabecera (con aria-sort)", () => {
    renderTabla();

    const cabeceraVistas = screen.getByRole("button", { name: /Vistas/ });
    fireEvent.click(cabeceraVistas); // desc: Claro Sports (300k) primero
    let cuerpoFilas = screen
      .getAllByRole("row")
      .filter((f) => within(f).queryByText(/UnoTV|Claro Sports/));
    expect(within(cuerpoFilas[0]).getByText("Claro Sports")).toBeInTheDocument();
    expect(cabeceraVistas.closest("th")).toHaveAttribute("aria-sort", "descending");

    fireEvent.click(cabeceraVistas); // asc: UnoTV (100k) primero
    cuerpoFilas = screen
      .getAllByRole("row")
      .filter((f) => within(f).queryByText(/UnoTV|Claro Sports/));
    expect(within(cuerpoFilas[0]).getByText("UnoTV")).toBeInTheDocument();
    expect(cabeceraVistas.closest("th")).toHaveAttribute("aria-sort", "ascending");
  });

  it("invoca onVerPiezas con el id de la marca (drill-down)", () => {
    const onVerPiezas = vi.fn();
    renderTabla({ onVerPiezas });

    fireEvent.click(screen.getByTitle("Ver piezas de UnoTV"));
    expect(onVerPiezas).toHaveBeenCalledWith("unotv");
  });

  it("dice con honestidad cuando no hay marcas", () => {
    render(
      <MemoryRouter>
        <TablaCuentas cuentas={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/No hay marcas para mostrar en este periodo/i)).toBeInTheDocument();
  });
});
