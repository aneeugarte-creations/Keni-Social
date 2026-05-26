/**
 * Tests para @/lib/formato — utilidades de formato es-MX compartidas.
 *
 * Cubre todos los helpers: numeroCompacto, numeroCompleto, porcentaje,
 * variacion, costeUsd y duracion; incluyendo valores límite y no finitos.
 */
import { describe, expect, it } from "vitest";

import {
  costeUsd,
  duracion,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
  variacion,
} from "./formato";

// ---------------------------------------------------------------------------
// numeroCompacto
// ---------------------------------------------------------------------------
describe("numeroCompacto", () => {
  it("devuelve — para valores no finitos", () => {
    expect(numeroCompacto(NaN)).toBe("—");
    expect(numeroCompacto(Infinity)).toBe("—");
    expect(numeroCompacto(-Infinity)).toBe("—");
  });

  it("devuelve el entero sin abreviar para valores < 1000", () => {
    expect(numeroCompacto(0)).toBe("0");
    expect(numeroCompacto(842)).toBe("842");
    expect(numeroCompacto(999)).toBe("999");
  });

  it("abrevia con notación compacta para valores >= 1000", () => {
    // El símbolo compacto de miles varía según la implementación de ICU en el
    // entorno (Node full-ICU → "mil", Node sin ICU completo → "k").
    const mil = numeroCompacto(1830);
    expect(mil).toMatch(/mil|k/i);

    // 221_621_046 → "221.6 M" o "221.6 M." según ICU, siempre contiene dígitos y M
    const millones = numeroCompacto(221_621_046);
    expect(millones).toMatch(/\d.*[Mm]/);
  });

  it("maneja negativos pequeños sin abreviar", () => {
    expect(numeroCompacto(-500)).toBe("-500");
  });
});

// ---------------------------------------------------------------------------
// numeroCompleto
// ---------------------------------------------------------------------------
describe("numeroCompleto", () => {
  it("devuelve — para valores no finitos", () => {
    expect(numeroCompleto(NaN)).toBe("—");
  });

  it("formatea con separadores de miles es-MX", () => {
    // En es-MX el separador de miles es coma: 1,234,567
    const resultado = numeroCompleto(1_234_567);
    expect(resultado).toBe("1,234,567");
  });

  it("formatea cero", () => {
    expect(numeroCompleto(0)).toBe("0");
  });
});

// ---------------------------------------------------------------------------
// porcentaje
// ---------------------------------------------------------------------------
describe("porcentaje", () => {
  it("devuelve — para valores no finitos", () => {
    expect(porcentaje(NaN)).toBe("—");
  });

  it("incluye un decimal y el símbolo %", () => {
    const r = porcentaje(1.8);
    expect(r).toContain("%");
    expect(r).toContain("1");
    expect(r).toContain("8");
  });

  it("formatea cero correctamente", () => {
    expect(porcentaje(0)).toContain("0.0");
  });
});

// ---------------------------------------------------------------------------
// variacion
// ---------------------------------------------------------------------------
describe("variacion", () => {
  it("devuelve — para valores no finitos", () => {
    expect(variacion(NaN)).toBe("—");
  });

  it("añade + para valores positivos", () => {
    expect(variacion(12.345)).toContain("+");
  });

  it("añade − (menos tipográfico) para valores negativos", () => {
    // El signo menos tipográfico (U+2212) se distingue del ASCII '-'
    expect(variacion(-4)).toContain("−");
  });

  it("no añade signo para cero", () => {
    const r = variacion(0);
    expect(r).not.toContain("+");
    expect(r).not.toContain("−");
  });

  it("incluye un decimal y el símbolo %", () => {
    expect(variacion(5)).toContain("%");
  });
});

// ---------------------------------------------------------------------------
// costeUsd
// ---------------------------------------------------------------------------
describe("costeUsd", () => {
  it("devuelve — para valores no finitos", () => {
    expect(costeUsd(NaN)).toBe("—");
  });

  it("usa 3 decimales para importes muy pequeños (< $0.10)", () => {
    const r = costeUsd(0.0381);
    // Debe contener 3 dígitos después del separador decimal
    expect(r).toMatch(/\.\d{3}/);
  });

  it("usa 2 decimales para importes normales", () => {
    const r = costeUsd(1.5);
    expect(r).toMatch(/\.\d{2}$/);
  });

  it("incluye una referencia a USD (símbolo $ o literal 'USD' según ICU)", () => {
    // Node sin full-ICU puede producir "USD 0.00" en lugar de "$0.00".
    const r = costeUsd(0);
    expect(r).toMatch(/\$|USD/);
  });
});

// ---------------------------------------------------------------------------
// duracion
// ---------------------------------------------------------------------------
describe("duracion", () => {
  it("devuelve — para valores no finitos o negativos", () => {
    expect(duracion(NaN)).toBe("—");
    expect(duracion(-1)).toBe("—");
  });

  it("formatea menos de 60 segundos con 1 decimal y 's'", () => {
    const r = duracion(850);
    expect(r).toContain("s");
    // 0.9 s
    expect(r).toMatch(/0[.,]9/);
  });

  it("formatea 60+ segundos como 'X min Y s'", () => {
    // 95 000 ms → 95 s → 1 min 35 s
    const r = duracion(95_000);
    expect(r).toContain("min");
    expect(r).toContain("1");
    expect(r).toContain("35");
  });

  it("formatea exactamente 60 segundos (1 min 0 s)", () => {
    const r = duracion(60_000);
    expect(r).toContain("min");
    expect(r).toContain("1");
  });
});
