/**
 * Tests de las utilidades de color del editor (`color.ts`):
 *  - Conversión hex <-> RGB <-> HSV: ida y vuelta EXACTA para cualquier hex (el espectro del
 *    ColorControl pasa por HSV y no debe desviar el color al soltarlo donde estaba).
 *  - `normalizaHex`: admite con/sin `#`, forma corta de 3 dígitos y descarta lo no interpretable.
 *  - Paleta de sólidos predeterminados: hex válidos, sin duplicados, de negro a naranja.
 */
import { describe, expect, it } from "vitest";

import {
  COLORES_PREDETERMINADOS,
  hexARgb,
  hsvARgb,
  normalizaHex,
  rgbAHex,
  rgbAHsv,
} from "./color";

describe("color — conversiones hex/RGB/HSV", () => {
  it("hexARgb interpreta #RRGGBB y #RRGGBBAA (ignorando el alfa); rechaza lo demás", () => {
    expect(hexARgb("#FF0000")).toEqual({ r: 255, g: 0, b: 0 });
    expect(hexARgb("#0057b7")).toEqual({ r: 0, g: 87, b: 183 });
    expect(hexARgb("#11223380")).toEqual({ r: 17, g: 34, b: 51 });
    expect(hexARgb("123456")).toBeNull(); // sin '#'
    expect(hexARgb("#FFF")).toBeNull(); // la forma corta es cosa de normalizaHex
  });

  it("la ida y vuelta hex -> HSV -> hex es exacta (el espectro no desvía el color)", () => {
    const hexes = ["#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#123456", "#FFDE59", "#5CE1E6", "#E30613"];
    for (const hex of hexes) {
      const rgb = hexARgb(hex)!;
      expect(rgbAHex(hsvARgb(rgbAHsv(rgb)))).toBe(hex);
    }
  });

  it("hsvARgb cubre los seis sextantes del tono y los extremos", () => {
    expect(rgbAHex(hsvARgb({ h: 0, s: 1, v: 1 }))).toBe("#FF0000");
    expect(rgbAHex(hsvARgb({ h: 120, s: 1, v: 1 }))).toBe("#00FF00");
    expect(rgbAHex(hsvARgb({ h: 240, s: 1, v: 1 }))).toBe("#0000FF");
    expect(rgbAHex(hsvARgb({ h: 360, s: 1, v: 1 }))).toBe("#FF0000"); // 360 == 0
    expect(rgbAHex(hsvARgb({ h: 200, s: 0, v: 1 }))).toBe("#FFFFFF"); // s=0 => gris, da igual el tono
    expect(rgbAHex(hsvARgb({ h: 200, s: 1, v: 0 }))).toBe("#000000"); // v=0 => negro
  });
});

describe("color — normalizaHex (entrada teclada)", () => {
  it("admite con/sin '#', mayúsculas/minúsculas y espacios alrededor", () => {
    expect(normalizaHex("#0057b7")).toBe("#0057B7");
    expect(normalizaHex("0057B7")).toBe("#0057B7");
    expect(normalizaHex("  #ffaa00  ")).toBe("#FFAA00");
  });

  it("expande la forma corta de 3 dígitos", () => {
    expect(normalizaHex("fff")).toBe("#FFFFFF");
    expect(normalizaHex("#f0a")).toBe("#FF00AA");
  });

  it("devuelve null para lo no interpretable", () => {
    expect(normalizaHex("")).toBeNull();
    expect(normalizaHex("12345")).toBeNull();
    expect(normalizaHex("gggggg")).toBeNull();
    expect(normalizaHex("#12345678")).toBeNull(); // el alfa no se teclea: lo pone el deslizador
  });
});

describe("color — paleta de sólidos predeterminados", () => {
  it("24 muestras: hex de 6 dígitos en mayúsculas, sin duplicados, con negro y blanco", () => {
    expect(COLORES_PREDETERMINADOS).toHaveLength(24);
    for (const c of COLORES_PREDETERMINADOS) expect(c).toMatch(/^#[0-9A-F]{6}$/);
    expect(new Set(COLORES_PREDETERMINADOS).size).toBe(COLORES_PREDETERMINADOS.length);
    expect(COLORES_PREDETERMINADOS[0]).toBe("#000000");
    expect(COLORES_PREDETERMINADOS).toContain("#FFFFFF");
  });
});
