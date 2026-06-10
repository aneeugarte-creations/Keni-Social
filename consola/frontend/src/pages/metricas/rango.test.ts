/**
 * Tests de `parComparable` (guarda de comparabilidad de los deltas de KPI): A y B
 * SIEMPRE de la misma duración, con el mes en curso recortado a los días
 * transcurridos. Se fija "hoy" (CDMX) en 2026-06-10 mockeando `hoyCDMX`.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { hoyCDMX } from "@/lib/fecha";

import { parComparable } from "./rango";

vi.mock("@/lib/fecha", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/fecha")>();
  return { ...real, hoyCDMX: vi.fn(() => "2026-06-10") };
});

beforeEach(() => {
  vi.mocked(hoyCDMX).mockReturnValue("2026-06-10");
});

describe("parComparable — mes en curso", () => {
  it("compara los días transcurridos con los MISMOS días del mes anterior", () => {
    // A 10 de junio, mes:2026-06 son 10 días de datos: 1–10 jun vs 1–10 may,
    // nunca 10 días contra los 31 de mayo (desplome espurio).
    expect(parComparable("mes:2026-06")).toEqual({
      rangoA: "rango:2026-05-01_2026-05-10",
      rangoB: "rango:2026-06-01_2026-06-10",
      enCurso: true,
    });
  });

  it("el primer día del mes compara 1 día contra 1 día", () => {
    vi.mocked(hoyCDMX).mockReturnValue("2026-06-01");
    expect(parComparable("mes:2026-06")).toEqual({
      rangoA: "rango:2026-05-01_2026-05-01",
      rangoB: "rango:2026-06-01_2026-06-01",
      enCurso: true,
    });
  });

  it("un mes íntegramente FUTURO no tiene par comparable (null, sin % espurio)", () => {
    expect(parComparable("mes:2026-07")).toBeNull();
  });
});

describe("parComparable — mes cerrado", () => {
  it("compara el mes de N días con los primeros N días del mes anterior", () => {
    // Abril (30 d) vs 1–30 de marzo: misma duración, alineado al ciclo mensual.
    expect(parComparable("mes:2026-04")).toEqual({
      rangoA: "rango:2026-03-01_2026-03-30",
      rangoB: "mes:2026-04",
      enCurso: false,
    });
  });

  it("febrero (28 d) se compara con 1–28 de enero, nunca 28 vs 31 días", () => {
    expect(parComparable("mes:2026-02")).toEqual({
      rangoA: "rango:2026-01-01_2026-01-28",
      rangoB: "mes:2026-02",
      enCurso: false,
    });
  });

  it("si el mes anterior es más corto, cae a la ventana adyacente de la misma duración", () => {
    // Mayo (31 d): abril solo tiene 30 → ventana de 31 días terminando el 30 de abril.
    expect(parComparable("mes:2026-05")).toEqual({
      rangoA: "rango:2026-03-31_2026-04-30",
      rangoB: "mes:2026-05",
      enCurso: false,
    });
    // Marzo (31 d) vs febrero (28 d): ventana de 31 días terminando el 28 de febrero.
    expect(parComparable("mes:2026-03")).toEqual({
      rangoA: "rango:2026-01-29_2026-02-28",
      rangoB: "mes:2026-03",
      enCurso: false,
    });
  });

  it("enero compara con los mismos días de diciembre del año anterior", () => {
    expect(parComparable("mes:2026-01")).toEqual({
      rangoA: "rango:2025-12-01_2025-12-31",
      rangoB: "mes:2026-01",
      enCurso: false,
    });
  });
});

describe("parComparable — presets y rangos", () => {
  it("semana cerrada: la semana natural anterior, misma duración (7 vs 7 días)", () => {
    // Hoy mié 10 jun → semana cerrada = lun 1–dom 7 jun; anterior = 25–31 may.
    expect(parComparable("semana_cerrada")).toEqual({
      rangoA: "rango:2026-05-25_2026-05-31",
      rangoB: "semana_cerrada",
      enCurso: false,
    });
  });

  it("preset rodante (mes = 30 días): ventana adyacente de 30 días", () => {
    expect(parComparable("mes")).toEqual({
      rangoA: "rango:2026-04-12_2026-05-11",
      rangoB: "mes",
      enCurso: false,
    });
  });

  it("un rango personalizado que invade el futuro se recorta a hoy antes de derivar A", () => {
    expect(parComparable("rango:2026-06-01_2026-06-30")).toEqual({
      rangoA: "rango:2026-05-22_2026-05-31",
      rangoB: "rango:2026-06-01_2026-06-10",
      enCurso: true,
    });
  });

  it("un rango íntegramente futuro o un token irresoluble dan null", () => {
    expect(parComparable("rango:2026-07-01_2026-07-15")).toBeNull();
    expect(parComparable("garabato")).toBeNull();
  });
});
