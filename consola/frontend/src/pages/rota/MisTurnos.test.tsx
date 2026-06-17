import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EventoRota, TurnoRota } from "@/types";

import { type ItemEventoCalendario } from "./comun";
import { ListaMisTurnos } from "./MisTurnos";

function evento(over: Partial<EventoRota> = {}): EventoRota {
  return {
    id: "e1",
    titulo: "Partido",
    fecha: "2026-06-15",
    hora: "10:00",
    contenido: "",
    nota: "",
    tipo_cobertura: "transmision",
    prioridad: "media",
    cambiado: false,
    actualizado: "",
    es_sabado: false,
    marca: "",
    marca_nombre: "",
    ...over,
  };
}

/** Mapa `turno.id -> eventos` como el que arma `eventosPorTurno`. */
function mapaEventos(
  entradas: Record<string, ItemEventoCalendario[]>,
): Map<string, ItemEventoCalendario[]> {
  return new Map(Object.entries(entradas));
}

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
    inicio: "08:00",
    fin: "16:00",
    horario_propio: false,
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

  it("muestra el NOMBRE real de una franja custom (no se queda en blanco)", () => {
    render(
      <ListaMisTurnos
        turnos={[turno({ franja: "", franja_nombre: "Cobertura nocturna" })]}
      />,
    );
    expect(screen.getByText("Cobertura nocturna")).toBeInTheDocument();
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

  it("sin `eventosPorTurno` no pinta el bloque de eventos (retrocompat)", () => {
    render(<ListaMisTurnos turnos={[turno()]} />);
    expect(screen.queryByText("En tu franja")).not.toBeInTheDocument();
  });
});

describe("ListaMisTurnos — eventos que me tocan en mi franja", () => {
  it("muestra «Por cubrir» con botón Coger y avisa al cogerlo", () => {
    const onCoger = vi.fn();
    render(
      <ListaMisTurnos
        turnos={[turno({ id: "t1" })]}
        eventosPorTurno={mapaEventos({
          t1: [{ evento: evento({ id: "e1", titulo: "Final" }), cubridores: [] }],
        })}
        miId="u1"
        onCoger={onCoger}
      />,
    );
    expect(screen.getByText("Final")).toBeInTheDocument();
    expect(screen.getByText("Por cubrir")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Coger" }));
    expect(onCoger).toHaveBeenCalledWith("e1");
  });

  it("marca «Lo cubres tú» cuando el cubridor soy yo (sin botón Coger)", () => {
    render(
      <ListaMisTurnos
        turnos={[turno({ id: "t1" })]}
        eventosPorTurno={mapaEventos({
          t1: [{ evento: evento({ id: "e1" }), cubridores: [{ id: "u1", nombre: "Ana" }] }],
        })}
        miId="u1"
        onCoger={vi.fn()}
      />,
    );
    expect(screen.getByText("Lo cubres tú")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Coger" })).not.toBeInTheDocument();
  });

  it("muestra quién lo cubre cuando es otra persona", () => {
    render(
      <ListaMisTurnos
        turnos={[turno({ id: "t1" })]}
        eventosPorTurno={mapaEventos({
          t1: [{ evento: evento({ id: "e1" }), cubridores: [{ id: "u9", nombre: "Bruno" }] }],
        })}
        miId="u1"
        onCoger={vi.fn()}
      />,
    );
    expect(screen.getByText(/Lo cubre Bruno/)).toBeInTheDocument();
  });

  it("dice «Sin eventos en esta franja» cuando el turno no tiene eventos", () => {
    render(
      <ListaMisTurnos
        turnos={[turno({ id: "t1" })]}
        eventosPorTurno={mapaEventos({ t1: [] })}
        miId="u1"
      />,
    );
    expect(screen.getByText("Sin eventos en esta franja.")).toBeInTheDocument();
  });

  it("en un turno de DESCANSO no pinta el bloque de eventos", () => {
    render(
      <ListaMisTurnos
        turnos={[turno({ id: "t1", franja: "descanso", franja_nombre: "Descanso" })]}
        eventosPorTurno={mapaEventos({ t1: [] })}
        miId="u1"
      />,
    );
    expect(screen.queryByText("En tu franja")).not.toBeInTheDocument();
  });
});
