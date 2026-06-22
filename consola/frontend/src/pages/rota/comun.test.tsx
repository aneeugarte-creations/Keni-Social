import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { lunesDeSemana } from "@/lib/rota-calendario";
import type { FranjaSemana, SwapTurno } from "@/types";

import {
  contarSwapsPendientes,
  eventosFueraDeFranja,
  franjaIdParaHoraEvento,
  franjasSolapan,
  horaAMinutos,
  horaEnRangoFranja,
  NavegadorSemana,
} from "./comun";

function franja(over: Partial<FranjaSemana> = {}): FranjaSemana {
  return {
    id: "f-manana",
    lunes: "2026-06-15",
    nombre: "Mañana",
    inicio: "08:00",
    fin: "14:00",
    orden: 0,
    es_descanso: false,
    marca: "",
    marca_nombre: "",
    ...over,
  } as unknown as FranjaSemana;
}

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

describe("horaAMinutos", () => {
  it("parsea horas normales", () => {
    expect(horaAMinutos("00:00")).toBe(0);
    expect(horaAMinutos("16:00")).toBe(960);
    expect(horaAMinutos("23:59")).toBe(1439);
  });

  it("acepta «24:00» como 1440 (fin exclusivo de jornada), igual que el backend", () => {
    expect(horaAMinutos("24:00")).toBe(1440);
  });

  it("rechaza «24:30» y horas malformadas", () => {
    expect(horaAMinutos("24:30")).toBeNull();
    expect(horaAMinutos("25:00")).toBeNull();
    expect(horaAMinutos("ab:cd")).toBeNull();
    expect(horaAMinutos("12:60")).toBeNull();
  });
});

describe("franja Tarde 16:00–24:00 (regresión: «24:00» no debe romper el bucketizado)", () => {
  const tarde = franja({ id: "f-tarde", inicio: "16:00", fin: "24:00", orden: 1 });

  it("horaEnRangoFranja contiene 16:00–23:59 y no degenera", () => {
    expect(horaEnRangoFranja("16:00", tarde.inicio, tarde.fin)).toBe(true);
    expect(horaEnRangoFranja("23:59", tarde.inicio, tarde.fin)).toBe(true);
    expect(horaEnRangoFranja("15:59", tarde.inicio, tarde.fin)).toBe(false);
  });

  it("franjaIdParaHoraEvento manda los eventos de la tarde a la franja Tarde", () => {
    const manana = franja({ id: "f-manana", inicio: "08:00", fin: "16:00", orden: 0 });
    expect(franjaIdParaHoraEvento("20:00", [manana, tarde])).toBe("f-tarde");
  });

  it("franjasSolapan detecta el solape Mañana/Tarde si comparten el corte", () => {
    const manana = franja({ id: "f-manana", inicio: "08:00", fin: "16:30", orden: 0 });
    expect(franjasSolapan(manana, tarde)).toBe(true);
  });
});

describe("eventosFueraDeFranja", () => {
  it("sin franjas configuradas, TODOS los eventos quedan fuera de franja (no se pierden)", () => {
    const evs = [{ hora: "10:00" }, { hora: "20:00" }];
    expect(eventosFueraDeFranja(evs, [])).toHaveLength(2);
  });

  it("con una franja que cubre la hora, ningún evento queda fuera", () => {
    const franjas = [franja({ inicio: "08:00", fin: "22:00" })];
    expect(eventosFueraDeFranja([{ hora: "10:00" }], franjas)).toHaveLength(0);
  });

  it("con franjas, una hora que no encaja NO queda fuera (cae al fallback de franja), no se pierde", () => {
    const franjas = [franja({ inicio: "08:00", fin: "14:00" })];
    expect(eventosFueraDeFranja([{ hora: "23:00" }], franjas)).toHaveLength(0);
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
