import { describe, expect, it } from "vitest";

import {
  PLANTILLA_DEFECTO,
  PLANTILLA_GRANDE,
  PLANTILLA_NORMAL,
  plantillaParaTipo,
} from "./guion";
import { ROLES_COBERTURA } from "./roles";

describe("guion — plantillas de matchday por fases", () => {
  it("la plantilla normal tiene las 3 fases en orden (pre/vivo/post)", () => {
    expect(PLANTILLA_NORMAL.fases.map((f) => f.id)).toEqual(["pre", "vivo", "post"]);
  });

  it("cubre los entregables canónicos por fase", () => {
    const porFase = Object.fromEntries(
      PLANTILLA_NORMAL.fases.map((f) => [f.id, f.entregables.map((e) => e.titulo)]),
    );
    expect(porFase.pre).toContain("Gráfico de matchday");
    expect(porFase.vivo).toContain("Gol o clip");
    expect(porFase.post).toContain("Jugador del partido");
  });

  it("cada rol de cobertura aparece en al menos un entregable (mapeo ejercitable)", () => {
    const roles = new Set(
      PLANTILLA_NORMAL.fases.flatMap((f) => f.entregables.map((e) => e.rol).filter(Boolean)),
    );
    for (const r of ROLES_COBERTURA) expect(roles.has(r)).toBe(true);
  });

  it("«Partido grande» extiende al normal (más entregables, mismas fases)", () => {
    const nNormal = PLANTILLA_NORMAL.fases.reduce((n, f) => n + f.entregables.length, 0);
    const nGrande = PLANTILLA_GRANDE.fases.reduce((n, f) => n + f.entregables.length, 0);
    expect(nGrande).toBeGreaterThan(nNormal);
    expect(PLANTILLA_GRANDE.fases.map((f) => f.id)).toEqual(["pre", "vivo", "post"]);
  });

  it("la fase de directo se etiqueta «Durante el partido», no «En vivo» (no choca con el semáforo)", () => {
    const vivo = PLANTILLA_NORMAL.fases.find((f) => f.id === "vivo");
    expect(vivo?.etiqueta).toBe("Durante el partido");
    expect(PLANTILLA_NORMAL.fases.map((f) => f.etiqueta)).not.toContain("En vivo");
  });

  it("plantillaParaTipo: tamaño desconocido o vacío → default (Partido normal)", () => {
    expect(plantillaParaTipo()).toBe(PLANTILLA_DEFECTO);
    expect(plantillaParaTipo(null)).toBe(PLANTILLA_DEFECTO);
    expect(plantillaParaTipo("inexistente")).toBe(PLANTILLA_DEFECTO);
    expect(PLANTILLA_DEFECTO).toBe(PLANTILLA_NORMAL);
    // El dial sí resuelve un tamaño conocido cuando se le pasa explícito.
    expect(plantillaParaTipo("grande")).toBe(PLANTILLA_GRANDE);
  });
});
