import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import type { Generacion } from "@/types";

/**
 * Test de la consola de progreso en vivo de una generación de IA. Cubre los tres
 * estados visibles: ejecutando con texto en streaming, ejecutando sin texto
 * (Pensando…) y error (mensaje + botón de reintentar).
 */

function base(parcial: Partial<Generacion>): Generacion {
  return {
    id: "g1",
    tipo: "copy",
    marca: "unotv",
    etiqueta: "Copy desde nota · UnoTV",
    estado: "ejecutando",
    motivo: "",
    salida: "",
    error: "",
    metricas: null,
    resultado: null,
    fecha_inicio: "2026-05-24T23:00:00",
    fecha_fin: "",
    ...parcial,
  };
}

describe("ProgresoGeneracion", () => {
  it("muestra el texto del asistente mientras corre (streaming)", () => {
    render(<ProgresoGeneracion generacion={base({ salida: "Hola mundo en vivo" })} />);
    expect(screen.getByText("Copy desde nota · UnoTV")).toBeInTheDocument();
    expect(screen.getByText("Generando…")).toBeInTheDocument();
    expect(screen.getByText(/Hola mundo en vivo/)).toBeInTheDocument();
  });

  it("muestra 'Pensando…' cuando aún no hay texto", () => {
    render(<ProgresoGeneracion generacion={base({ salida: "" })} />);
    expect(screen.getByText("Pensando…")).toBeInTheDocument();
  });

  it("muestra el error y el botón de reintentar", () => {
    let reintentos = 0;
    render(
      <ProgresoGeneracion
        generacion={base({ estado: "error", error: "El asistente terminó con error." })}
        onReintentar={() => {
          reintentos += 1;
        }}
      />,
    );
    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByText("El asistente terminó con error.")).toBeInTheDocument();
    const boton = screen.getByRole("button", { name: "Reintentar" });
    boton.click();
    expect(reintentos).toBe(1);
  });
});
