/**
 * Adaptador PURO del Informe: convierte los datos vivos de Métricas (las queries activas de
 * React Query, los mismos pares `[queryKey, data]` que alimentan el PDF) en las `InformeProps`
 * que pinta el deck. No conoce React, ni la red, ni jsPDF: solo transforma datos crudos en la
 * forma del contrato. Es el otro lado del seam descrito en `tipos.ts`.
 */
import {
  REDES_CANONICAS,
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
  redCanonica,
  variacion,
} from "@/lib/formato";
import { colorDe } from "@/pages/metricas/coloresRed";
import type {
  ConclusionInforme,
  CuentaInforme,
  FilaPiezaInforme,
  InformeProps,
  KpiInforme,
  SerieApilada,
} from "./tipos";

/** Contexto legible que acompaña a las entradas (espejo de `ContextoDeck` + el id de métricas). */
export interface ContextoInforme {
  marca: string;
  red: string;
  formato: string;
  periodo: string;
  generadoEn?: string;
  /** Id de métricas de la marca (`claro_sports`, …); ausente cuando son todas. */
  marcaId?: string;
}

const ETIQUETA_TODAS = "Todas las marcas";

const MESES_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

// Formas crudas por dominio (narrowing local; el backend ya las documenta en types.gen.ts).

interface ReporteTotal {
  visualizaciones?: number;
  alcance?: number;
  interacciones?: number;
  engagement_pct?: number;
  piezas?: number;
}
interface ReportePorRed {
  red?: string;
  visualizaciones?: number;
}
interface ReporteCuenta {
  marca?: string;
  marca_id?: string;
  visualizaciones?: number;
}
interface ReporteCrudo {
  total?: ReporteTotal;
  por_red?: ReportePorRed[];
  cuentas?: ReporteCuenta[];
}
interface PuntoTendencia {
  fecha?: string;
  visualizaciones?: number;
  interacciones?: number;
}
interface PuntoSeguidores {
  fecha?: string;
  total?: number;
}
interface PiezaCruda {
  titulo?: string;
  plataforma?: string;
  publicado?: string;
  visualizaciones?: number;
  interacciones?: number;
  engagement_pct?: number;
}
interface CeldaDesglose {
  marca?: string;
  red?: string;
  likes?: number;
  comentarios?: number;
  compartidos?: number;
  guardados?: number;
}
interface MetricaComparada {
  metrica?: string;
  variacion_pct?: number;
  diferencia?: number;
}

/** Índice dominio → dato (primer dato no nulo por dominio), espejo del `porDominio` del PDF. */
function porDominio(entradas: Array<[readonly unknown[], unknown]>): Map<string, unknown> {
  const m = new Map<string, unknown>();
  for (const [key, dato] of entradas) {
    const dom = String(key[1] ?? "");
    if (dato != null && !m.has(dom)) m.set(dom, dato);
  }
  return m;
}

const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** Slug por guiones (minúsculas, sin acentos, separadores → `-`). */
function aSlug(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Fecha corta es-MX ("12 may") a partir de un ISO; cadena vacía si no parsea. */
function fechaCorta(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}

/** Etiqueta del mes anterior si el periodo es "mes AAAA"; si no, una frase genérica. */
function mesAnteriorDe(periodo: string): string {
  const m = /^([a-záéíóú]+)\s+(\d{4})$/i.exec(periodo.trim());
  if (m) {
    const idx = MESES_ES.indexOf(m[1].toLowerCase());
    if (idx >= 0) {
      const anio = Number(m[2]);
      const prevIdx = (idx + 11) % 12;
      // Solo añadimos el año cuando el mes anterior cae en OTRO año (enero → diciembre);
      // si no, "mayo" a secas: el año ya está en la cabecera y el pie del informe.
      return idx === 0 ? `${MESES_ES[prevIdx]} ${anio - 1}` : MESES_ES[prevIdx];
    }
  }
  return "el periodo anterior";
}

/** Variación relativa con signo de dirección (texto + signo del contrato). */
function deltaRelativo(variacion_pct: number): { texto: string; signo: "sube" | "baja" | "igual" } {
  const r = Math.round(variacion_pct * 10) / 10;
  return {
    texto: variacion(variacion_pct),
    signo: r > 0 ? "sube" : r < 0 ? "baja" : "igual",
  };
}

/** Diferencia en puntos (para engagement) con signo de dirección. */
function deltaPuntos(diferencia: number): { texto: string; signo: "sube" | "baja" | "igual" } {
  const r = Math.round(diferencia * 10) / 10;
  const abs = Math.abs(r).toLocaleString("es-MX", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const signo = r > 0 ? "+" : r < 0 ? "−" : "";
  return {
    texto: `${signo}${abs} pts`,
    signo: r > 0 ? "sube" : r < 0 ? "baja" : "igual",
  };
}

/** Reparte 100 % por mayor-resto sobre una lista de valores (los pct suman exactamente 100). */
function repartirPct(valores: number[]): number[] {
  const total = valores.reduce((s, v) => s + v, 0);
  if (total <= 0) return valores.map(() => 0);
  const exactos = valores.map((v) => (v / total) * 100);
  const suelo = exactos.map((e) => Math.floor(e));
  let resto = 100 - suelo.reduce((s, v) => s + v, 0);
  const orden = exactos
    .map((e, i) => ({ i, frac: e - Math.floor(e) }))
    .sort((a, b) => b.frac - a.frac);
  const out = [...suelo];
  for (const { i } of orden) {
    if (resto <= 0) break;
    out[i] += 1;
    resto -= 1;
  }
  return out;
}

export function desdeEntradas(
  entradas: Array<[readonly unknown[], unknown]>,
  ctx: ContextoInforme,
): InformeProps {
  const datos = porDominio(entradas);
  const esTodas = ctx.marca === ETIQUETA_TODAS;

  const marcaId = esTodas
    ? null
    : aSlug(ctx.marcaId ?? ctx.marca) || null;

  const reporte = (datos.get("reporte") ?? {}) as ReporteCrudo;
  const total = reporte.total ?? {};

  // Comparativa por métrica (variación vs periodo anterior), indexada por nombre interno.
  const comparar = datos.get("comparar") as { total?: { metricas?: MetricaComparada[] } } | undefined;
  const compPorMetrica = new Map<string, MetricaComparada>();
  for (const m of comparar?.total?.metricas ?? []) {
    if (m.metrica) compPorMetrica.set(m.metrica, m);
  }
  const hayComparar = compPorMetrica.size > 0;

  const deltaDe = (metrica: string): KpiInforme["delta"] => {
    const c = compPorMetrica.get(metrica);
    if (!c) return undefined;
    if (metrica === "engagement_pct") return deltaPuntos(num(c.diferencia));
    return deltaRelativo(num(c.variacion_pct));
  };

  // --- KPIs: 5 tiles del reporte (delta solo si hay comparativa). ---
  const kpis: KpiInforme[] = [
    {
      etiqueta: "Piezas",
      valor: numeroCompleto(num(total.piezas)),
      titulo: numeroCompleto(num(total.piezas)),
      delta: deltaDe("piezas"),
    },
    {
      etiqueta: "Visualizaciones",
      valor: numeroCompacto(num(total.visualizaciones)),
      titulo: numeroCompleto(num(total.visualizaciones)),
      delta: deltaDe("visualizaciones"),
    },
    {
      etiqueta: "Alcance",
      valor: numeroCompacto(num(total.alcance)),
      titulo: numeroCompleto(num(total.alcance)),
      delta: deltaDe("alcance"),
    },
    {
      etiqueta: "Interacciones",
      valor: numeroCompacto(num(total.interacciones)),
      titulo: numeroCompleto(num(total.interacciones)),
      delta: deltaDe("interacciones"),
    },
    {
      etiqueta: "Engagement",
      valor: porcentaje(num(total.engagement_pct)),
      titulo: porcentaje(num(total.engagement_pct)),
      delta: deltaDe("engagement_pct"),
    },
  ];

  // --- Tendencia diaria (vistas por punto). ---
  const tendenciaCrudo = (datos.get("tendencia") ?? {}) as { puntos?: PuntoTendencia[] };
  const tendencia = (tendenciaCrudo.puntos ?? []).map((p) => ({
    fecha: fechaCorta(p.fecha),
    Vistas: num(p.visualizaciones),
  }));

  // --- Seguidores (total acumulado por punto). ---
  const seguidoresCrudo = (datos.get("seguidores") ?? {}) as { puntos?: PuntoSeguidores[] };
  const seguidores = (seguidoresCrudo.puntos ?? []).map((p) => ({
    fecha: fechaCorta(p.fecha),
    Total: num(p.total),
  }));

  // --- Por red: solo hay totales por red, así que UNA barra "Periodo" apilada por red.
  // Es lo más honesto sin datos temporales: no inventa una evolución que el backend no da.
  const porRedCrudo = reporte.por_red ?? [];
  const vistasPorRed = new Map<string, number>();
  for (const r of porRedCrudo) {
    const red = redCanonica(String(r.red ?? ""));
    if (red) vistasPorRed.set(red, (vistasPorRed.get(red) ?? 0) + num(r.visualizaciones));
  }
  const redesConDato = REDES_CANONICAS.filter((red) => (vistasPorRed.get(red) ?? 0) > 0);
  const filaPorRed: Record<string, string | number> = { semana: "Periodo" };
  for (const red of redesConDato) filaPorRed[nombreRed(red)] = vistasPorRed.get(red) ?? 0;
  const porRed: SerieApilada = {
    data: redesConDato.length ? [filaPorRed] : [],
    categorias: redesConDato.map((red) => nombreRed(red)),
    colores: redesConDato.map((red) => colorDe(red)),
  };

  // --- Desglose de interacciones: una barra por celda marca×red, normalizada al 100 %
  // (modo proporción de DesgloseInteracciones: los "me gusta" eclipsan al resto en absoluto).
  const desgloseCrudo = (datos.get("desglose") ?? {}) as { celdas?: CeldaDesglose[] };
  const categoriasDesglose = ["Me gusta", "Comentarios", "Compartidos", "Guardados"];
  const dataDesglose: Array<Record<string, string | number>> = (desgloseCrudo.celdas ?? []).map((c) => {
    const valores = [num(c.likes), num(c.comentarios), num(c.compartidos), num(c.guardados)];
    const totalCelda = valores.reduce((s, v) => s + v, 0);
    const grupo = `${String(c.marca ?? "")} · ${nombreRed(String(c.red ?? ""))}`;
    const fila: Record<string, string | number> = { grupo };
    categoriasDesglose.forEach((cat, i) => {
      fila[cat] = totalCelda > 0 ? (valores[i] / totalCelda) * 100 : 0;
    });
    return fila;
  });
  const desglose: SerieApilada = {
    data: dataDesglose,
    categorias: categoriasDesglose,
    colores: ["rose", "blue", "emerald", "amber"],
  };

  // --- Top piezas (las 8 mejores). `plataforma` ya es id de red; lo canonizamos. ---
  const piezasCrudo = (datos.get("piezas") ?? {}) as { top?: PiezaCruda[] };
  const topPiezas: FilaPiezaInforme[] = (piezasCrudo.top ?? []).slice(0, 8).map((p) => ({
    titulo: String(p.titulo ?? ""),
    red: redCanonica(String(p.plataforma ?? "")),
    publicado: String(p.publicado ?? ""),
    vistas: num(p.visualizaciones),
    interacciones: num(p.interacciones),
    engagement: num(p.engagement_pct),
  }));

  // --- Comparativa por marca (solo modo "todas"); pct con mayor-resto a 100. ---
  let cuentas: CuentaInforme[] = [];
  if (esTodas) {
    const ordenadas = [...(reporte.cuentas ?? [])]
      .map((c) => ({ marca: String(c.marca ?? c.marca_id ?? ""), vistas: num(c.visualizaciones) }))
      .sort((a, b) => b.vistas - a.vistas);
    const pcts = repartirPct(ordenadas.map((c) => c.vistas));
    cuentas = ordenadas.map((c, i) => ({
      marca: c.marca,
      vistas: c.vistas,
      Vistas: c.vistas,
      pct: pcts[i],
    }));
  }

  // --- Conclusiones (SIEMPRE 3): relativas si hay comparativa, absolutas si no. ---
  const conclusiones = construirConclusiones(total, compPorMetrica, hayComparar, ctx.periodo);

  // --- Foco: una frase accionable determinista (la métrica que más cayó, o la red dominante). ---
  const foco = construirFoco(compPorMetrica, vistasPorRed, redesConDato);

  return {
    marcaId,
    marcaLabel: ctx.marca,
    esTodas,
    periodo: ctx.periodo,
    mesAnterior: mesAnteriorDe(ctx.periodo),
    kpis,
    tendencia,
    porRed,
    seguidores,
    desglose,
    topPiezas,
    cuentas,
    conclusiones,
    foco,
  };
}

/** Las 3 conclusiones de cierre (visualizaciones/alcance/interacciones). */
function construirConclusiones(
  total: ReporteTotal,
  comp: Map<string, MetricaComparada>,
  hayComparar: boolean,
  periodo: string,
): ConclusionInforme[] {
  const defs: Array<{ metrica: keyof ReporteTotal; label: string; nota: string }> = [
    { metrica: "visualizaciones", label: "Visualizaciones", nota: `Vistas totales en ${periodo}.` },
    { metrica: "alcance", label: "Alcance", nota: `Cuentas alcanzadas en ${periodo}.` },
    { metrica: "interacciones", label: "Interacciones", nota: `Interacciones acumuladas en ${periodo}.` },
  ];
  return defs.map(({ metrica, label, nota }) => {
    const c = hayComparar ? comp.get(metrica) : undefined;
    if (c) {
      const v = num(c.variacion_pct);
      const r = Math.round(v * 10) / 10;
      const signo: "sube" | "baja" | "neutral" = r > 0 ? "sube" : r < 0 ? "baja" : "neutral";
      const tendencia = r > 0 ? "más que" : r < 0 ? "menos que" : "igual que";
      return {
        valor: variacion(v),
        label,
        signo,
        nota: `${tendencia} ${mesAnteriorDe(periodo)}.`,
      };
    }
    return {
      valor: numeroCompacto(num(total[metrica])),
      label,
      signo: "neutral",
      nota,
    };
  });
}

/**
 * Frase de foco determinista: prioriza la métrica que más cayó (acción correctiva); si no hay
 * comparativa o nada cayó, apunta a la red dominante (dónde concentrar). Nunca inventa métricas.
 */
function construirFoco(
  comp: Map<string, MetricaComparada>,
  vistasPorRed: Map<string, number>,
  redesConDato: readonly string[],
): string {
  const etiquetas: Record<string, string> = {
    visualizaciones: "las visualizaciones",
    alcance: "el alcance",
    interacciones: "las interacciones",
    engagement_pct: "el engagement",
  };
  let peor: { metrica: string; v: number } | null = null;
  for (const [metrica, c] of comp) {
    const v = num(c.variacion_pct);
    if (v < 0 && (peor === null || v < peor.v)) peor = { metrica, v };
  }
  if (peor && etiquetas[peor.metrica]) {
    return `Recuperar ${etiquetas[peor.metrica]}, que cayó frente al periodo anterior.`;
  }
  if (redesConDato.length) {
    const dominante = [...redesConDato].sort(
      (a, b) => (vistasPorRed.get(b) ?? 0) - (vistasPorRed.get(a) ?? 0),
    )[0];
    return `Doblar la apuesta en ${nombreRed(dominante)}, la red que más visualizaciones aporta.`;
  }
  return "Mantener la cadencia de publicación y vigilar el engagement.";
}
