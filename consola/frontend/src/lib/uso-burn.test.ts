import { describe, expect, it } from "vitest";

import type { UsoCuenta } from "@/hooks/use-uso-cuenta";
import { limiteMasUrgente } from "@/lib/uso-burn";

const AHORA = Date.parse("2026-06-15T12:00:00Z");

function uso(parcial: Partial<UsoCuenta>): UsoCuenta {
  return {
    cuenta: "a",
    etiqueta: "Cuenta A",
    marcas: ["claro-sports"],
    conectada: true,
    semana_pct: null,
    sesion_5h_pct: null,
    reset_semana_iso: null,
    reset_semana_txt: null,
    reset_sesion_iso: null,
    actualizado_ts: null,
    al_100: false,
    alerta_roja: false,
    dia: { consumo_pct: null, umbral_pct: 14.3, limite: "semanal", pausado: false },
    ...parcial,
  };
}

describe("limiteMasUrgente", () => {
  it("elige la ventana que ANTES toca el 100%, no la de mayor %", () => {
    const u = uso({
      // sesión 5h: 80% a 3 h del inicio de su ventana -> ~26.7%/h -> llena en ~0.75 h.
      sesion_5h_pct: 80,
      reset_sesion_iso: "2026-06-15T14:00:00Z",
      // semana: 50% en 2 días -> llena en ~48 h (mucho más tarde).
      semana_pct: 50,
      reset_semana_iso: "2026-06-20T12:00:00Z",
    });
    const p = limiteMasUrgente(u, AHORA);
    expect(p?.limite).toBe("sesion");
    expect(p?.etiqueta).toBe("5h");
    expect(p?.pct).toBe(80);
    expect(p?.horas).toBeCloseTo(0.75, 2);
  });

  it("descarta la ventana que RESETEA antes de llenarse", () => {
    // sesión 5h muy lenta (5% en 1h): a su ritmo no llega al 100% antes de su propio reset -> no bloquea.
    const u = uso({
      sesion_5h_pct: 5,
      reset_sesion_iso: "2026-06-15T16:00:00Z",
      semana_pct: 50,
      reset_semana_iso: "2026-06-20T12:00:00Z",
    });
    const p = limiteMasUrgente(u, AHORA);
    expect(p?.limite).toBe("semana"); // sesión se descarta; gana la semana
  });

  it("pct >= 100 bloquea ya (horas 0) y gana", () => {
    const u = uso({
      sesion_5h_pct: 100,
      reset_sesion_iso: "2026-06-15T14:00:00Z",
      semana_pct: 90,
      reset_semana_iso: "2026-06-15T13:00:00Z",
    });
    const p = limiteMasUrgente(u, AHORA);
    expect(p?.limite).toBe("sesion");
    expect(p?.horas).toBe(0);
  });

  it("sin reset o sin %: esa ventana no cuenta", () => {
    const u = uso({ sesion_5h_pct: 90, reset_sesion_iso: null }); // % sin reset -> se omite
    expect(limiteMasUrgente(u, AHORA)).toBeNull();
  });

  it("todo nulo -> null (sin dato para predecir)", () => {
    expect(limiteMasUrgente(uso({}), AHORA)).toBeNull();
  });

  it("pct 0 no se llena (se omite)", () => {
    const u = uso({ semana_pct: 0, reset_semana_iso: "2026-06-20T12:00:00Z" });
    expect(limiteMasUrgente(u, AHORA)).toBeNull();
  });
});
