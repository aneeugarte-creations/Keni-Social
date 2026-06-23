/**
 * Tests para @/lib/fecha — fechas/horas ancladas a CDMX (America/Mexico_City).
 *
 * Lo importante NO es el texto localizado exacto (depende de la versión de ICU del
 * runtime) sino la SEMÁNTICA de zona: un instante UTC se muestra/convierte a la hora
 * de pared CDMX correcta, y un ISO naive se interpreta como UTC (convención backend).
 * CDMX está en UTC-06:00 (sin horario de verano desde 2023).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  aInstante,
  datetimeLocalAIso,
  establecerZonaDisplay,
  formatearFecha,
  formatearFechaHora,
  formatearHora,
  formatearHoraOperativa,
  hoyCDMX,
  isoADatetimeLocal,
  minutosHastaEvento,
  posicionTemporal,
  tiempoRelativoCorto,
  ZONA_CDMX,
  zonaDisplay,
  zonaDisplayDifiereDeOperativa,
} from "./fecha";

describe("horas OPERATIVAS (CDMX fija, no siguen la zona de display)", () => {
  afterEach(() => establecerZonaDisplay(ZONA_CDMX));

  it("se quedan en CDMX aunque la zona de display sea otra", () => {
    const enCdmx = formatearHoraOperativa("2026-06-03T22:00:00Z"); // hora de pared CDMX + "CDMX"
    expect(enCdmx).toMatch(/ CDMX$/);
    establecerZonaDisplay("Europe/Madrid");
    // La hora de DISPLAY pasa a Madrid (offset GMT)...
    expect(formatearHora("2026-06-03T22:00:00Z")).toContain("GMT");
    // ...pero la OPERATIVA es la MISMA que en CDMX (no se mueve con el display).
    expect(formatearHoraOperativa("2026-06-03T22:00:00Z")).toBe(enCdmx);
  });

  it("zonaDisplayDifiereDeOperativa: false en CDMX, true en otra zona", () => {
    expect(zonaDisplayDifiereDeOperativa()).toBe(false);
    establecerZonaDisplay("Europe/Madrid");
    expect(zonaDisplayDifiereDeOperativa()).toBe(true);
  });
});

describe("tiempoRelativoCorto (relativo compacto, sin 'hace')", () => {
  const haceSeg = (s: number) => new Date(Date.now() - s * 1000).toISOString();
  it("escala: minutos < 1 h, horas hasta 48 h, luego días", () => {
    expect(tiempoRelativoCorto(haceSeg(30))).toBe("ahora");
    expect(tiempoRelativoCorto(haceSeg(5 * 60))).toBe("5min");
    expect(tiempoRelativoCorto(haceSeg(90 * 60))).toBe("1h"); // 90 min ya se cuenta en horas
    expect(tiempoRelativoCorto(haceSeg(36 * 3600))).toBe("36h"); // sigue en horas hasta 48 h
    expect(tiempoRelativoCorto(haceSeg(3 * 86400))).toBe("3d");
  });
  it("vacío/ inválido → ''", () => {
    expect(tiempoRelativoCorto("")).toBe("");
    expect(tiempoRelativoCorto(null)).toBe("");
  });
});

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

  it("convierte el instante UTC a la hora de pared CDMX (no lo deja en UTC) y etiqueta la zona", () => {
    // La hora de pared es la de CDMX y SIEMPRE lleva la etiqueta de zona pegada ("… CDMX").
    expect(formatearHora("2026-06-03T22:00:00Z")).toBe(`${enCdmx("2026-06-03T22:00:00Z")} CDMX`);
    // 22:00 UTC ≠ 22:00 CDMX: se aplica el offset -06:00.
    expect(formatearHora("2026-06-03T22:00:00Z")).not.toBe(`${enUtc("2026-06-03T22:00:00Z")} CDMX`);
  });

  it("interpreta un naive como UTC (mismo resultado que con 'Z')", () => {
    expect(formatearHora("2026-06-03T22:00:00")).toBe(formatearHora("2026-06-03T22:00:00Z"));
  });
});

describe("zona de DISPLAY configurable + etiqueta de zona", () => {
  // El estado de zona vive en el módulo: dejamos siempre CDMX para no filtrar entre tests.
  afterEach(() => establecerZonaDisplay(ZONA_CDMX));

  it("por defecto las horas absolutas se etiquetan como CDMX", () => {
    expect(formatearHora("2026-06-03T22:00:00Z")).toMatch(/ CDMX$/);
    expect(formatearFechaHora("2026-06-03T22:00:00Z")).toMatch(/ CDMX$/);
  });

  it("la fecha SIN hora no lleva etiqueta de zona", () => {
    expect(formatearFecha("2026-06-03T22:00:00Z")).not.toMatch(/CDMX|GMT/);
  });

  it("cambiar de zona reformatea la hora de pared y la etiqueta (offset GMT si no hay abreviatura)", () => {
    const cdmx = formatearHora("2026-06-03T22:00:00Z"); // "16:00 CDMX"
    establecerZonaDisplay("Europe/Madrid");
    expect(zonaDisplay()).toBe("Europe/Madrid");
    const madrid = formatearHora("2026-06-03T22:00:00Z");
    expect(madrid).toContain("GMT"); // zona sin abreviatura conocida → offset GMT
    expect(madrid).not.toBe(cdmx); // otra hora de pared y otra etiqueta
  });

  it("una zona inválida se ignora y se conserva la actual (no rompe el formateo)", () => {
    establecerZonaDisplay("No/Existe");
    expect(zonaDisplay()).toBe(ZONA_CDMX);
    expect(formatearHora("2026-06-03T22:00:00Z")).toMatch(/ CDMX$/);
  });

  it("vacío/null vuelve a CDMX", () => {
    establecerZonaDisplay("Europe/Madrid");
    establecerZonaDisplay(null);
    expect(zonaDisplay()).toBe(ZONA_CDMX);
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
      expect(new Date().toISOString().slice(0, 10)).toBe("2026-06-05"); // el día UTC naíf sería el 5; hoyCDMX no
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

  it("partido NOCTURNO pasada la medianoche sigue «durante» (no salta a «despues» por el día)", () => {
    vi.useFakeTimers();
    try {
      // AHORA = 2026-06-14 00:30 CDMX = 06:30 UTC. El saque fue AYER (2026-06-13) a las 23:00 CDMX:
      // hace 90 min, dentro de la ventana de 180'. El bug comparaba el STRING de día (ayer < hoy) y
      // lo mandaba a «despues»/«Cubierto» a las 00:00 aunque el partido siguiera EN VIVO.
      vi.setSystemTime(new Date("2026-06-14T06:30:00Z"));
      expect(posicionTemporal("2026-06-13", "23:00")).toBe("durante");
      // Ya fuera de la ventana (saque 20:00 = hace 4.5 h) sí es «despues», cruzando la medianoche.
      expect(posicionTemporal("2026-06-13", "20:00")).toBe("despues");
      // Y un partido aún por empezar más tarde hoy sigue «antes».
      expect(posicionTemporal("2026-06-14", "21:00")).toBe("antes");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("minutosHastaEvento (cuenta atrás al pitido)", () => {
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

  it("futuro lejano → minutos grandes y positivos (fuera de la ventana PRE-LIVE)", () => {
    conAhora(() => {
      // 2026-06-14 18:00 CDMX = 2026-06-15 00:00 UTC: 24 h desde ahora.
      expect(minutosHastaEvento("2026-06-14", "18:00")).toBe(1440);
    });
  });

  it("«empieza en X»: dentro de la ventana, positivo y pequeño", () => {
    conAhora(() => {
      // Son las 18:00 CDMX; el partido es a las 19:00 / 18:30 CDMX de hoy.
      expect(minutosHastaEvento("2026-06-13", "19:00")).toBe(60);
      expect(minutosHastaEvento("2026-06-13", "18:30")).toBe(30);
    });
  });

  it("en vivo (ya arrancó) → negativo pequeño", () => {
    conAhora(() => {
      // Arrancó a las 17:30 CDMX: hace 30 min.
      expect(minutosHastaEvento("2026-06-13", "17:30")).toBe(-30);
    });
  });

  it("pasado → negativo grande", () => {
    conAhora(() => {
      expect(minutosHastaEvento("2026-06-12", "20:00")).toBeLessThan(0);
    });
  });

  it("sin hora concreta → ancla al inicio del día CDMX (00:00)", () => {
    conAhora(() => {
      // 2026-06-14 00:00 CDMX = 2026-06-14 06:00 UTC; ahora 00:00 UTC → 360 min.
      expect(minutosHastaEvento("2026-06-14")).toBe(360);
    });
  });

  it("sin fecha → null", () => {
    expect(minutosHastaEvento("")).toBeNull();
    expect(minutosHastaEvento(null)).toBeNull();
    expect(minutosHastaEvento(undefined)).toBeNull();
  });
});
