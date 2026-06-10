/**
 * Tests del cálculo de correlación (ρ de Spearman) con datos sintéticos:
 * perfecta positiva, nula, robustez a outliers/empates y casos no calculables.
 */
import { describe, expect, it } from "vitest";

import { N_MINIMA_CORRELACION, spearman } from "./estadistica";

describe("spearman", () => {
  it("relación monótona perfecta positiva → ρ = 1 (aunque no sea lineal)", () => {
    const xs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    // Lineal:
    expect(spearman(xs, xs.map((x) => 3 * x + 2))).toBeCloseTo(1, 10);
    // Monótona NO lineal (cuadrática): Pearson < 1, Spearman = 1.
    expect(spearman(xs, xs.map((x) => x * x))).toBeCloseTo(1, 10);
  });

  it("relación monótona perfecta negativa → ρ = −1", () => {
    const xs = [1, 2, 3, 4, 5, 6, 7, 8];
    expect(spearman(xs, xs.map((x) => -x))).toBeCloseTo(-1, 10);
  });

  it("sin relación (patrón simétrico) → ρ = 0", () => {
    const xs = [1, 2, 3, 4, 5, 6, 7, 8];
    const ys = [1, 2, 3, 4, 4, 3, 2, 1]; // sube y baja en espejo: rangos descorrelacionados
    expect(spearman(xs, ys)).toBeCloseTo(0, 10);
  });

  it("es robusto a un outlier extremo (día viral): los rangos no se disparan", () => {
    const xs = [1, 2, 3, 4, 5, 6, 7, 8];
    const ys = [10, 20, 30, 40, 50, 60, 70, 1_000_000]; // outlier brutal en el último día
    expect(spearman(xs, ys)).toBeCloseTo(1, 10); // sigue siendo monótona perfecta
  });

  it("maneja empates con rango promedio (n_posts repite valores pequeños)", () => {
    // x con empates; y perfectamente alineada con el orden de los grupos.
    const xs = [0, 0, 1, 1, 2, 2, 3, 3];
    const ys = [1, 2, 3, 4, 5, 6, 7, 8];
    const rho = spearman(xs, ys);
    expect(rho).not.toBeNull();
    expect(rho!).toBeGreaterThan(0.9); // fuerte, aunque < 1 por los empates en x
    expect(rho!).toBeLessThanOrEqual(1);
  });

  it("vector constante (sin varianza) → null, no un número inventado", () => {
    expect(spearman([1, 1, 1, 1, 1, 1, 1, 1], [1, 2, 3, 4, 5, 6, 7, 8])).toBeNull();
    expect(spearman([1, 2, 3, 4, 5, 6, 7, 8], [5, 5, 5, 5, 5, 5, 5, 5])).toBeNull();
  });

  it("n insuficiente para calcular (n < 2) o vectores desparejos → null", () => {
    expect(spearman([], [])).toBeNull();
    expect(spearman([1], [2])).toBeNull();
    expect(spearman([1, 2, 3], [1, 2])).toBeNull();
  });

  it("la guarda de la UI exige al menos 8 pares", () => {
    // El umbral es contrato de presentación: por debajo se muestra
    // «n insuficiente para estimar correlación» en vez del coeficiente.
    expect(N_MINIMA_CORRELACION).toBe(8);
  });
});
