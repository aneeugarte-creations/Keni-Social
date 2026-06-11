import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";

import { numeroCompacto } from "@/lib/formato";
import type { CuentaMetrica } from "@/types";

import { GraficaMarcas } from "./GraficaMarcas";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

function cuenta(over: Partial<CuentaMetrica>): CuentaMetrica {
  return {
    marca_id: "unotv",
    marca: "UnoTV",
    visualizaciones: 1_500_000,
    alcance: 1_000_000,
    interacciones: 42_000,
    engagement_pct: 2.8,
    ...over,
  };
}

const CUENTAS: CuentaMetrica[] = [
  cuenta({ marca_id: "unotv", marca: "UnoTV", visualizaciones: 1_500_000 }),
  cuenta({ marca_id: "claro_sports", marca: "Claro Sports", visualizaciones: 800 }),
];

describe("GraficaMarcas", () => {
  it("el título es fijo y la métrica activa vive en el selector", () => {
    render(<GraficaMarcas cuentas={CUENTAS} />);

    // La gráfica enseña UNA métrica a la vez: el selector la dice; el título no la repite.
    expect(screen.getByText("Por marca")).toBeInTheDocument();
    expect(screen.queryByText("Vistas e interacciones")).not.toBeInTheDocument();
  });

  it("ofrece una alternativa textual del chart (role=img con marcas y valores)", () => {
    render(<GraficaMarcas cuentas={CUENTAS} />);

    const img = screen.getByRole("img", { name: /Vistas por marca:/ });
    expect(img).toHaveAttribute(
      "aria-label",
      `Vistas por marca: UnoTV ${numeroCompacto(1_500_000)}, Claro Sports ${numeroCompacto(800)}`,
    );
  });

  it("con más de 5 marcas el resumen del aria-label corta en 5 y añade «y N más»", () => {
    const seis = Array.from({ length: 6 }, (_, i) =>
      cuenta({ marca_id: `m${i}`, marca: `Marca ${i}`, visualizaciones: 100 + i }),
    );
    render(<GraficaMarcas cuentas={seis} />);

    const img = screen.getByRole("img", { name: /Vistas por marca:/ });
    expect(img.getAttribute("aria-label")).toMatch(/ y 1 más$/);
    expect(img.getAttribute("aria-label")).not.toContain("Marca 5");
  });

  it("dice con honestidad cuando no hay marcas en el periodo", () => {
    render(<GraficaMarcas cuentas={[]} />);

    expect(screen.getByText(/No hay marcas para mostrar en este periodo/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
