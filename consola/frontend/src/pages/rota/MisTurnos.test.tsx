/**
 * Tests del agrupado del calendario MENSUAL del EQUIPO («Mis turnos» → vista «Equipo»):
 * por día → franja → personas, ordenado por hora y excluyendo descanso (es «quién trabaja»).
 */
import { describe, expect, it } from "vitest";

import type { TurnoRota } from "@/types";

import { agruparEquipoPorFecha, agruparPersonasPorHorario } from "./MisTurnos";

function turno(p: Partial<TurnoRota>): TurnoRota {
  return {
    id: Math.random().toString(36).slice(2),
    semana: "",
    fecha: "2026-06-03",
    miembro_id: "m1",
    miembro_nombre: "Ana",
    franja_id: "f-man",
    franja_nombre: "Mañana",
    franja: "matutino",
    inicio: "08:00",
    fin: "14:00",
    horario_propio: false,
    estado: "aprobado",
    override: false,
    motivo: "",
    nota_relevo: "",
    es_sabado: false,
    marca: "",
    marca_nombre: "",
    ...p,
  } as TurnoRota;
}

describe("agruparEquipoPorFecha", () => {
  it("agrupa por día y franja, con todas las personas de cada franja", () => {
    const m = agruparEquipoPorFecha([
      turno({ fecha: "2026-06-03", franja_id: "f-man", miembro_id: "a", miembro_nombre: "Ana" }),
      turno({ fecha: "2026-06-03", franja_id: "f-man", miembro_id: "b", miembro_nombre: "Beto" }),
      turno({
        fecha: "2026-06-03",
        franja_id: "f-tar",
        franja_nombre: "Tarde",
        inicio: "14:00",
        fin: "20:00",
        miembro_id: "c",
        miembro_nombre: "Caro",
      }),
    ]);
    const dia = m.get("2026-06-03")!;
    // Dos franjas, ordenadas por inicio (Mañana antes que Tarde).
    expect(dia.map((f) => f.nombre)).toEqual(["Mañana", "Tarde"]);
    // La franja de mañana junta a Ana y Beto (orden alfabético).
    expect(dia[0].personas.map((p) => p.nombre)).toEqual(["Ana", "Beto"]);
    expect(dia[1].personas.map((p) => p.nombre)).toEqual(["Caro"]);
  });

  it("excluye descanso (la vista de equipo es «quién trabaja»)", () => {
    const m = agruparEquipoPorFecha([
      turno({ fecha: "2026-06-04", franja: "descanso", franja_nombre: "Descanso" }),
    ]);
    expect(m.get("2026-06-04")).toBeUndefined();
  });

  it("ordena las personas alfabéticamente dentro de la franja", () => {
    const m = agruparEquipoPorFecha([
      turno({ franja_id: "f-man", miembro_id: "z", miembro_nombre: "Zoe" }),
      turno({ franja_id: "f-man", miembro_id: "a", miembro_nombre: "Ada" }),
    ]);
    expect(m.get("2026-06-03")![0].personas.map((p) => p.nombre)).toEqual(["Ada", "Zoe"]);
  });

  it("guarda el horario efectivo de cada persona", () => {
    const dia = agruparEquipoPorFecha([
      turno({ miembro_id: "a", miembro_nombre: "Ana", inicio: "08:00", fin: "16:00" }),
    ]).get("2026-06-03")!;
    expect(dia[0].personas[0]).toMatchObject({ nombre: "Ana", inicio: "08:00", fin: "16:00" });
  });
});

describe("agruparPersonasPorHorario", () => {
  it("franja homogénea = un solo grupo con toda la gente", () => {
    const g = agruparPersonasPorHorario([
      { id: "a", nombre: "Ana", inicio: "08:00", fin: "16:00" },
      { id: "b", nombre: "Beto", inicio: "08:00", fin: "16:00" },
    ]);
    expect(g).toHaveLength(1);
    expect(g[0]).toMatchObject({ inicio: "08:00", fin: "16:00" });
    expect(g[0].personas.map((p) => p.nombre)).toEqual(["Ana", "Beto"]);
  });

  it("franja heterogénea = un grupo por horario, ordenados por inicio", () => {
    const g = agruparPersonasPorHorario([
      { id: "a", nombre: "Ana", inicio: "10:00", fin: "18:00" },
      { id: "b", nombre: "Beto", inicio: "08:00", fin: "16:00" },
      { id: "c", nombre: "Caro", inicio: "08:00", fin: "16:00" },
    ]);
    expect(g.map((x) => x.inicio)).toEqual(["08:00", "10:00"]);
    expect(g[0].personas.map((p) => p.nombre)).toEqual(["Beto", "Caro"]);
    expect(g[1].personas.map((p) => p.nombre)).toEqual(["Ana"]);
  });
});
