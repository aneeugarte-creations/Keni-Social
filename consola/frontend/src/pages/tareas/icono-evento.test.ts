import { describe, expect, it } from "vitest";

import { esPartido } from "./icono-evento";

describe("esPartido — copa solo para partidos «Equipo vs Equipo»", () => {
  it("reconoce partidos (vs / VS / vs.)", () => {
    expect(esPartido("España vs Cabo Verde")).toBe(true);
    expect(esPartido("Argentina VS Austria")).toBe(true);
    expect(esPartido("Real Madrid vs. Barcelona")).toBe(true);
  });

  it("NO marca como partido las noticias y demás coberturas", () => {
    expect(esPartido("Conferencia de prensa")).toBe(false);
    expect(esPartido("Noticias del día")).toBe(false);
    expect(esPartido("Resumen semanal")).toBe(false);
    expect(esPartido("")).toBe(false);
    // No confundir substrings: «vs» pegado a otra palabra no es un partido.
    expect(esPartido("Avstria gana")).toBe(false);
  });

  it("los huecos de cuadro (sin «vs») se tratan como no-partido", () => {
    // Slot de eliminatoria aún sin rivales: «R32 · 73 · 1° A a 2° B».
    expect(esPartido("R32 · 73 · 1° A a 2° B")).toBe(false);
  });
});
