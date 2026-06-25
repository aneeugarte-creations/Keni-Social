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
  it("produce un InformeProps con la identidad de marca en modo una-marca", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.esTodas).toBe(false);
    expect(props.marcaId).toBe("claro-sports");
    expect(props.marcaLabel).toBe("Claro Sports");
    expect(props.periodo).toBe("junio 2026");
    expect(props.mesAnterior).toBe("mayo");
  });

  it("arma los 5 KPIs del reporte en orden, con ritmo de piezas como lectura secundaria", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.kpis).toHaveLength(5);
    expect(props.kpis.map((k) => k.etiqueta)).toEqual([
      "Piezas",
      "Visualizaciones",
      "Alcance",
      "Interacciones",
      "Engagement",
    ]);
    expect(props.kpis[0].valor).toBe("10");
    // Piezas sin comparativa → lectura secundaria de ritmo (10 piezas / 2 días de serie = 5/día).
    expect(props.kpis[0].secundario).toBe("5 / día");
    expect(props.kpis[1].valor).toBe(numeroCompactoEsperado(1000));
    expect(props.kpis[1].titulo).toBe("1,000");
    expect(props.kpis[4].valor).toBe("5.0 %");
  });

  it("CON comparar añade deltas por KPI y un titular de mes según la dirección", () => {
    const props = desdeEntradas([...entradasBase(), entradaComparar()], CTX_UNA);

    const porEtiqueta = Object.fromEntries(props.kpis.map((k) => [k.etiqueta, k.delta]));
    expect(porEtiqueta["Visualizaciones"]).toEqual({ texto: "+25.0 %", signo: "sube" });
    expect(porEtiqueta["Alcance"]).toEqual({ texto: "−16.6 %", signo: "baja" });
    expect(porEtiqueta["Engagement"]).toEqual({ texto: "+1.0 pts", signo: "sube" });
    expect(porEtiqueta["Piezas"]).toBeUndefined();

    // Vistas e interacciones suben → titular "al alza".
    expect(props.titularMes).toContain("al alza");
  });

  it("SIN comparar emite un titular factual (sin dirección inventada)", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);
    expect(props.kpis.every((k) => k.delta === undefined)).toBe(true);
    expect(props.titularMes).toContain("engagement");
  });

  it("tendencia lleva vistas E interacciones por día y calcula pico + media", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.tendencia).toEqual([
      { fecha: fechaCortaEsperada("2026-06-01"), Vistas: 10, Interacciones: 1 },
      { fecha: fechaCortaEsperada("2026-06-02"), Vistas: 20, Interacciones: 3 },
    ]);
    // Pico y media se anclan al total CANÓNICO del mes (1000), no a la suma de la serie diaria:
    // pico = 20 / 1000 = 2 %; media = 1000 / 2 días = 500.
    expect(props.picoVistas).toEqual({ fecha: fechaCortaEsperada("2026-06-02"), pct: 2, valor: 20 });
    expect(props.mediaVistas).toBe(500);
  });

  it("reparto por red = ranking ordenado desc con % que reparte a 100 y color de deck", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.porRed.map((r) => r.nombre)).toEqual(["Instagram", "YouTube"]);
    expect(props.porRed.map((r) => r.valor)).toEqual([600, 400]);
    expect(props.porRed.map((r) => r.pct)).toEqual([60, 40]);
    expect(props.porRed[0].color).toMatch(/^#/);
    expect(norm(props.redInsight)).toBe("Instagram concentra el 60 % de las visualizaciones");
  });

  it("engagement por red = interacción por vista, ranking desc (dónde engancha)", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    // Solo instagram tiene desglose (12 interac / 600 vistas = 2 %); youtube sin celda → fuera.
    expect(props.engPorRed.map((r) => r.nombre)).toEqual(["Instagram"]);
    expect(props.engPorRed[0].rate).toBe(2);
    expect(norm(props.engInsight)).toContain("Instagram lidera la interacción por vista");
  });

  it("seguidores: ganancia ACUMULADA desde 0 + neto honesto", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    // La serie del gráfico es la ganancia acumulada (0 → +20), no el nivel absoluto.
    expect(props.seguidores).toEqual([
      { fecha: fechaCortaEsperada("2026-06-01"), Ganados: 0 },
      { fecha: fechaCortaEsperada("2026-06-02"), Ganados: 20 },
    ]);
    // +20 netos sobre 100 = +20.0 % (un decimal fijo, coherente con los deltas del deck).
    expect(props.seguidoresNeto?.signo).toBe("sube");
    expect(norm(props.seguidoresNeto?.pct ?? "")).toBe("+20.0 %");
  });

  it("mezcla de interacciones AGREGADA a 4 segmentos (no una barra por celda)", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.desgloseMix.segmentos.map((s) => s.label)).toEqual([
      "Me gusta",
      "Comentarios",
      "Compartidos",
      "Guardados",
    ]);
    expect(props.desgloseMix.total).toBe(12);
    // 10 likes + 2 comentarios → 83 / 17; alto valor (compartir+guardar) = 0 %.
    expect(props.desgloseMix.segmentos.map((s) => s.pct)).toEqual([83, 17, 0, 0]);
    expect(props.desgloseMix.altoValorPct).toBe(0);
  });

  it("top piezas + pieza estrella (% del total y múltiplo vs pieza media)", () => {
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
    // 900 de 1000 vistas totales → 90 %; pieza media = 1000/10 = 100 → 900/100 = 9×.
    expect(props.pctEstrella).toBe(90);
    expect(props.multiploEstrella).toBe(9);
  });

  it("conclusiones del cierre = cifras DERIVADAS (no repiten los KPIs)", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);

    expect(props.conclusiones.map((c) => c.label)).toEqual([
      "Seguidores netos",
      "Vistas por pieza",
      "Interacción de alto valor",
    ]);
    expect(props.conclusiones[1].valor).toBe(numeroCompactoEsperado(100)); // 1000 vistas / 10 piezas
    expect(norm(props.conclusiones[2].valor)).toBe("0 %");
  });

  it("recomendaciones accionables nacen de la evidencia (pieza estrella, caída, red)", () => {
    const conComparar = desdeEntradas([...entradasBase(), entradaComparar()], CTX_UNA);

    expect(conComparar.recomendaciones.length).toBeGreaterThanOrEqual(2);
    expect(conComparar.recomendaciones.length).toBeLessThanOrEqual(3);
    expect(conComparar.recomendaciones[0]).toContain("«Gol»");
    // Alcance cayó (−16.6 %) → una recomendación apunta a recuperarlo.
    expect(conComparar.recomendaciones.some((r) => r.includes("alcance"))).toBe(true);
  });

  it("deja cuentas vacío en modo una-marca", () => {
    const props = desdeEntradas(entradasBase(), CTX_UNA);
    expect(props.cuentas).toEqual([]);
  });

  it("en modo todas, cuentas = ranking con % que suman 100, ordenado desc", () => {
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
    expect(props.cuentas.map((c) => c.nombre)).toEqual(["Claro Sports", "UnoTV"]);
    expect(props.cuentas[0].valor).toBe(700);
    expect(props.cuentas.reduce((s, c) => s + c.pct, 0)).toBe(100);
  });

  it("es determinista (misma entrada → misma salida)", () => {
    const a = desdeEntradas(entradasBase(), CTX_UNA);
    const b = desdeEntradas(entradasBase(), CTX_UNA);
    expect(a).toEqual(b);
  });

  it("no revienta con entradas vacías (insights vacíos, no nulos sueltos)", () => {
    const props = desdeEntradas([], CTX_UNA);
    expect(props.kpis).toHaveLength(5);
    expect(props.tendencia).toEqual([]);
    expect(props.picoVistas).toBeNull();
    expect(props.porRed).toEqual([]);
    expect(props.cuentas).toEqual([]);
    expect(props.seguidoresNeto).toBeNull();
    expect(props.conclusiones).toEqual([]);
    expect(props.recomendaciones).toEqual([]);
  });
});

// --- Espejos de formato es-MX (deterministas) para no acoplar el test a la coma/locale exacta. ---

function numeroCompactoEsperado(v: number): string {
  // Espejo de `numeroCompactoFijo`: < 1000 entero; a partir de ahí compacto con un decimal fijo.
  if (Math.abs(v) < 1000) return new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 }).format(v);
  return new Intl.NumberFormat("es-MX", {
    notation: "compact",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(v);
}

function fechaCortaEsperada(iso: string): string {
  // Espejo de `fechaCorta`: fecha de calendario como fecha LOCAL (no UTC) para no retroceder un día.
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}

/** Normaliza el espacio fino (U+202F) que el adaptador pone antes de "%" a un espacio normal. */
function norm(s: string): string {
  return s.replace(/\u202f/g, " ");
}
