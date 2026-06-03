/**
 * Tests para @/lib/fecha — fechas/horas ancladas a CDMX (America/Mexico_City).
 *
 * Lo importante NO es el texto localizado exacto (depende de la versión de ICU del
 * runtime) sino la SEMÁNTICA de zona: un instante UTC se muestra/convierte a la hora
 * de pared CDMX correcta, y un ISO naive se interpreta como UTC (convención backend).
 * CDMX está en UTC-06:00 (sin horario de verano desde 2023).
 */
import { describe, expect, it } from "vitest";

import {
  aInstante,
  datetimeLocalAIso,
  formatearHora,
  isoADatetimeLocal,
  ZONA_CDMX,
} from "./fecha";

describe("aInstante", () => {
  it("trata un ISO sin zona como UTC", () => {
    // 22:00 UTC, naive (sin Z): debe ser el mismo instante que 22:00Z.
    expect(aInstante("2026-06-03T22:00:00")?.getTime()).toBe(
      new Date("2026-06-03T22:00:00Z").getTime(),
    );
  });

  it("respeta una zona explícita (Z u offset)", () => {
    expect(aInstante("2026-06-03T22:00:00Z")?.toISOString()).toBe("2026-06-03T22:00:00.000Z");
    expect(aInstante("2026-06-03T16:00:00-06:00")?.toISOString()).toBe(
      "2026-06-03T22:00:00.000Z",
    );
  });

  it("devuelve null para vacío o inválido", () => {
    expect(aInstante("")).toBeNull();
    expect(aInstante(null)).toBeNull();
    expect(aInstante("no-es-fecha")).toBeNull();
  });
});

describe("formatearHora (en CDMX)", () => {
  // No fijamos el texto localizado exacto ("04:00 p.m." vs "16:00") porque depende
  // de la versión de ICU del runtime; comprobamos la SEMÁNTICA de zona.
  const enCdmx = (iso: string) =>
    new Intl.DateTimeFormat("es-MX", {
      timeZone: ZONA_CDMX,
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  const enUtc = (iso: string) =>
    new Intl.DateTimeFormat("es-MX", {
      timeZone: "UTC",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));

  it("convierte el instante UTC a la hora de pared CDMX (no lo deja en UTC)", () => {
    expect(formatearHora("2026-06-03T22:00:00Z")).toBe(enCdmx("2026-06-03T22:00:00Z"));
    // 22:00 UTC ≠ 22:00 CDMX: se aplica el offset -06:00.
    expect(formatearHora("2026-06-03T22:00:00Z")).not.toBe(enUtc("2026-06-03T22:00:00Z"));
  });

  it("interpreta un naive como UTC (mismo resultado que con 'Z')", () => {
    expect(formatearHora("2026-06-03T22:00:00")).toBe(formatearHora("2026-06-03T22:00:00Z"));
  });
});

describe("datetimeLocalAIso ↔ isoADatetimeLocal (CDMX)", () => {
  it("interpreta el picker como hora CDMX y produce el instante UTC", () => {
    // 18:00 CDMX = 00:00 UTC del día siguiente.
    expect(datetimeLocalAIso("2026-06-03T18:00")).toBe("2026-06-04T00:00:00.000Z");
  });

  it("ida y vuelta: UTC → picker CDMX → UTC es estable", () => {
    const iso = "2026-06-04T00:00:00.000Z";
    const local = isoADatetimeLocal(iso); // "2026-06-03T18:00"
    expect(local).toBe("2026-06-03T18:00");
    expect(datetimeLocalAIso(local)).toBe(iso);
  });

  it("devuelve null para vacío", () => {
    expect(datetimeLocalAIso("")).toBeNull();
  });
});

describe("ZONA_CDMX", () => {
  it("es America/Mexico_City", () => {
    expect(ZONA_CDMX).toBe("America/Mexico_City");
  });
});
