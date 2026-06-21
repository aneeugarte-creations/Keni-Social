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
    fase: "",
    motivo: "",
    salida: "",
    error: "",
    metricas: null,
    resultado: null,
    autor_id: "",
    autor_nombre: "",
    fecha_inicio: "2026-05-24T23:00:00",
    fecha_fin: "",
    ...parcial,
  };
}

describe("ProgresoGeneracion", () => {
  it("muestra el texto del asistente mientras corre (streaming)", () => {
    render(<ProgresoGeneracion generacion={base({ salida: "Hola mundo en vivo" })} />);
    expect(screen.getByText("Copy desde nota · UnoTV")).toBeInTheDocument();
    expect(screen.getByText("Visualizando…")).toBeInTheDocument();
    expect(screen.getByText(/Hola mundo en vivo/)).toBeInTheDocument();
  });

  it("pinta la etapa según la fase: Razonando… → Escribiendo… → Terminando…", () => {
    const { rerender } = render(
      <ProgresoGeneracion generacion={base({ fase: "razonando" })} />,
    );
    expect(screen.getByText("Razonando…")).toBeInTheDocument();
    rerender(<ProgresoGeneracion generacion={base({ fase: "generando", salida: "Hola" })} />);
    expect(screen.getByText("Escribiendo…")).toBeInTheDocument();
    rerender(<ProgresoGeneracion generacion={base({ fase: "completado", salida: "Hola" })} />);
    expect(screen.getByText("Terminando…")).toBeInTheDocument();
  });

  it("sin fase cae a 'Visualizando…'", () => {
    render(<ProgresoGeneracion generacion={base({ fase: "", salida: "en curso" })} />);
    expect(screen.getByText("Visualizando…")).toBeInTheDocument();
  });

  it("muestra 'Pensando…' cuando aún no hay texto", () => {
    render(<ProgresoGeneracion generacion={base({ salida: "" })} />);
    expect(screen.getByText("Pensando…")).toBeInTheDocument();
  });

  it("muestra el botón Cancelar mientras corre y dispara onCancelar", () => {
    let cancelaciones = 0;
    render(
      <ProgresoGeneracion
        generacion={base({ salida: "en curso" })}
        onCancelar={() => {
          cancelaciones += 1;
        }}
      />,
    );
    const boton = screen.getByRole("button", { name: /Cancelar/ });
    boton.click();
    expect(cancelaciones).toBe(1);
  });

  it("no muestra Cancelar si no se pasa onCancelar", () => {
    render(<ProgresoGeneracion generacion={base({ salida: "en curso" })} />);
    expect(screen.queryByRole("button", { name: /Cancelar/ })).toBeNull();
  });

  it("deshabilita Cancelar mientras la cancelación está en curso", () => {
    render(
      <ProgresoGeneracion
        generacion={base({ salida: "en curso" })}
        onCancelar={() => {}}
        cancelando
      />,
    );
    expect(screen.getByRole("button", { name: /Cancelar/ })).toBeDisabled();
  });

  it("no muestra Cancelar cuando ya terminó (no está ejecutando)", () => {
    render(
      <ProgresoGeneracion
        generacion={base({ estado: "completado", salida: "listo" })}
        onCancelar={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /Cancelar/ })).toBeNull();
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
