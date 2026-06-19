/**
 * Tests para los helpers de MES de @/lib/rota-calendario (calendario mensual de «Mis
 * turnos»). Lo que importa es la aritmética de meses y la rejilla lun→dom: cruces de
 * año, alineación de la cuadrícula y pertenencia de una fecha al mes.
 */
import { describe, expect, it } from "vitest";

import {
  fechaMasDias,
  mesSiguiente,
  mismoMes,
  semanasDelMes,
} from "./rota-calendario";

describe("fechaMasDias — desplaza un día calendario conservando el día de la semana", () => {
  it("suma y resta días dentro del mes", () => {
    expect(fechaMasDias("2026-05-25", 7)).toBe("2026-06-01"); // +1 semana (lun→lun)
    expect(fechaMasDias("2026-06-01", -7)).toBe("2026-05-25");
  });

  it("cruza el fin de mes y de año", () => {
    expect(fechaMasDias("2026-05-28", 7)).toBe("2026-06-04");
    expect(fechaMasDias("2026-12-31", 7)).toBe("2027-01-07");
  });
});

describe("mesSiguiente — aritmética de meses (cruza año)", () => {
  it("avanza y retrocede dentro del año", () => {
    expect(mesSiguiente("2026-06", 1)).toBe("2026-07");
    expect(mesSiguiente("2026-06", -1)).toBe("2026-05");
  });

  it("cruza el fin de año en ambos sentidos", () => {
    expect(mesSiguiente("2026-12", 1)).toBe("2027-01");
    expect(mesSiguiente("2026-01", -1)).toBe("2025-12");
    expect(mesSiguiente("2026-06", 12)).toBe("2027-06");
  });
});

describe("mismoMes — pertenencia de una fecha a un mes", () => {
  it("distingue el mes del día", () => {
    expect(mismoMes("2026-06-01", "2026-06")).toBe(true);
    expect(mismoMes("2026-06-30", "2026-06")).toBe(true);
    expect(mismoMes("2026-07-01", "2026-06")).toBe(false);
    expect(mismoMes("2026-05-31", "2026-06")).toBe(false);
  });
});

describe("semanasDelMes — rejilla lun→dom que cubre el mes", () => {
  it("arranca en lunes, termina en domingo y cubre todo el mes", () => {
    const semanas = semanasDelMes("2026-06"); // jun 2026: 1 = lunes
    // Cada fila son 7 días; la primera empieza en lunes y la última acaba en domingo.
    for (const semana of semanas) expect(semana).toHaveLength(7);
    const plano = semanas.flat();
    expect(plano[0]).toBe("2026-06-01"); // lunes 1 jun
    // El primer y el último día del mes están presentes.
    expect(plano).toContain("2026-06-01");
    expect(plano).toContain("2026-06-30");
  });

  it("incluye días de relleno del mes vecino para alinear la cuadrícula", () => {
    // Mayo 2026 empieza en VIERNES; la primera fila trae días de abril como relleno.
    const plano = semanasDelMes("2026-05").flat();
    expect(plano[0]).toBe("2026-04-27"); // lunes de la semana del 1 de mayo
    expect(plano).toContain("2026-05-01");
    expect(plano).toContain("2026-05-31");
    // Solo días de relleno fuera del mes; nunca se pierde un día del mes.
    for (let d = 1; d <= 31; d += 1) {
      expect(plano).toContain(`2026-05-${String(d).padStart(2, "0")}`);
    }
  });
});
