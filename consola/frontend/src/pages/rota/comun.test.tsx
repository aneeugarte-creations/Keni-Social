import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { lunesDeSemana } from "@/lib/rota-calendario";
import type { EventoRota, FranjaSemana, SwapTurno, TurnoRota } from "@/types";

import { contarSwapsPendientes, eventosPorTurno, NavegadorSemana, type CubridorEvento } from "./comun";

function swap(over: Partial<SwapTurno> = {}): SwapTurno {
  return {
    id: "s1",
    solicitante_id: "u1",
    solicitante_nombre: "Ana",
    destinatario_id: "u2",
    destinatario_nombre: "Bruno",
    fecha_a: "2026-06-15",
    franja_a: "f-a",
    fecha_b: "2026-06-16",
    franja_b: "f-b",
    motivo: "",
    estado: "propuesto",
    respuesta_destinatario: "",
    respuesta_admin: "",
    creado: "2026-06-10T12:00:00",
    actualizado: "2026-06-10T12:00:00",
    decidido_destinatario: "",
    decidido_admin: "",
    aplicado: "",
    marca: "",
    marca_nombre: "",
    tipo: "intercambio",
    ...over,
  };
}

describe("contarSwapsPendientes", () => {
  it("cuenta los `propuesto` dirigidos a mí, no los que envié yo ni los de otros", () => {
    const swaps = [
      swap({ id: "a", estado: "propuesto", destinatario_id: "yo" }), // me toca responder
      swap({ id: "b", estado: "propuesto", destinatario_id: "otro" }), // no es para mí
      // lo envié yo: sigue `propuesto` pero espera al OTRO, no a mí
      swap({ id: "c", estado: "propuesto", solicitante_id: "yo", destinatario_id: "otro" }),
    ];
    expect(contarSwapsPendientes(swaps, "yo", false)).toBe(1);
  });

  it("un admin cuenta además los `aceptado` (esperan su aprobación)", () => {
    const swaps = [
      swap({ id: "a", estado: "aceptado", destinatario_id: "otro" }),
      swap({ id: "b", estado: "aceptado", destinatario_id: "otro2" }),
      swap({ id: "c", estado: "propuesto", destinatario_id: "yo" }), // y soy destinatario de otro
    ];
    expect(contarSwapsPendientes(swaps, "yo", true)).toBe(3);
  });

  it("un editor (no admin) NO cuenta los `aceptado`: no es quien aprueba", () => {
    const swaps = [swap({ estado: "aceptado", destinatario_id: "otro" })];
    expect(contarSwapsPendientes(swaps, "yo", false)).toBe(0);
  });

  it("ignora los estados terminales aunque me involucren", () => {
    const swaps = [
      swap({ estado: "aplicado", destinatario_id: "yo" }),
      swap({ estado: "rechazado", destinatario_id: "yo" }),
      swap({ estado: "cancelado", destinatario_id: "yo" }),
      swap({ estado: "rechazado_admin", destinatario_id: "yo" }),
    ];
    expect(contarSwapsPendientes(swaps, "yo", true)).toBe(0);
  });
});

describe("NavegadorSemana — atajo «Hoy»", () => {
  it("«Hoy» salta a la semana ACTUAL (lunes de hoy), esté donde esté el navegador", () => {
    const setLunes = vi.fn();
    // Arrancamos en una semana lejana (enero 2020) para que «Hoy» tenga algo a lo que volver.
    render(
      <NavegadorSemana lunes="2020-01-06" setLunes={setLunes} inicio="2020-01-06" fin="2020-01-12" />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Hoy" }));
    expect(setLunes).toHaveBeenCalledWith(lunesDeSemana(new Date()));
  });
});

function franja(over: Partial<FranjaSemana> = {}): FranjaSemana {
  return {
    id: "f1",
    lunes: "2026-06-15",
    nombre: "Mañana",
    inicio: "08:00",
    fin: "16:00",
    orden: 0,
    es_descanso: false,
    marca: "",
    marca_nombre: "",
    ...over,
  };
}

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

describe("eventosPorTurno — puente franja → eventos que me tocan", () => {
  const manana = franja({ id: "f1", nombre: "Mañana", inicio: "08:00", fin: "16:00", orden: 0 });
  const tarde = franja({ id: "f2", nombre: "Tarde", inicio: "16:00", fin: "23:59", orden: 1 });
  const franjas = [manana, tarde];

  it("mete cada evento en el turno de la franja que contiene su hora, ese día", () => {
    const turnos = [
      turno({ id: "tA", franja_id: "f1", fecha: "2026-06-15" }),
      turno({ id: "tB", franja_id: "f2", fecha: "2026-06-15" }),
    ];
    const eventos = [
      evento({ id: "e-man", hora: "10:00", fecha: "2026-06-15" }),
      evento({ id: "e-tar", hora: "18:00", fecha: "2026-06-15" }),
    ];
    const mapa = eventosPorTurno(turnos, eventos, new Map(), franjas);
    expect(mapa.get("tA")?.map((i) => i.evento.id)).toEqual(["e-man"]);
    expect(mapa.get("tB")?.map((i) => i.evento.id)).toEqual(["e-tar"]);
  });

  it("ordena los eventos por hora dentro del turno", () => {
    const turnos = [turno({ id: "tA", franja_id: "f1", fecha: "2026-06-15" })];
    const eventos = [
      evento({ id: "tarde-man", hora: "11:30", fecha: "2026-06-15" }),
      evento({ id: "pronto", hora: "09:00", fecha: "2026-06-15" }),
    ];
    const mapa = eventosPorTurno(turnos, eventos, new Map(), franjas);
    expect(mapa.get("tA")?.map((i) => i.evento.id)).toEqual(["pronto", "tarde-man"]);
  });

  it("no mezcla días: un evento de otro día no entra en el turno", () => {
    const turnos = [turno({ id: "tA", franja_id: "f1", fecha: "2026-06-15" })];
    const eventos = [evento({ id: "otro-dia", hora: "10:00", fecha: "2026-06-16" })];
    const mapa = eventosPorTurno(turnos, eventos, new Map(), franjas);
    expect(mapa.get("tA")).toEqual([]);
  });

  it("adjunta los cubridores (titularidad) que vienen en el mapa", () => {
    const turnos = [turno({ id: "tA", franja_id: "f1", fecha: "2026-06-15" })];
    const eventos = [evento({ id: "e-man", hora: "10:00", fecha: "2026-06-15" })];
    const cubridores = new Map<string, CubridorEvento[]>([
      ["e-man", [{ id: "u9", nombre: "Bruno" }]],
    ]);
    const mapa = eventosPorTurno(turnos, eventos, cubridores, franjas);
    expect(mapa.get("tA")?.[0]?.cubridores).toEqual([{ id: "u9", nombre: "Bruno" }]);
  });
});
