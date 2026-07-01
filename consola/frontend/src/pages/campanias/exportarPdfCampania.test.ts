import { describe, expect, it } from "vitest";

import type { AnaliticaCampania } from "@/types";

import { descargarPdfCampania } from "./exportarPdfCampania";

function datosVacios(): AnaliticaCampania {
  return {
    campania: {
      id: "c1",
      marcas: ["uno_tv"],
      marcas_nombres: ["UnoTV"],
      nombre: "Mundial 2026",
      hashtags: ["Mundial2026"],
      etiqueta_web: "",
      precio_venta: 0,
      margen_objetivo_pct: 40,
      activa: true,
      fecha_creacion: "2026-06-01T00:00:00Z",
      fecha_actualizacion: "2026-06-01T00:00:00Z",
    },
    rango: "mes",
    periodo: { desde: "2026-05-26", hasta: "2026-06-25" },
    fuente: "metricool",
    kpis: { visualizaciones: 0, interacciones: 0, engagement_pct: 0, piezas: 0, alcance: null },
    comparativa: {
      visualizaciones: { actual: 0, anterior: 0, delta: 0, variacion_pct: null },
      interacciones: { actual: 0, anterior: 0, delta: 0, variacion_pct: null },
      engagement_pct: { actual: 0, anterior: 0, delta: 0, variacion_pct: null },
      piezas: { actual: 0, anterior: 0, delta: 0, variacion_pct: null },
    },
    tendencia: { puntos: [] },
    desglose_red: [],
    cross_posts: 0,
    inorganico: { visualizaciones: 0, gasto: 0, clics: 0, campanias: 0, moneda: "MXN" },
    piezas: [],
    generado_en: "2026-06-25T12:00:00Z",
  };
}

describe("descargarPdfCampania", () => {
  // El camino feliz monta React + rasteriza con html-to-image (canvas), que jsdom no soporta;
  // el contenido del deck se prueba en `informe/DeckCampania.test.tsx`. Aquí solo verificamos
  // la guarda de "campaña vacía en el periodo", que ocurre antes de tocar el DOM.
  it("lanza cuando no hay piezas ni tendencia en el periodo", async () => {
    await expect(
      descargarPdfCampania(datosVacios(), { periodoEtiqueta: "junio 2026", ocultarAds: false }),
    ).rejects.toThrow();
  });
});
