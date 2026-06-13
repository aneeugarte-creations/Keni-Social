import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TurnoRota } from "@/types";

import { ListaMisTurnos } from "./MisTurnos";

function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "t1",
    semana: "2026-06-15",
    fecha: "2026-06-15",
    miembro_id: "u1",
    miembro_nombre: "Ana",
    franja_id: "f1",
    franja_nombre: "Mañana",
    franja: "matutino",
    estado: "aprobado",
    override: false,
    motivo: "",
    nota_relevo: "",
    es_sabado: false,
    marca: "",
    marca_nombre: "",
    ...over,
  };
}

describe("ListaMisTurnos — tarjetas móvil-first", () => {
  it("renderiza una lista con la franja como dato primario y la fecha", () => {
    render(<ListaMisTurnos turnos={[turno()]} />);
    // Lista semántica (ul/li) para una pila vertical legible en móvil.
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByText("Mañana")).toBeInTheDocument();
    // La fecha se formatea en CDMX (vía lib/fecha): 15 de junio.
    expect(screen.getByText(/15/)).toBeInTheDocument();
    expect(screen.getByText(/jun/i)).toBeInTheDocument();
  });

  it("muestra los matices del turno (sábado, override, motivo y relevo)", () => {
    render(
      <ListaMisTurnos
        turnos={[
          turno({
            es_sabado: true,
            override: true,
            motivo: "Cobertura crítica",
            nota_relevo: "Queda pendiente subir el resumen",
          }),
        ]}
      />,
    );
    expect(screen.getByText("Sábado")).toBeInTheDocument();
    expect(screen.getByText("Override")).toBeInTheDocument();
    expect(screen.getByText(/Cobertura crítica/)).toBeInTheDocument();
    expect(screen.getByText(/Queda pendiente subir el resumen/)).toBeInTheDocument();
  });

  it("ordena cronológicamente por fecha", () => {
    render(
      <ListaMisTurnos
        turnos={[
          turno({ id: "b", fecha: "2026-06-17", franja: "vespertino", franja_nombre: "Tarde" }),
          turno({ id: "a", fecha: "2026-06-15" }),
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    // El 15 (Mañana) va antes que el 17 (Tarde).
    expect(items[0]).toHaveTextContent("Mañana");
    expect(items[1]).toHaveTextContent("Tarde");
  });
});
