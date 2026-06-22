import { describe, expect, it } from "vitest";

import { construirCsvCompleto, type ContextoCsv } from "./exportarCsv";

const CTX: ContextoCsv = {
  marca: "Claro Sports",
  red: "Instagram",
  periodo: "junio 2026",
  generadoEn: "2026-06-22T10:00:00Z",
};

describe("construirCsvCompleto", () => {
  it("incluye la cabecera de contexto (marca, red, periodo)", () => {
    const csv = construirCsvCompleto([], CTX);
    expect(csv).toContain("# Analíticas Keni Social");
    expect(csv).toContain("Marca,Claro Sports");
    expect(csv).toContain("Red,Instagram");
    expect(csv).toContain("Periodo,junio 2026");
  });

  it("serializa el reporte: KPIs como clave/valor y las listas como tablas", () => {
    const reporte = {
      total: { visualizaciones: 1000, interacciones: 50, engagement_pct: 5 },
      cuentas: [
        { marca: "Claro Sports", visualizaciones: 1000, interacciones: 50 },
      ],
      por_red: [{ red: "instagram", visualizaciones: 1000 }],
    };
    const csv = construirCsvCompleto(
      [[["metricas", "reporte", "mes", "claro_sports"], reporte]],
      CTX,
    );
    expect(csv).toContain("# Reporte (KPIs · por marca · por red · cobertura)");
    // KPIs aplanados a clave/valor.
    expect(csv).toContain("total.visualizaciones,1000");
    // Subsección tabla para las listas.
    expect(csv).toContain("· cuentas");
    expect(csv).toContain("· por_red");
  });

  it("vuelca un listado de piezas (array de objetos) como tabla con todas las columnas", () => {
    const listado = {
      piezas: [
        { titulo: "Gol de último minuto", plataforma: "instagram", visualizaciones: 900, clics_enlace: 12 },
        { titulo: "Resumen jornada", plataforma: "instagram", visualizaciones: 400, clics_enlace: 3 },
      ],
    };
    const csv = construirCsvCompleto(
      [[["metricas", "piezas-listado", "mes", "claro_sports"], listado]],
      CTX,
    );
    expect(csv).toContain("# Listado de piezas");
    expect(csv).toContain("titulo");
    expect(csv).toContain("clics_enlace");
    expect(csv).toContain("Gol de último minuto");
    expect(csv).toContain("Resumen jornada");
  });

  it("omite la query de opciones y los datos nulos", () => {
    const csv = construirCsvCompleto(
      [
        [["metricas", "opciones"], { marcas: [], rangos: [] }],
        [["metricas", "tendencia", "mes"], null],
      ],
      CTX,
    );
    expect(csv).not.toContain("opciones");
    expect(csv).not.toContain("Tendencia");
  });

  it("escapa comas y comillas en los valores", () => {
    const csv = construirCsvCompleto(
      [[["metricas", "piezas-listado", "mes"], { piezas: [{ titulo: 'Título con, coma y "comillas"' }] }]],
      CTX,
    );
    expect(csv).toContain('"Título con, coma y ""comillas"""');
  });
});
