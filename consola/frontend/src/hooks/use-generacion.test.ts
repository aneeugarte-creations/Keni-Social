/**
 * Tests para useGeneracion (#118 A-1):
 *  - Cuando POST responde ya "completado" (completado-inmediato), el sondeo
 *    NO debe depender de initialData; la query parte de undefined y el estado
 *    local se usa como fallback.
 *  - El sondeo arranca cuando el estado es "ejecutando".
 *  - El sondeo se detiene cuando el estado pasa a "completado".
 */
import { describe, expect, it } from "vitest";

import { estaEjecutando } from "./use-generacion";

describe("estaEjecutando (#118 A-1)", () => {
  it('devuelve true solo para estado "ejecutando"', () => {
    expect(estaEjecutando("ejecutando")).toBe(true);
  });

  it('devuelve false para "completado"', () => {
    expect(estaEjecutando("completado")).toBe(false);
  });

  it('devuelve false para "error"', () => {
    expect(estaEjecutando("error")).toBe(false);
  });

  it("devuelve false para undefined (completado-inmediato antes del primer fetch)", () => {
    // Caso A-1: cuando la query aún no tiene data (undefined), el refetchInterval
    // evalúa generacion?.estado. Si el estado local ya es "completado" (el POST
    // respondió directamente con completado), estaEjecutando debe devolver false
    // para que no se inicie un sondeo innecesario.
    expect(estaEjecutando(undefined)).toBe(false);
  });

  it("devuelve false para string vacío", () => {
    expect(estaEjecutando("")).toBe(false);
  });
});
