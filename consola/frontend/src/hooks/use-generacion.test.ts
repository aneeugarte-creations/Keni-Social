/**
 * Tests para useGeneracion (#118 A-1 + SSE):
 *  - Cuando POST responde ya "completado" (completado-inmediato), el sondeo
 *    NO debe depender de initialData; la query parte de undefined y el estado
 *    local se usa como fallback.
 *  - El sondeo arranca cuando el estado es "ejecutando".
 *  - El sondeo se detiene cuando el estado pasa a "completado".
 *  - `instantaneaMasAvanzada` (SSE): al convivir dos transportes (eventos SSE +
 *    fetches del sondeo de fallback), la vista nunca retrocede.
 */
import { describe, expect, it } from "vitest";

import type { Generacion } from "@/types";

import { estaEjecutando, instantaneaMasAvanzada } from "./use-generacion";

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

/** Generación mínima para los tests del merge (solo los campos que el merge mira). */
function gen(parcial: Partial<Generacion>): Generacion {
  return {
    id: "abc123abc123",
    tipo: "copy",
    marca: "unotv",
    etiqueta: "X",
    estado: "ejecutando",
    fase: "",
    motivo: "",
    salida: "",
    error: "",
    metricas: null,
    resultado: null,
    fecha_inicio: "2026-06-09T10:00:00",
    fecha_fin: "",
    ...parcial,
  } as Generacion;
}

describe("instantaneaMasAvanzada (SSE + sondeo conviviendo)", () => {
  it("con un solo lado, devuelve el que haya", () => {
    const a = gen({ salida: "hola" });
    expect(instantaneaMasAvanzada(a, null)).toBe(a);
    expect(instantaneaMasAvanzada(null, a)).toBe(a);
    expect(instantaneaMasAvanzada(null, null)).toBeNull();
  });

  it("una instantánea terminal gana a una en curso (no retrocede a 'ejecutando')", () => {
    const terminal = gen({ estado: "completado", salida: "todo" });
    const enCurso = gen({ estado: "ejecutando", salida: "todo y más texto rezagado" });
    expect(instantaneaMasAvanzada(terminal, enCurso)).toBe(terminal);
    expect(instantaneaMasAvanzada(enCurso, terminal)).toBe(terminal);
  });

  it("a igualdad de estado gana la que acumula más texto (salida + razonamiento)", () => {
    const corta = gen({ salida: "hola" });
    const larga = gen({ salida: "hola mundo", razonamiento: "pensando…" });
    expect(instantaneaMasAvanzada(corta, larga)).toBe(larga);
    expect(instantaneaMasAvanzada(larga, corta)).toBe(larga);
  });

  it("en empate exacto conserva la primera (estable: sin re-render espurio)", () => {
    const a = gen({ salida: "igual" });
    const b = gen({ salida: "igual" });
    expect(instantaneaMasAvanzada(a, b)).toBe(a);
  });

  it("si los ids difieren manda la primera (la generación recién lanzada no se pisa)", () => {
    const nueva = gen({ id: "nueva0000001", salida: "" });
    const vieja = gen({ id: "vieja0000001", estado: "completado", salida: "muchísimo texto" });
    expect(instantaneaMasAvanzada(nueva, vieja)).toBe(nueva);
  });
});
