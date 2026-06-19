/**
 * Tests de la derivación por DÍA de la vista mensual de Turnos (`derivarCoberturaPorDia`): cuántos
 * eventos hay y cuántos están SIN CUBRIR por día, reusando el selector canónico de cobertura. Función
 * pura (mismo patrón que `lib/cobertura.test.ts`); `ahora` se inyecta para un semáforo determinista.
 */
import { describe, expect, it } from "vitest";

import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  Publicacion,
  RotaSemana,
  TurnoRota,
} from "@/types";

import { derivarCoberturaPorDia } from "./useTableroMes";

// Mes y reloj fijos: los eventos caen en julio, MUY por delante de `AHORA` (junio) → semáforo
// «programado» estable (sin «en vivo»/«empieza-en» dependientes del reloj real).
const MES = "2026-07";
const AHORA = new Date("2026-06-01T12:00:00Z");
const LUNES = "2026-06-29"; // lunes de la semana que contiene el 2026-07-01.

function ev(over: Partial<EventoRota> = {}): EventoRota {
  return {
    id: "ev1",
    titulo: "Cruz Azul vs América",
    fecha: "2026-07-01",
    hora: "20:00",
    tipo_cobertura: "transmision",
    prioridad: "media",
    ...over,
  } as unknown as EventoRota;
}

function claim(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "c1",
    clase: "tarea",
    evento_id: "ev1",
    responsable_id: "u1",
    responsable_nombre: "luis",
    titulo: "Cruz Azul vs América",
    formato: "foto",
    fecha_objetivo: "2026-07-01",
    hora_objetivo: "20:00",
    ...over,
  } as unknown as Publicacion;
}

function franja(over: Partial<FranjaSemana> = {}): FranjaSemana {
  return {
    id: "f-tarde",
    lunes: LUNES,
    nombre: "Tarde",
    inicio: "14:00",
    fin: "22:00",
    orden: 1,
    es_descanso: false,
    marca: "",
    marca_nombre: "",
    ...over,
  } as unknown as FranjaSemana;
}

function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "t1",
    semana: LUNES,
    fecha: "2026-07-01",
    miembro_id: "m1",
    miembro_nombre: "Ana",
    franja_id: "f-tarde",
    franja_nombre: "Tarde",
    franja: "vespertino",
    inicio: "14:00",
    fin: "22:00",
    es_descanso: false,
    ...over,
  } as unknown as TurnoRota;
}

function ausencia(over: Partial<AusenciaRota> = {}): AusenciaRota {
  return {
    id: "a1",
    miembro_id: "m1",
    miembro_nombre: "Ana",
    tipo: "vacaciones",
    desde: "2026-07-01",
    hasta: "2026-07-01",
    motivo: "",
    ...over,
  } as unknown as AusenciaRota;
}

/** Una rota de una semana con sus turnos + franjas. */
function semana(turnos: TurnoRota[], franjas: FranjaSemana[]): RotaSemana {
  return { turnos, franjas } as unknown as RotaSemana;
}

describe("derivarCoberturaPorDia", () => {
  it("un evento sin turno ni claim ese día → 1 evento, 1 sin cubrir", () => {
    const m = derivarCoberturaPorDia(MES, [ev()], [], new Map(), [], AHORA);
    const d = m.get("2026-07-01")!;
    expect(d.nEventos).toBe(1);
    expect(d.nSinCubrir).toBe(1);
    expect(d.hayAusencia).toBe(false);
  });

  it("un turno en la franja del evento lo cubre → 1 evento, 0 sin cubrir", () => {
    const porLunes = new Map([[LUNES, semana([turno()], [franja()])]]);
    const m = derivarCoberturaPorDia(MES, [ev()], [], porLunes, [], AHORA);
    expect(m.get("2026-07-01")!.nSinCubrir).toBe(0);
  });

  it("un claim con responsable lo cubre aunque no haya turno → 0 sin cubrir", () => {
    const m = derivarCoberturaPorDia(MES, [ev()], [claim()], new Map(), [], AHORA);
    expect(m.get("2026-07-01")!.nSinCubrir).toBe(0);
  });

  it("la persona de turno ausente NO cubre → vuelve a contar como sin cubrir", () => {
    const porLunes = new Map([[LUNES, semana([turno()], [franja()])]]);
    const m = derivarCoberturaPorDia(MES, [ev()], [], porLunes, [ausencia()], AHORA);
    const d = m.get("2026-07-01")!;
    expect(d.nSinCubrir).toBe(1);
    expect(d.hayAusencia).toBe(true);
  });

  it("excluye eventos `no_cubrir` del conteo", () => {
    const m = derivarCoberturaPorDia(
      MES,
      [ev({ tipo_cobertura: "no_cubrir" })],
      [],
      new Map(),
      [],
      AHORA,
    );
    expect(m.has("2026-07-01")).toBe(false);
  });

  it("agrega varios eventos del MISMO día", () => {
    const m = derivarCoberturaPorDia(
      MES,
      [ev({ id: "ev1" }), ev({ id: "ev2", hora: "10:00" })],
      [],
      new Map(),
      [],
      AHORA,
    );
    const d = m.get("2026-07-01")!;
    expect(d.nEventos).toBe(2);
    expect(d.nSinCubrir).toBe(2);
  });

  it("un día sin eventos NO emite entrada (la celda lo distingue como «sin eventos»)", () => {
    const m = derivarCoberturaPorDia(MES, [ev({ fecha: "2026-07-05" })], [], new Map(), [], AHORA);
    expect(m.has("2026-07-01")).toBe(false);
    expect(m.has("2026-07-05")).toBe(true);
  });

  it("un día con SOLO ausencia (sin eventos) sí se marca", () => {
    const m = derivarCoberturaPorDia(
      MES,
      [],
      [],
      new Map(),
      [ausencia({ desde: "2026-07-10", hasta: "2026-07-10" })],
      AHORA,
    );
    const d = m.get("2026-07-10")!;
    expect(d.nEventos).toBe(0);
    expect(d.hayAusencia).toBe(true);
  });

  it("ignora eventos fuera de la rejilla del mes", () => {
    const m = derivarCoberturaPorDia(MES, [ev({ fecha: "2026-09-15" })], [], new Map(), [], AHORA);
    expect(m.has("2026-09-15")).toBe(false);
  });
});
