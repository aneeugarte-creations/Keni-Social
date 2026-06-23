import { describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import type { FranjaSemana } from "@/types";

import { agruparFechasPorSemana, asignarMatriz, lunesDeFecha } from "./rota-reparto";

const franja = (id: string, lunes: string): FranjaSemana => ({
  id,
  lunes,
  nombre: "Mañana",
  inicio: "08:00",
  fin: "16:00",
  orden: 0,
  es_descanso: false,
  marca: "",
  marca_nombre: "",
});

// Junio 2026: 15 y 22 son lunes.
const LUN_A = "2026-06-15";
const LUN_B = "2026-06-22";

describe("lunesDeFecha / agruparFechasPorSemana", () => {
  it("reancla cualquier día al lunes de su semana", () => {
    expect(lunesDeFecha("2026-06-15")).toBe(LUN_A); // lunes
    expect(lunesDeFecha("2026-06-20")).toBe(LUN_A); // sábado de esa semana
    expect(lunesDeFecha("2026-06-22")).toBe(LUN_B); // lunes siguiente
  });

  it("agrupa fechas por su semana preservando el orden", () => {
    const g = agruparFechasPorSemana(["2026-06-15", "2026-06-22", "2026-06-16"]);
    expect([...g.keys()]).toEqual([LUN_A, LUN_B]);
    expect(g.get(LUN_A)).toEqual(["2026-06-15", "2026-06-16"]);
    expect(g.get(LUN_B)).toEqual(["2026-06-22"]);
  });
});

describe("asignarMatriz — reparto multi-semana, franja por semana de cada día", () => {
  it("crea cada turno con el lunes y la franja_id de SU semana", async () => {
    const crear = vi.spyOn(apiMod.api, "crearTurno").mockResolvedValue({} as never);
    const franjasPorSemana = new Map<string, FranjaSemana[]>([
      [LUN_A, [franja("fA", LUN_A)]],
      [LUN_B, [franja("fB", LUN_B)]],
    ]);
    const porPersona = new Map<string, string[]>([
      ["u-elias", ["2026-06-15", "2026-06-16", "2026-06-22"]], // 2 en semana A, 1 en B
      ["u-luis", ["2026-06-15"]], // 1 en semana A
    ]);

    const r = await asignarMatriz(porPersona, franjasPorSemana, "08:00", "16:00");

    expect(r).toEqual({
      creados: 4,
      yaEstaba: 0,
      requierenOverride: 0,
      fallos: 0,
      personasConCreados: 2,
      sinFranja: 0,
    });
    // Elias semana A (fA) y semana B (fB); horas omitidas porque coinciden con la franja.
    expect(crear).toHaveBeenCalledWith({
      lunes: LUN_A,
      fecha: "2026-06-15",
      miembro_id: "u-elias",
      franja_id: "fA",
    });
    expect(crear).toHaveBeenCalledWith({
      lunes: LUN_B,
      fecha: "2026-06-22",
      miembro_id: "u-elias",
      franja_id: "fB",
    });
    expect(crear).toHaveBeenCalledWith({
      lunes: LUN_A,
      fecha: "2026-06-15",
      miembro_id: "u-luis",
      franja_id: "fA",
    });
    expect(crear).toHaveBeenCalledTimes(4);
  });

  it("una semana sin franjas laborales no rompe el reparto: cuenta sus días en sinFranja", async () => {
    const crear = vi.spyOn(apiMod.api, "crearTurno").mockResolvedValue({} as never);
    // Solo la semana A tiene franjas; la B falta en el mapa.
    const franjasPorSemana = new Map<string, FranjaSemana[]>([[LUN_A, [franja("fA", LUN_A)]]]);
    const porPersona = new Map<string, string[]>([
      ["u-elias", ["2026-06-16", "2026-06-22", "2026-06-23"]], // 1 en A, 2 en B (sin franja)
    ]);

    const r = await asignarMatriz(porPersona, franjasPorSemana, "08:00", "16:00");

    expect(r.creados).toBe(1);
    expect(r.sinFranja).toBe(2);
    expect(r.personasConCreados).toBe(1);
    expect(crear).toHaveBeenCalledTimes(1);
    expect(crear).toHaveBeenCalledWith({
      lunes: LUN_A,
      fecha: "2026-06-16",
      miembro_id: "u-elias",
      franja_id: "fA",
    });
  });

  it("manda horario a medida cuando difiere del de la franja", async () => {
    const crear = vi.spyOn(apiMod.api, "crearTurno").mockResolvedValue({} as never);
    const franjasPorSemana = new Map<string, FranjaSemana[]>([[LUN_A, [franja("fA", LUN_A)]]]);
    const porPersona = new Map<string, string[]>([["u-luis", ["2026-06-15"]]]);

    await asignarMatriz(porPersona, franjasPorSemana, "07:00", "15:00");

    expect(crear).toHaveBeenLastCalledWith({
      lunes: LUN_A,
      fecha: "2026-06-15",
      miembro_id: "u-luis",
      franja_id: "fA",
      inicio: "07:00",
      fin: "15:00",
    });
  });
});
