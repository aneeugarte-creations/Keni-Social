/**
 * Tests para TarjetaKpi — componente de tarjeta KPI unificado.
 *
 * Verifica que ambas variantes ("borde" y "card") renderizan la etiqueta y el
 * valor, y que el tooltip usa el prop `titulo` cuando está disponible.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TarjetaKpi } from "./TarjetaKpi";

describe("TarjetaKpi — variante borde (por defecto)", () => {
  it("muestra la etiqueta y el valor", () => {
    render(<TarjetaKpi etiqueta="Alcance" valor="1.8 mil" />);
    expect(screen.getByText("Alcance")).toBeInTheDocument();
    expect(screen.getByText("1.8 mil")).toBeInTheDocument();
  });

  it("usa el valor como tooltip si no hay titulo", () => {
    render(<TarjetaKpi etiqueta="Alcance" valor="1.8 mil" />);
    const p = screen.getByText("1.8 mil");
    expect(p).toHaveAttribute("title", "1.8 mil");
  });

  it("usa el prop titulo como tooltip cuando se pasa", () => {
    render(<TarjetaKpi etiqueta="Alcance" valor="1.8 mil" titulo="1,830" />);
    const p = screen.getByText("1.8 mil");
    expect(p).toHaveAttribute("title", "1,830");
  });

  it("sin ayuda no pinta el icono de información", () => {
    render(<TarjetaKpi etiqueta="Alcance" valor="1.8 mil" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("con ayuda pinta el icono y despliega la explicación al clicar", () => {
    render(<TarjetaKpi etiqueta="Alcance" valor="1.8 mil" ayuda="Solo lo mide Meta." />);
    const boton = screen.getByRole("button", { name: "Qué es Alcance" });
    fireEvent.click(boton);
    expect(screen.getByText("Solo lo mide Meta.")).toBeInTheDocument();
  });
});

describe("TarjetaKpi — variante card", () => {
  it("muestra la etiqueta y el valor con texto más grande", () => {
    render(<TarjetaKpi variante="card" etiqueta="Visualizaciones" valor="221.6 M" />);
    expect(screen.getByText("Visualizaciones")).toBeInTheDocument();
    expect(screen.getByText("221.6 M")).toBeInTheDocument();
  });

  it("aplica la clase de tamaño 2xl al valor", () => {
    render(<TarjetaKpi variante="card" etiqueta="Engagement" valor="1.8 %" />);
    const p = screen.getByText("1.8 %");
    expect(p.className).toContain("text-2xl");
  });
});
