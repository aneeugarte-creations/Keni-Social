import { describe, expect, it } from "vitest";

import type { AusenciaRota, FranjaSemana, TurnoRota } from "@/types";

import {
  conflictosDelDia,
  formatearMinutos,
  horarioEfectivo,
  horasTotalesDelDia,
  minutosTurno,
} from "./ResumenDia";

// --- Factorías compactas (cast por brevedad: los helpers solo leen unos campos) ---------------

function franja(over: Partial<FranjaSemana> = {}): FranjaSemana {
  return {
    id: "f-manana",
    lunes: "2026-06-15",
    nombre: "Mañana",
    inicio: "08:00",
    fin: "16:00",
    orden: 0,
    es_descanso: false,
    marca: "",
    marca_nombre: "",
    ...over,
  } as unknown as FranjaSemana;
}

function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "t1",
    semana: "2026-06-15",
    fecha: "2026-06-17",
    miembro_id: "u1",
    miembro_nombre: "Luis",
    franja_id: "f-manana",
    franja_nombre: "Mañana",
    inicio: "",
    fin: "",
    ...over,
  } as unknown as TurnoRota;
}

function ausencia(over: Partial<AusenciaRota> = {}): AusenciaRota {
  return {
    id: "a1",
    miembro_id: "u1",
    miembro_nombre: "Luis",
    tipo: "vacaciones",
    desde: "2026-06-17",
    hasta: "2026-06-17",
    motivo: "",
    ...over,
  } as unknown as AusenciaRota;
}

const mapa = (fs: FranjaSemana[]) => new Map(fs.map((f) => [f.id, f]));

describe("minutosTurno — duración de un horario (con cruce de medianoche)", () => {
  it("rango normal", () => {
    expect(minutosTurno("08:00", "16:00")).toBe(480);
    expect(minutosTurno("09:30", "10:00")).toBe(30);
  });
  it("cruce de medianoche (fin <= inicio) suma 24h", () => {
    expect(minutosTurno("22:00", "02:00")).toBe(240);
    expect(minutosTurno("17:00", "01:00")).toBe(480);
  });
  it("rango degenerado / hora inválida = 0", () => {
    expect(minutosTurno("10:00", "10:00")).toBe(0);
    expect(minutosTurno("nope", "16:00")).toBe(0);
  });
  it("«24:00» como fin", () => {
    expect(minutosTurno("16:00", "24:00")).toBe(480);
  });
});

describe("horarioEfectivo — horas propias o heredadas de la franja", () => {
  it("usa las horas propias del turno si las tiene", () => {
    const fp = mapa([franja()]);
    expect(horarioEfectivo(turno({ inicio: "07:00", fin: "15:00" }), fp)).toEqual({
      inicio: "07:00",
      fin: "15:00",
    });
  });
  it("hereda de la franja si el turno no trae horas", () => {
    const fp = mapa([franja({ inicio: "08:00", fin: "16:00" })]);
    expect(horarioEfectivo(turno(), fp)).toEqual({ inicio: "08:00", fin: "16:00" });
  });
  it("franja desconocida y sin horas propias = vacío", () => {
    expect(horarioEfectivo(turno({ franja_id: "fantasma" }), mapa([]))).toEqual({
      inicio: "",
      fin: "",
    });
  });
});

describe("horasTotalesDelDia — suma de minutos de los turnos del día", () => {
  it("suma horas heredadas y a medida; ignora la franja de descanso", () => {
    const fp = mapa([
      franja({ id: "f-manana", inicio: "08:00", fin: "16:00" }),
      franja({ id: "f-tarde", nombre: "Tarde", inicio: "16:00", fin: "22:00", orden: 1 }),
      franja({ id: "f-descanso", nombre: "Descanso", es_descanso: true, inicio: "00:00", fin: "00:00", orden: 999 }),
    ]);
    const turnos = [
      turno({ id: "t1", miembro_id: "u1", franja_id: "f-manana" }), // 480 (hereda)
      turno({ id: "t2", miembro_id: "u2", franja_id: "f-tarde", inicio: "16:00", fin: "20:00" }), // 240 (a medida)
      turno({ id: "t3", miembro_id: "u3", franja_id: "f-descanso", franja_nombre: "Descanso" }), // 0 (descanso)
    ];
    expect(horasTotalesDelDia(turnos, fp)).toBe(720);
  });
  it("sin turnos = 0", () => {
    expect(horasTotalesDelDia([], mapa([franja()]))).toBe(0);
  });
});

describe("formatearMinutos", () => {
  it("formatea horas y minutos", () => {
    expect(formatearMinutos(0)).toBe("0 min");
    expect(formatearMinutos(45)).toBe("45 min");
    expect(formatearMinutos(60)).toBe("1 h");
    expect(formatearMinutos(90)).toBe("1 h 30 min");
    expect(formatearMinutos(480)).toBe("8 h");
  });
});

describe("conflictosDelDia — solapes y ausentes con turno", () => {
  it("avisa de un solape de la MISMA persona en dos franjas que comparten horas", () => {
    const fp = mapa([
      franja({ id: "f-manana", nombre: "Mañana", inicio: "08:00", fin: "16:00" }),
      franja({ id: "f-tarde", nombre: "Tarde", inicio: "14:00", fin: "22:00", orden: 1 }),
    ]);
    const turnos = [
      turno({ id: "t1", miembro_id: "u1", miembro_nombre: "Luis", franja_id: "f-manana", franja_nombre: "Mañana" }),
      turno({ id: "t2", miembro_id: "u1", miembro_nombre: "Luis", franja_id: "f-tarde", franja_nombre: "Tarde" }),
    ];
    const r = conflictosDelDia("2026-06-17", turnos, fp, []);
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ tipo: "solape", miembroNombre: "Luis" });
  });

  it("NO avisa si las franjas no comparten horas", () => {
    const fp = mapa([
      franja({ id: "f-manana", inicio: "08:00", fin: "14:00" }),
      franja({ id: "f-tarde", nombre: "Tarde", inicio: "14:00", fin: "22:00", orden: 1 }),
    ]);
    const turnos = [
      turno({ id: "t1", miembro_id: "u1", franja_id: "f-manana" }),
      turno({ id: "t2", miembro_id: "u1", franja_id: "f-tarde" }),
    ];
    expect(conflictosDelDia("2026-06-17", turnos, fp, [])).toHaveLength(0);
  });

  it("avisa de una persona de turno que está de ausencia ese día (una vez)", () => {
    const fp = mapa([franja()]);
    const turnos = [
      turno({ id: "t1", miembro_id: "u1", miembro_nombre: "Luis" }),
      turno({ id: "t2", miembro_id: "u1", miembro_nombre: "Luis", franja_id: "f-manana" }),
    ];
    const r = conflictosDelDia(
      "2026-06-17",
      turnos,
      fp,
      [ausencia({ miembro_id: "u1", desde: "2026-06-15", hasta: "2026-06-20" })],
    );
    const ausencias = r.filter((x) => x.tipo === "ausencia");
    expect(ausencias).toHaveLength(1);
    expect(ausencias[0]).toMatchObject({ miembroNombre: "Luis" });
  });

  it("la ausencia de otra persona / fuera del rango no avisa", () => {
    const fp = mapa([franja()]);
    const turnos = [turno({ miembro_id: "u1" })];
    expect(
      conflictosDelDia("2026-06-17", turnos, fp, [
        ausencia({ miembro_id: "u2", desde: "2026-06-17", hasta: "2026-06-17" }),
      ]),
    ).toHaveLength(0);
    expect(
      conflictosDelDia("2026-06-17", turnos, fp, [
        ausencia({ miembro_id: "u1", desde: "2026-06-18", hasta: "2026-06-20" }),
      ]),
    ).toHaveLength(0);
  });
});
