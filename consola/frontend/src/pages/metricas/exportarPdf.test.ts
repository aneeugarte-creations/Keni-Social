import { describe, expect, it } from "vitest";

import { descargarPresentacion, etiquetaPeriodo } from "./exportarPdf";

const CTX = {
  marca: "Claro Sports",
  red: "Instagram",
  formato: "Todos los formatos",
  periodo: "junio 2026",
  generadoEn: "2026-06-22T10:00:00Z",
  marcaId: "claro_sports",
};

describe("etiquetaPeriodo", () => {
  it("traduce presets y tokens de mes/rango", () => {
    expect(etiquetaPeriodo("semana", [{ id: "semana", etiqueta: "Última semana" }])).toBe("Última semana");
    expect(etiquetaPeriodo("mes:2026-06", [])).toBe("junio 2026");
  });
});

describe("descargarPresentacion", () => {
  // El camino feliz monta React + rasteriza con html-to-image (canvas), que jsdom no soporta;
  // la transformación de datos se prueba aparte en `informe/desdeEntradas.test.ts`. Aquí solo
  // verificamos la guarda de "sin datos", que ocurre antes de tocar el DOM.
  it("lanza cuando no hay datos", async () => {
    await expect(descargarPresentacion([], CTX, "x")).rejects.toThrow();
  });
});
