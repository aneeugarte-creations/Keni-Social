/**
 * Tests para @/lib/fecha — fechas/horas ancladas a CDMX (America/Mexico_City).
 *
 * Lo importante NO es el texto localizado exacto (depende de la versión de ICU del
 * runtime) sino la SEMÁNTICA de zona: un instante UTC se muestra/convierte a la hora
 * de pared CDMX correcta, y un ISO naive se interpreta como UTC (convención backend).
 * CDMX está en UTC-06:00 (sin horario de verano desde 2023).
 */
import { describe, expect, it, vi } from "vitest";

import {
  aInstante,
  datetimeLocalAIso,
  formatearHora,
  hoyCDMX,
  isoADatetimeLocal,
  posicionTemporal,
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

describe("hoyCDMX", () => {
  it("devuelve el día CDMX, no el día UTC (a las 23:30Z en CDMX aún es el día anterior)", () => {
    vi.useFakeTimers();
    try {
      // 2026-06-04 23:30 UTC = 2026-06-04 17:30 CDMX (UTC-6): mismo día.
      vi.setSystemTime(new Date("2026-06-04T23:30:00Z"));
      expect(hoyCDMX()).toBe("2026-06-04");
      // 2026-06-05 03:30 UTC = 2026-06-04 21:30 CDMX: el día UTC ya es el 5, CDMX sigue en el 4.
      vi.setSystemTime(new Date("2026-06-05T03:30:00Z"));
      expect(hoyCDMX()).toBe("2026-06-04");
      expect(new Date().toISOString().slice(0, 10)).toBe("2026-06-05"); // el bug que evita
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("posicionTemporal (semáforo de cobertura)", () => {
  // AHORA fijo = 2026-06-14 00:00 UTC = 2026-06-13 18:00 CDMX (UTC-6).
  function conAhora(fn: () => void) {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date("2026-06-14T00:00:00Z"));
      fn();
    } finally {
      vi.useRealTimers();
    }
  }

  it("día futuro → «antes»; día pasado → «despues»", () => {
    conAhora(() => {
      expect(posicionTemporal("2026-06-14")).toBe("antes");
      expect(posicionTemporal("2026-06-12")).toBe("despues");
    });
  });

  it("hoy: antes de la hora → «antes»; dentro de la ventana → «durante»; pasada → «despues»", () => {
    conAhora(() => {
      // Son las 18:00 CDMX.
      expect(posicionTemporal("2026-06-13", "19:00")).toBe("antes"); // aún no es la hora
      expect(posicionTemporal("2026-06-13", "17:00")).toBe("durante"); // 17:00–20:00 (ventana 180')
      expect(posicionTemporal("2026-06-13", "14:00")).toBe("despues"); // 14:00+180' = 17:00 < 18:00
    });
  });

  it("hoy sin hora concreta → «durante»; sin fecha → null", () => {
    conAhora(() => {
      expect(posicionTemporal("2026-06-13")).toBe("durante");
      expect(posicionTemporal("")).toBeNull();
      expect(posicionTemporal(null)).toBeNull();
    });
  });
});
