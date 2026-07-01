import { describe, expect, it } from "vitest";

import type { EnlacePublicoCampania, PiezaCampania } from "@/types";

import { calcularRentabilidad, enlaceVigentePara, urlEnlace, visEfectivas } from "./formato";

function pieza(visualizaciones: number, visualizacionesPagadas: number): PiezaCampania {
  return {
    id: "p1",
    red: "instagram",
    marca: "UnoTV",
    titulo: "Pieza",
    publicado: "2026-06-10T00:00:00Z",
    visualizaciones,
    visualizaciones_pagadas: visualizacionesPagadas,
    interacciones: 0,
    engagement_pct: 0,
    url: "",
    formato: "reel",
    por_cross_post: false,
    es_inorganico: false,
  };
}

describe("visEfectivas", () => {
  it("no toca lo pagado fuera de modo cliente", () => {
    expect(visEfectivas(pieza(1000, 500), false)).toBe(1000);
  });

  it("funde lo pagado en modo cliente (sin rastro de pauta)", () => {
    expect(visEfectivas(pieza(1000, 500), true)).toBe(1500);
  });
});

describe("urlEnlace", () => {
  it("compone la URL pública a partir del token", () => {
    expect(urlEnlace("abc123")).toBe(`${window.location.origin}/c/abc123`);
  });
});

function enlace(over: Partial<EnlacePublicoCampania>): EnlacePublicoCampania {
  return {
    id: "e1",
    token: "tok",
    campania_id: "c1",
    rango: "mes",
    ocultar_ads: false,
    creado: "2026-06-01T00:00:00Z",
    expira: "",
    desactivado: false,
    vigente: true,
    ...over,
  };
}

describe("enlaceVigentePara", () => {
  it("encuentra el enlace vigente que coincide en periodo y modo", () => {
    const e = enlace({ token: "match" });
    expect(enlaceVigentePara([e], "mes", false)?.token).toBe("match");
  });

  it("ignora un enlace vigente de OTRO periodo", () => {
    const e = enlace({ rango: "semana" });
    expect(enlaceVigentePara([e], "mes", false)).toBeNull();
  });

  it("ignora un enlace vigente con OTRO modo (ocultar_ads)", () => {
    const e = enlace({ ocultar_ads: true });
    expect(enlaceVigentePara([e], "mes", false)).toBeNull();
  });

  it("ignora un enlace que coincide pero ya no está vigente (caducado/revocado)", () => {
    const e = enlace({ vigente: false });
    expect(enlaceVigentePara([e], "mes", false)).toBeNull();
  });

  it("sin enlaces, devuelve null", () => {
    expect(enlaceVigentePara([], "mes", false)).toBeNull();
  });
});

describe("calcularRentabilidad", () => {
  it("null si no hay precio de venta definido (0)", () => {
    expect(calcularRentabilidad({ precio_venta: 0, margen_objetivo_pct: 40 }, 0)).toBeNull();
  });

  it("deriva el tope como precio_venta * (1 - margen/100)", () => {
    const r = calcularRentabilidad({ precio_venta: 1200000, margen_objetivo_pct: 40 }, 0);
    expect(r?.tope).toBe(720000);
  });

  it("disponible = tope - gasto; sobreTope falso mientras no se pase", () => {
    const r = calcularRentabilidad({ precio_venta: 1000000, margen_objetivo_pct: 40 }, 500000);
    expect(r?.tope).toBe(600000);
    expect(r?.disponible).toBe(100000);
    expect(r?.sobreTope).toBe(false);
  });

  it("sobreTope true cuando el gasto ya pasó el tope", () => {
    const r = calcularRentabilidad({ precio_venta: 1000000, margen_objetivo_pct: 40 }, 700000);
    expect(r?.disponible).toBe(-100000);
    expect(r?.sobreTope).toBe(true);
  });

  it("margen 0 permite gastar hasta el precio de venta completo", () => {
    const r = calcularRentabilidad({ precio_venta: 100000, margen_objetivo_pct: 0 }, 0);
    expect(r?.tope).toBe(100000);
  });

  it("margen 100 no deja margen de pauta", () => {
    const r = calcularRentabilidad({ precio_venta: 100000, margen_objetivo_pct: 100 }, 0);
    expect(r?.tope).toBe(0);
  });
});
