import { describe, expect, it } from "vitest";

import { diaSemanaLunes0, diasDePreset, finDeMesISO } from "./recurrencia";

// 2026-06-15 = lunes; 2026-06-20 = sábado; 2026-06-21 = domingo.

describe("diaSemanaLunes0 (0=lunes … 6=domingo)", () => {
  it("mapea con lunes=0, no domingo=0 como getDay()", () => {
    expect(diaSemanaLunes0("2026-06-15")).toBe(0); // lunes
    expect(diaSemanaLunes0("2026-06-20")).toBe(5); // sábado
    expect(diaSemanaLunes0("2026-06-21")).toBe(6); // domingo
  });

  it("una fecha vacía o inválida cae a lunes (0)", () => {
    expect(diaSemanaLunes0("")).toBe(0);
    expect(diaSemanaLunes0("no-fecha")).toBe(0);
  });
});

describe("finDeMesISO", () => {
  it("devuelve el último día del mes de la fecha", () => {
    expect(finDeMesISO("2026-06-15")).toBe("2026-06-30");
    expect(finDeMesISO("2026-02-10")).toBe("2026-02-28"); // 2026 no bisiesto
    expect(finDeMesISO("2026-12-01")).toBe("2026-12-31");
  });

  it("vacía → vacía", () => {
    expect(finDeMesISO("")).toBe("");
  });
});

describe("diasDePreset", () => {
  it("los presets fijos no dependen de la fecha", () => {
    expect(diasDePreset("laborables", "2026-06-15")).toEqual([0, 1, 2, 3, 4]);
    expect(diasDePreset("fin_de_semana", "2026-06-15")).toEqual([5, 6]);
    expect(diasDePreset("diario", "2026-06-15")).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it("«semanal» usa el día de la semana de la base", () => {
    expect(diasDePreset("semanal", "2026-06-15")).toEqual([0]); // lunes
    expect(diasDePreset("semanal", "2026-06-20")).toEqual([5]); // sábado
  });

  it("«no» y «personalizado» no aportan días (los pone el usuario)", () => {
    expect(diasDePreset("no", "2026-06-15")).toEqual([]);
    expect(diasDePreset("personalizado", "2026-06-15")).toEqual([]);
  });
});
