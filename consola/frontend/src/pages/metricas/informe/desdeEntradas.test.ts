import { describe, expect, it } from "vitest";

import { desdeEntradas, type ContextoInforme } from "./desdeEntradas";

const CTX_UNA: ContextoInforme = {
  marca: "Claro Sports",
  red: "Instagram",
  formato: "Todos los formatos",
  periodo: "junio 2026",
  generadoEn: "2026-06-22T10:00:00Z",
  marcaId: "claro_sports",
};

const CTX_TODAS: ContextoInforme = {
  marca: "Todas las marcas",
  red: "Todas las redes",
  formato: "Todos los formatos",
  periodo: "junio 2026",
};

/** Entradas con las MISMAS formas que `exportarPdf.test.ts` (reporte/tendencia/seguidores/piezas/desglose). */
function entradasBase(): Array<[readonly unknown[], unknown]> {
  return [
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
        top: [
          { titulo: "Gol", plataforma: "instagram", publicado: "2026-06-01", visualizaciones: 900, interacciones: 40, engagement_pct: 4.4 },
        ],
        peores: [
          { titulo: "Resumen", plataforma: "instagram", publicado: "2026-06-02", visualizaciones: 4, interacciones: 0, engagement_pct: 0 },
        ],
      },
    ],
    [
      ["metricas", "desglose", "mes", "claro_sports"],
      { celdas: [{ marca: "UnoTV", red: "instagram", likes: 10, comentarios: 2, compartidos: 0, guardados: 0 }] },
    ],
  ];
}

/** Comparativa (variación vs periodo anterior) con las 4 métricas del reporte. */
function entradaComparar(): [readonly unknown[], unknown] {
  return [
    ["metricas", "comparar", "mes:2026-06", "mes:2026-05", "claro_sports"],
    {
      total: {
        metricas: [
          { metrica: "visualizaciones", a: 800, b: 1000, variacion_pct: 25, diferencia: 200 },
          { metrica: "alcance", a: 600, b: 500, variacion_pct: -16.6, diferencia: -100 },
          { metrica: "interacciones", a: 40, b: 50, variacion_pct: 25, diferencia: 10 },
          { metrica: "engagement_pct", a: 4, b: 5, variacion_pct: 25, diferencia: 1 },
        ],
      },
    },
  ];
}

describe("desdeEntradas", () => {
  it("produce un InformeProps completo en modo una-marca", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.esTodas).toBe(false);
    expect(props.marcaId).toBe("claro-sports");
    expect(props.marcaLabel).toBe("Claro Sports");
    expect(props.periodo).toBe("junio 2026");
    expect(props.mesAnterior).toBe("mayo");
  });

  it("arma los 5 KPIs del reporte en orden", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.kpis).toHaveLength(5);
    expect(props.kpis.map((k) => k.etiqueta)).toEqual([
      "Piezas",
      "Visualizaciones",
      "Alcance",
      "Interacciones",
      "Engagement",
    ]);
    // Piezas = número completo; visualizaciones = compacto + title completo.
    expect(props.kpis[0].valor).toBe("10");
    expect(props.kpis[1].valor).toBe(numeroCompactoEsperado(1000));
    expect(props.kpis[1].titulo).toBe("1,000");
    expect(props.kpis[4].valor).toBe("5.0 %");
  });

  it("SIN comparar no pone deltas y las conclusiones son absolutas/neutrales", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.kpis.every((k) => k.delta === undefined)).toBe(true);
    expect(props.conclusiones).toHaveLength(3);
    expect(props.conclusiones.map((c) => c.signo)).toEqual(["neutral", "neutral", "neutral"]);
    expect(props.conclusiones[0].label).toBe("Visualizaciones");
    expect(props.conclusiones[0].valor).toBe(numeroCompactoEsperado(1000));
  });

  it("CON comparar añade deltas por KPI y conclusiones relativas con signo", () => {
    const props = desdeEntradas([...entradasBase(), entradaComparar()], CTX_UNA);

    const porEtiqueta = Object.fromEntries(props.kpis.map((k) => [k.etiqueta, k.delta]));
    expect(porEtiqueta["Visualizaciones"]).toEqual({ texto: "+25.0 %", signo: "sube" });
    expect(porEtiqueta["Alcance"]).toEqual({ texto: "−16.6 %", signo: "baja" });
    // Engagement compara en puntos (diferencia), no variación relativa.
    expect(porEtiqueta["Engagement"]).toEqual({ texto: "+1.0 pts", signo: "sube" });
    // Piezas no viene en la comparativa → sin delta.
    expect(porEtiqueta["Piezas"]).toBeUndefined();

    expect(props.conclusiones).toHaveLength(3);
    expect(props.conclusiones[0]).toMatchObject({ valor: "+25.0 %", signo: "sube" });
    expect(props.conclusiones[1]).toMatchObject({ valor: "−16.6 %", signo: "baja" });
    expect(props.conclusiones[1].nota).toContain("menos que mayo");
  });

  it("mapea tendencia y seguidores a la forma del contrato", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.tendencia).toEqual([
      { fecha: fechaCortaEsperada("2026-06-01"), Vistas: 10 },
      { fecha: fechaCortaEsperada("2026-06-02"), Vistas: 20 },
    ]);
    expect(props.seguidores).toEqual([
      { fecha: fechaCortaEsperada("2026-06-01"), Total: 100 },
      { fecha: fechaCortaEsperada("2026-06-02"), Total: 120 },
    ]);
  });

  it("apila las vistas por red en UNA barra Periodo, orden canónico y color por red", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.porRed.data).toHaveLength(1);
    expect(props.porRed.data[0].semana).toBe("Periodo");
    // Instagram va antes que YouTube en REDES_CANONICAS, aunque en los datos llegue primero IG.
    expect(props.porRed.categorias).toEqual(["Instagram", "YouTube"]);
    expect(props.porRed.data[0]["Instagram"]).toBe(600);
    expect(props.porRed.data[0]["YouTube"]).toBe(400);
    expect(props.porRed.colores).toHaveLength(2);
  });

  it("normaliza el desglose a 100 % por celda con las 4 categorías", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.desglose.categorias).toEqual(["Me gusta", "Comentarios", "Compartidos", "Guardados"]);
    expect(props.desglose.colores).toEqual(["rose", "blue", "emerald", "amber"]);
    expect(props.desglose.data).toHaveLength(1);
    const celda = props.desglose.data[0];
    const suma = ["Me gusta", "Comentarios", "Compartidos", "Guardados"].reduce(
      (s, k) => s + (celda[k] as number),
      0,
    );
    expect(suma).toBeCloseTo(100, 5);
    // 10 likes de 12 → 83.3 %.
    expect(celda["Me gusta"] as number).toBeCloseTo((10 / 12) * 100, 5);
  });

  it("mapea las top piezas (red canónica, vistas, engagement)", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.topPiezas).toHaveLength(1);
    expect(props.topPiezas[0]).toEqual({
      titulo: "Gol",
      red: "instagram",
      publicado: "2026-06-01",
      vistas: 900,
      interacciones: 40,
      engagement: 4.4,
    });
  });

  it("deja cuentas vacío en modo una-marca", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);
    expect(props.cuentas).toEqual([]);
  });

  it("en modo todas llena cuentas con % que suman 100, ordenadas desc", () => {
    const entradas: Array<[readonly unknown[], unknown]> = [
      [
        ["metricas", "reporte", "mes", "todas"],
        {
          total: { visualizaciones: 1000, alcance: 500, interacciones: 50, engagement_pct: 5, piezas: 10 },
          por_red: [{ red: "instagram", visualizaciones: 1000 }],
          cuentas: [
            { marca: "UnoTV", visualizaciones: 300 },
            { marca: "Claro Sports", visualizaciones: 700 },
          ],
        },
      ],
    ];
    const props = desdeEntradas(entradas, CTX_TODAS);

    expect(props.esTodas).toBe(true);
    expect(props.marcaId).toBeNull();
    expect(props.cuentas.map((c) => c.marca)).toEqual(["Claro Sports", "UnoTV"]);
    expect(props.cuentas[0].vistas).toBe(700);
    expect(props.cuentas[0].Vistas).toBe(700);
    expect(props.cuentas.reduce((s, c) => s + c.pct, 0)).toBe(100);
  });

  it("siempre devuelve 3 conclusiones y un foco no vacío", () => {
    const sinComparar = desdeEntradas(entradasBase(), CTX_UNA);
    expect(sinComparar.conclusiones).toHaveLength(3);
    expect(sinComparar.foco.length).toBeGreaterThan(0);

    const conComparar = desdeEntradas([...entradasBase(), entradaComparar()], CTX_UNA);
    expect(conComparar.conclusiones).toHaveLength(3);
    // Alcance cayó (−16.6 %) → el foco apunta a recuperarlo.
    expect(conComparar.foco).toContain("alcance");
  });

  it("es determinista (misma entrada → misma salida)", () => {
    const a = desdeEntradas(entradasBase(), CTX_UNA);
    const b = desdeEntradas(entradasBase(), CTX_UNA);
    expect(a).toEqual(b);
  });

  it("no revienta con entradas vacías", () => {
    const props = desdeEntradas([], CTX_UNA);
    expect(props.kpis).toHaveLength(5);
    expect(props.tendencia).toEqual([]);
    expect(props.porRed.data).toEqual([]);
    expect(props.cuentas).toEqual([]);
    expect(props.conclusiones).toHaveLength(3);
  });
});

// --- Espejos de formato es-MX (deterministas) para no acoplar el test a la coma/locale exacta. ---

function numeroCompactoEsperado(v: number): string {
  return new Intl.NumberFormat("es-MX", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

function fechaCortaEsperada(iso: string): string {
  return new Date(iso).toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}
