import { beforeAll, describe, expect, it, vi } from "vitest";

import { descargarPresentacion, etiquetaPeriodo } from "./exportarPdf";

beforeAll(() => {
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
  // jsPDF.save() crea un <a> y hace click: en jsdom es no-op, lo neutralizamos por si acaso.
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

const CTX = { marca: "Claro Sports", red: "Instagram", formato: "Todos los formatos", periodo: "junio 2026", generadoEn: "2026-06-22T10:00:00Z" };

describe("etiquetaPeriodo", () => {
  it("traduce presets y tokens de mes/rango", () => {
    expect(etiquetaPeriodo("semana", [{ id: "semana", etiqueta: "Última semana" }])).toBe("Última semana");
    expect(etiquetaPeriodo("mes:2026-06", [])).toBe("junio 2026");
  });
});

describe("descargarPresentacion", () => {
  it("genera el deck con todos los tipos de slide sin reventar (KPIs, barras, líneas, tablas)", async () => {
    const entradas: Array<[readonly unknown[], unknown]> = [
      [
        ["metricas", "reporte", "mes", "claro_sports"],
        {
          total: { visualizaciones: 1000, alcance: 500, interacciones: 50, engagement_pct: 5, piezas: 10 },
          por_red: [
            { red: "instagram", visualizaciones: 600 },
            { red: "youtube", visualizaciones: 400 },
          ],
          cuentas: [{ marca: "UnoTV", visualizaciones: 1000 }],
        },
      ],
      [
        ["metricas", "tendencia", "mes", "claro_sports"],
        {
          puntos: [
            { fecha: "2026-06-01", visualizaciones: 10, interacciones: 1 },
            { fecha: "2026-06-02", visualizaciones: 20, interacciones: 3 },
          ],
        },
      ],
      [
        ["metricas", "seguidores", "mes", "claro_sports"],
        { puntos: [{ fecha: "2026-06-01", total: 100 }, { fecha: "2026-06-02", total: 120 }] },
      ],
      [
        ["metricas", "piezas", "mes", "claro_sports"],
        {
          top: [{ titulo: "Gol", plataforma: "instagram", publicado: "2026-06-01", visualizaciones: 900, interacciones: 40, engagement_pct: 4.4 }],
          peores: [{ titulo: "Resumen", plataforma: "instagram", publicado: "2026-06-02", visualizaciones: 4, interacciones: 0, engagement_pct: 0 }],
        },
      ],
      [["metricas", "desglose", "mes", "claro_sports"], { celdas: [{ marca: "UnoTV", red: "instagram", likes: 10, comentarios: 2 }] }],
    ];

    await expect(descargarPresentacion(entradas, CTX, "claro_sports-instagram-mes")).resolves.toBeUndefined();
  });

  it("lanza cuando no hay datos", async () => {
    await expect(descargarPresentacion([], CTX, "x")).rejects.toThrow();
  });
});
