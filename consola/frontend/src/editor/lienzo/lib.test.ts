import { describe, expect, it } from "vitest";

import {
  ESCALA_MAX,
  ESCALA_MIN,
  PASOS_ZOOM,
  ZOOM_MAX,
  ZOOM_MIN,
  clampMarco,
  clampZoom,
  etiquetaGrados,
  etiquetaTamano,
  franjasZonaSegura,
} from "./lib";

describe("clampZoom", () => {
  it("deja pasar un zoom dentro del rango clásico", () => {
    expect(clampZoom(1, 0.5)).toBe(1);
    expect(clampZoom(2, 0.5)).toBe(2);
  });

  it("permite alcanzar el 300% de escala efectiva aunque el fit sea pequeño", () => {
    // Una story con fit 0.3: el tope relativo clásico (4 * 0.3 = 1.2) no llega ni al 100%.
    const baseFit = 0.3;
    const z = clampZoom(ESCALA_MAX / baseFit, baseFit);
    expect(z * baseFit).toBeCloseTo(ESCALA_MAX);
    // Y un zoom desorbitado se acota exactamente a ese tope.
    expect(clampZoom(1000, baseFit) * baseFit).toBeCloseTo(ESCALA_MAX);
  });

  it("permite bajar hasta el 10% de escala efectiva cuando el fit es 1", () => {
    const z = clampZoom(0.0001, 1);
    expect(z).toBeCloseTo(ESCALA_MIN);
  });

  it("no recorta el rango relativo clásico cuando es más amplio que el absoluto", () => {
    // fit 1: el máximo clásico (ZOOM_MAX=4 => 400%) supera ESCALA_MAX (300%) y se conserva.
    expect(clampZoom(ZOOM_MAX, 1)).toBe(ZOOM_MAX);
    // fit 0.5: el mínimo clásico (0.2 => 10% efectivo) coincide con ESCALA_MIN y se conserva.
    expect(clampZoom(0.0001, 0.5)).toBeCloseTo(ZOOM_MIN);
  });
});

describe("PASOS_ZOOM", () => {
  it("está ordenado ascendente, dentro de los límites y con el 100% incluido", () => {
    const ordenado = [...PASOS_ZOOM].sort((a, b) => a - b);
    expect(PASOS_ZOOM).toEqual(ordenado);
    expect(PASOS_ZOOM[0]).toBeGreaterThanOrEqual(ESCALA_MIN);
    expect(PASOS_ZOOM[PASOS_ZOOM.length - 1]).toBeLessThanOrEqual(ESCALA_MAX);
    expect(PASOS_ZOOM).toContain(1);
  });
});

describe("etiquetaTamano", () => {
  it("redondea a píxeles enteros del documento", () => {
    expect(etiquetaTamano(123.4, 67.8)).toBe("123 × 68 px");
    expect(etiquetaTamano(1080, 1350)).toBe("1080 × 1350 px");
  });
});

describe("etiquetaGrados", () => {
  it("normaliza a [0, 360)", () => {
    expect(etiquetaGrados(0)).toBe("0°");
    expect(etiquetaGrados(45)).toBe("45°");
    expect(etiquetaGrados(-10)).toBe("350°");
    expect(etiquetaGrados(370.2)).toBe("10°");
    expect(etiquetaGrados(360)).toBe("0°");
  });
});

describe("clampMarco", () => {
  it("acota la posición para que la caja quede dentro del lienzo", () => {
    expect(clampMarco(-5, 100, 1000)).toBe(0);
    expect(clampMarco(950, 100, 1000)).toBe(900);
    expect(clampMarco(400, 100, 1000)).toBe(400);
  });

  it("con una caja mayor que el lienzo permite sobresalir por ambos lados", () => {
    // Caja de 1200 en lienzo de 1000: rango permitido [-200, 0].
    expect(clampMarco(-300, 1200, 1000)).toBe(-200);
    expect(clampMarco(50, 1200, 1000)).toBe(0);
    expect(clampMarco(-100, 1200, 1000)).toBe(-100);
  });
});

describe("franjasZonaSegura", () => {
  it("devuelve null si el formato no define ninguna zona segura (overlay solo con safe_* > 0)", () => {
    expect(franjasZonaSegura(1080, 1080, { safe_top: 0, safe_bottom: 0 })).toBeNull();
    expect(franjasZonaSegura(1080, 1080, {})).toBeNull();
    // Valores negativos o ausentes cuentan como 0 (retrocompat con formatos sin laterales).
    expect(franjasZonaSegura(1080, 1080, { safe_top: -10, safe_left: undefined })).toBeNull();
  });

  it("para una story (solo top/bottom) vela las dos franjas horizontales con su límite", () => {
    const r = franjasZonaSegura(1080, 1920, { safe_top: 220, safe_bottom: 420 });
    expect(r).not.toBeNull();
    expect(r!.velos).toEqual([
      { x: 0, y: 0, w: 1080, h: 220 },
      { x: 0, y: 1500, w: 1080, h: 420 },
    ]);
    expect(r!.limites).toEqual([
      [0, 220, 1080, 220],
      [0, 1500, 1080, 1500],
    ]);
  });

  it("con laterales, los velos NO se solapan en las esquinas (las laterales solo cubren la franja central)", () => {
    const r = franjasZonaSegura(1080, 1920, { safe_top: 220, safe_bottom: 420, safe_left: 60, safe_right: 60 });
    expect(r!.velos).toContainEqual({ x: 0, y: 220, w: 60, h: 1280 });
    expect(r!.velos).toContainEqual({ x: 1020, y: 220, w: 60, h: 1280 });
    // Área total velada == suma exacta de franjas sin solape (esquinas contadas UNA vez).
    const area = r!.velos.reduce((acc, v) => acc + v.w * v.h, 0);
    expect(area).toBe(1080 * 220 + 1080 * 420 + 2 * 60 * (1920 - 220 - 420));
  });

  it("solo lados definidos: un único velo y un único límite por lado activo", () => {
    const r = franjasZonaSegura(1600, 900, { safe_top: 0, safe_bottom: 72 });
    expect(r!.velos).toEqual([{ x: 0, y: 828, w: 1600, h: 72 }]);
    expect(r!.limites).toEqual([[0, 828, 1600, 828]]);
  });

  it("es pura: no muta el formato que recibe", () => {
    const f = { safe_top: 220, safe_bottom: 420, safe_left: 0, safe_right: 0 };
    const copia = { ...f };
    franjasZonaSegura(1080, 1920, f);
    expect(f).toEqual(copia);
  });
});
