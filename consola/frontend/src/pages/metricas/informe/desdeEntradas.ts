/**
 * Adaptador PURO del Informe: convierte los datos vivos de Métricas (las queries activas de
 * React Query, los mismos pares `[queryKey, data]` que alimentan el PDF) en las `InformeProps`
 * que pinta el deck. No conoce React, ni la red, ni jsPDF: solo transforma datos crudos en la
 * forma del contrato. Aquí se calculan los INSIGHTS deterministas (mejor día, red dominante,
 * seguidores netos, pieza estrella, mezcla de interacción, recomendaciones) — el deck no
 * inventa nada, solo pinta lo que este adaptador deriva de los datos reales.
 */
import {
  REDES_CANONICAS,
  nombreRed,
  numeroCompactoFijo,
  numeroCompleto,
  porcentaje,
  redCanonica,
  variacion,
} from "@/lib/formato";
import type {
  ConclusionInforme,
  FilaPiezaInforme,
  FilaRanking,
  InformeProps,
  KpiInforme,
  PuntoTendencia,
  SegmentoMix,
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

/**
 * Rampa de naranja por POSICIÓN en un ranking (líder más intenso, descendiendo). Un solo tono
 * = "una sola cosa ordenada", coherente con el acento único del deck (sin multicolor). Mismo
 * patrón para reparto por red y comparativa por marca.
 */
const RAMPA_NARANJA = ["#ea580c", "#f97316", "#fb923c", "#fdba74", "#fdcfa4", "#fde3cb"];
const colorRango = (i: number): string => RAMPA_NARANJA[Math.min(i, RAMPA_NARANJA.length - 1)];

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
interface PuntoTendenciaCrudo {
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
  red?: string;
  publicado?: string;
  visualizaciones?: number;
  interacciones?: number;
  engagement_pct?: number;
  url?: string;
  formato?: string;
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

/**
 * Fecha corta es-MX ("12 may") a partir de un ISO; cadena vacía si no parsea. Las fechas de las
 * series son días de calendario (YYYY-MM-DD); `new Date("2026-06-01")` las interpreta como UTC y al
 * formatear en hora local de México retrocederían un día ("31 may"). Construimos la fecha con sus
 * componentes como fecha LOCAL para que el día mostrado sea el real del dato.
 */
function fechaCorta(iso: string | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
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
  const mesAnterior = mesAnteriorDe(ctx.periodo);

  const marcaId = esTodas ? null : aSlug(ctx.marcaId ?? ctx.marca) || null;

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

  // --- Tendencia diaria: vistas E interacciones por día (small-multiple). ---
  const tendenciaCrudo = (datos.get("tendencia") ?? {}) as { puntos?: PuntoTendenciaCrudo[] };
  const tendencia: PuntoTendencia[] = (tendenciaCrudo.puntos ?? []).map((p) => ({
    fecha: fechaCorta(p.fecha),
    Vistas: num(p.visualizaciones),
    Interacciones: num(p.interacciones),
  }));
  const sumaVistasDiarias = tendencia.reduce((s, p) => s + p.Vistas, 0);
  // Media y % del pico anclados al total CANÓNICO del mes (la KPI), no a la suma de la serie
  // diaria: el titular dice "% de las vistas DEL MES", que es el total del periodo; así la lámina
  // reconcilia con la de cifras aunque la serie diaria no sume exactamente el total.
  const totalVistasMes = num(total.visualizaciones) || sumaVistasDiarias;
  const mediaVistas = tendencia.length ? totalVistasMes / tendencia.length : 0;
  const sumaInterDiarias = tendencia.reduce((s, p) => s + p.Interacciones, 0);
  const totalInterMes = num(total.interacciones) || sumaInterDiarias;
  const mediaInteracciones = tendencia.length ? totalInterMes / tendencia.length : 0;
  let picoVistas: InformeProps["picoVistas"] = null;
  if (tendencia.length && totalVistasMes > 0) {
    const mejor = tendencia.reduce((a, b) => (b.Vistas > a.Vistas ? b : a));
    picoVistas = {
      fecha: mejor.fecha,
      pct: Math.round((mejor.Vistas / totalVistasMes) * 100),
      valor: mejor.Vistas,
    };
  }

  // --- KPIs: 5 tiles del reporte (delta solo si hay comparativa). ---
  const diasPeriodo = tendencia.length || 30;
  const piezas = num(total.piezas);
  const kpis: KpiInforme[] = [
    {
      etiqueta: "Piezas",
      valor: numeroCompleto(piezas),
      titulo: numeroCompleto(piezas),
      delta: deltaDe("piezas"),
      secundario: piezas > 0 ? `${Math.round(piezas / diasPeriodo)} / día` : undefined,
    },
    {
      etiqueta: "Visualizaciones",
      valor: numeroCompactoFijo(num(total.visualizaciones)),
      titulo: numeroCompleto(num(total.visualizaciones)),
      delta: deltaDe("visualizaciones"),
    },
    {
      etiqueta: "Alcance",
      valor: numeroCompactoFijo(num(total.alcance)),
      titulo: numeroCompleto(num(total.alcance)),
      delta: deltaDe("alcance"),
    },
    {
      etiqueta: "Interacciones",
      valor: numeroCompactoFijo(num(total.interacciones)),
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

  // --- Seguidores: ganancia ACUMULADA desde 0 (la pendiente cuenta el neto, eje honesto). ---
  const seguidoresCrudo = (datos.get("seguidores") ?? {}) as { puntos?: PuntoSeguidores[] };
  const totales = (seguidoresCrudo.puntos ?? []).map((p) => ({ fecha: fechaCorta(p.fecha), total: num(p.total) }));
  const base = totales.length ? totales[0].total : 0;
  const seguidores = totales.map((p) => ({ fecha: p.fecha, Ganados: p.total - base }));
  const seguidoresNeto = analizarSeguidores(totales);

  // --- Reparto por red: ranking horizontal ordenado (no una barra apilada falsa). ---
  const porRedCrudo = reporte.por_red ?? [];
  const vistasPorRed = new Map<string, number>();
  for (const r of porRedCrudo) {
    const red = redCanonica(String(r.red ?? ""));
    if (red) vistasPorRed.set(red, (vistasPorRed.get(red) ?? 0) + num(r.visualizaciones));
  }
  const redesOrden = REDES_CANONICAS.filter((red) => (vistasPorRed.get(red) ?? 0) > 0).sort(
    (a, b) => (vistasPorRed.get(b) ?? 0) - (vistasPorRed.get(a) ?? 0),
  );
  const pctRed = repartirPct(redesOrden.map((r) => vistasPorRed.get(r) ?? 0));
  const porRed: FilaRanking[] = redesOrden.map((red, i) => ({
    clave: red,
    nombre: nombreRed(red),
    valor: vistasPorRed.get(red) ?? 0,
    pct: pctRed[i],
    color: colorRango(i),
  }));
  // "Concentra" solo con dominio real (≥45 %); si no, "lidera" (no sobredimensiona el reparto).
  const redInsight =
    porRed.length === 0
      ? ""
      : porRed.length === 1
        ? `Todo el tráfico viene de ${porRed[0].nombre}`
        : porRed[0].pct >= 45
          ? `${porRed[0].nombre} concentra el ${porRed[0].pct}\u202f% de las visualizaciones`
          : `${porRed[0].nombre} lidera el reparto con el ${porRed[0].pct}\u202f% de las visualizaciones`;

  // --- Mezcla de interacciones: AGREGADA a una barra 100 % (no una por celda). ---
  const desgloseMix = analizarMezcla(datos.get("desglose"));

  // --- Engagement por red: interacción por vista (desglose por red ÷ vistas por red). ---
  // Dónde ENGANCHA la audiencia, no solo dónde se ve. Lectura orientativa entre redes
  // (las "vistas" no son idénticas plataforma a plataforma), pero el orden sí informa.
  const celdasEng = ((datos.get("desglose") ?? {}) as { celdas?: CeldaDesglose[] }).celdas ?? [];
  const interacPorRed = new Map<string, number>();
  for (const c of celdasEng) {
    const red = redCanonica(String(c.red ?? ""));
    if (!red) continue;
    const inter = num(c.likes) + num(c.comentarios) + num(c.compartidos) + num(c.guardados);
    interacPorRed.set(red, (interacPorRed.get(red) ?? 0) + inter);
  }
  const engOrden = redesOrden
    .map((red) => ({
      red,
      rate: Math.round(((interacPorRed.get(red) ?? 0) / (vistasPorRed.get(red) ?? 1)) * 1000) / 10,
    }))
    .filter((r) => r.rate > 0)
    .sort((a, b) => b.rate - a.rate);
  const engPorRed = engOrden.map((r, i) => ({
    clave: r.red,
    nombre: nombreRed(r.red),
    rate: r.rate,
    color: colorRango(i),
  }));
  const engInsight = engPorRed.length
    ? `${engPorRed[0].nombre} lidera la interacción por vista: ${engPorRed[0].rate} %`
    : "";

  // --- Top piezas (las 8 mejores). `plataforma` ya es id de red; lo canonizamos. ---
  const piezasCrudo = (datos.get("piezas") ?? {}) as { top?: PiezaCruda[] };
  const topPiezas: FilaPiezaInforme[] = (piezasCrudo.top ?? []).slice(0, 8).map((p) => ({
    titulo: String(p.titulo ?? ""),
    red: redCanonica(String(p.red ?? p.plataforma ?? "")),
    publicado: String(p.publicado ?? ""),
    vistas: num(p.visualizaciones),
    interacciones: num(p.interacciones),
    engagement: num(p.engagement_pct),
    url: typeof p.url === "string" && p.url ? p.url : undefined,
    formato: typeof p.formato === "string" && p.formato ? p.formato : undefined,
  }));
  const vistasTotal = num(total.visualizaciones);
  const pctEstrella =
    topPiezas.length && vistasTotal > 0 ? Math.round((topPiezas[0].vistas / vistasTotal) * 100) : 0;
  // Múltiplo de la pieza estrella frente a la pieza MEDIA del periodo (vistas totales / piezas):
  // convierte un "5 %" tibio en "rindió 33× la media".
  const mediaPieza = num(total.piezas) > 0 ? vistasTotal / num(total.piezas) : 0;
  const multiploEstrella =
    topPiezas.length && mediaPieza > 0 ? Math.round(topPiezas[0].vistas / mediaPieza) : 0;

  // --- Comparativa por marca (solo modo "todas"): ranking horizontal naranja. ---
  let cuentas: FilaRanking[] = [];
  if (esTodas) {
    const ordenadas = [...(reporte.cuentas ?? [])]
      .map((c) => ({ marca: String(c.marca ?? c.marca_id ?? ""), vistas: num(c.visualizaciones) }))
      .sort((a, b) => b.vistas - a.vistas);
    const pcts = repartirPct(ordenadas.map((c) => c.vistas));
    cuentas = ordenadas.map((c, i) => ({
      clave: aSlug(c.marca) || c.marca,
      nombre: c.marca,
      valor: c.vistas,
      pct: pcts[i],
      color: colorRango(i),
    }));
  }

  // --- Titular del mes, conclusiones y recomendaciones (deterministas). ---
  const titularMes = construirTitular(compPorMetrica, hayComparar, total, mesAnterior);
  const conclusiones = construirConclusiones(total, seguidoresNeto, desgloseMix);
  const recomendaciones = construirRecomendaciones(
    compPorMetrica,
    porRed,
    topPiezas,
    pctEstrella,
    multiploEstrella,
    desgloseMix,
    mesAnterior,
  );

  return {
    marcaId,
    marcaLabel: ctx.marca,
    esTodas,
    periodo: ctx.periodo,
    mesAnterior,
    titularMes,
    kpis,
    tendencia,
    picoVistas,
    mediaVistas,
    mediaInteracciones,
    porRed,
    redInsight,
    engPorRed,
    engInsight,
    seguidores,
    seguidoresNeto,
    desgloseMix,
    topPiezas,
    pctEstrella,
    multiploEstrella,
    cuentas,
    conclusiones,
    recomendaciones,
  };
}

/** Neto ganado en el periodo (cifra, %, ritmo) a partir de la serie de totales acumulados. */
function analizarSeguidores(totales: Array<{ fecha: string; total: number }>): InformeProps["seguidoresNeto"] {
  if (totales.length < 2) return null;
  const primero = totales[0].total;
  const ultimo = totales[totales.length - 1].total;
  const neto = ultimo - primero;
  const r = Math.round((neto / Math.max(1, primero)) * 1000) / 10;
  const signo: "sube" | "baja" | "igual" = neto > 0 ? "sube" : neto < 0 ? "baja" : "igual";
  const signoTxt = neto > 0 ? "+" : neto < 0 ? "−" : "";
  // Ritmo por día sobre el nº de días del periodo (mismo divisor que media de vistas/piezas).
  const porDiaVal = Math.round(neto / totales.length);
  return {
    texto: `${signoTxt}${numeroCompactoFijo(Math.abs(neto))}`,
    // Espacio normal entre cifra y "%" (como el resto de deltas v\u00eda variacion); la l\u00e1mina de
    // seguidores lo pasa por finos() para el espacio fino. Un decimal fijo: nunca "+3 %" junto a "+5.1 %".
    pct: `${signoTxt}${Math.abs(r).toLocaleString("es-MX", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`,
    porDia: `${signoTxt}${numeroCompactoFijo(Math.abs(porDiaVal))} / día`,
    signo,
  };
}

/** Mezcla de interacciones agregada (suma de todas las celdas) a 4 segmentos con %. */
function analizarMezcla(crudo: unknown): InformeProps["desgloseMix"] {
  const celdas = ((crudo ?? {}) as { celdas?: CeldaDesglose[] }).celdas ?? [];
  let likes = 0;
  let comentarios = 0;
  let compartidos = 0;
  let guardados = 0;
  for (const c of celdas) {
    likes += num(c.likes);
    comentarios += num(c.comentarios);
    compartidos += num(c.compartidos);
    guardados += num(c.guardados);
  }
  const valores = [likes, comentarios, compartidos, guardados];
  const total = valores.reduce((s, v) => s + v, 0);
  const pcts = repartirPct(valores);
  // Color con SIGNIFICADO y una sola lógica: el TONO marca el valor (gris = bajo valor —
  // me gusta, comentarios; naranja = alto valor — compartir, guardar), y la INTENSIDAD sigue
  // a la magnitud dentro de cada grupo (el segmento mayor, más intenso). El naranja de la
  // barra ES el dato del titular "X % se comparte o se guarda". Me gusta (74 %) > Comentarios;
  // Compartidos (12 %) > Guardados.
  const defs: Array<{ label: string; color: string }> = [
    { label: "Me gusta", color: "#a3a3a3" },
    { label: "Comentarios", color: "#d4d4d4" },
    { label: "Compartidos", color: "#ea580c" },
    { label: "Guardados", color: "#fdba74" },
  ];
  const segmentos: SegmentoMix[] = defs.map((d, i) => ({
    label: d.label,
    valor: valores[i],
    pct: pcts[i],
    color: d.color,
  }));
  const altoValorPct = pcts[2] + pcts[3];
  return { segmentos, total, altoValorPct };
}

/** Titular del mes: una frase determinista según la dirección de vistas e interacciones. */
function construirTitular(
  comp: Map<string, MetricaComparada>,
  hayComparar: boolean,
  total: ReporteTotal,
  mesAnterior: string,
): string {
  if (!hayComparar) {
    return `${numeroCompactoFijo(num(total.visualizaciones))} visualizaciones y ${porcentaje(
      num(total.engagement_pct),
    )} de engagement en el periodo`;
  }
  const vis = Math.round(num(comp.get("visualizaciones")?.variacion_pct) * 10) / 10;
  const inter = Math.round(num(comp.get("interacciones")?.variacion_pct) * 10) / 10;
  const subeVis = vis > 0;
  const subeInter = inter > 0;
  if (subeVis && subeInter) return `Un mes al alza: más audiencia y más conexión que ${mesAnterior}`;
  if (subeVis && !subeInter)
    return `Más alcance, menos conexión: llegó a más gente que ${mesAnterior}, pero enganchó menos`;
  if (!subeVis && subeInter)
    return `Menos volumen pero mejor conexión: cayeron las vistas y subió la interacción`;
  return `Mes a la baja: menos vistas y menos interacción que ${mesAnterior}`;
}

/**
 * Conclusiones del cierre: 3 cifras DERIVADAS (no repiten los KPIs del resumen). Seguidores
 * netos, eficiencia por pieza e interacción de alto valor: lo que el mes dejó para decidir.
 */
function construirConclusiones(
  total: ReporteTotal,
  seguidoresNeto: InformeProps["seguidoresNeto"],
  mix: InformeProps["desgloseMix"],
): ConclusionInforme[] {
  const out: ConclusionInforme[] = [];

  if (seguidoresNeto) {
    out.push({
      valor: seguidoresNeto.texto,
      label: "Seguidores netos",
      signo: seguidoresNeto.signo === "igual" ? "neutral" : seguidoresNeto.signo,
      nota: `${seguidoresNeto.porDia} de media; la base ${
        seguidoresNeto.signo === "baja" ? "se redujo" : "creció"
      }.`,
    });
  }

  const piezas = num(total.piezas);
  const vistas = num(total.visualizaciones);
  if (piezas > 0 && vistas > 0) {
    out.push({
      valor: numeroCompactoFijo(Math.round(vistas / piezas)),
      label: "Vistas por pieza",
      signo: "neutral",
      nota: `${numeroCompleto(piezas)} piezas publicadas en el periodo.`,
    });
  }

  if (mix.total > 0) {
    out.push({
      valor: `${mix.altoValorPct}\u202f%`,
      label: "Interacción de alto valor",
      signo: mix.altoValorPct >= 20 ? "sube" : "neutral",
      nota: "Lo que la gente comparte y guarda.",
    });
  }

  return out.slice(0, 3);
}

/**
 * Recomendaciones accionables (2-3) derivadas de la evidencia del propio deck: replica la
 * pieza estrella, recupera lo que cayó, explota la red infrautilizada o sube la interacción
 * de alto valor. Nunca inventa: cada frase nace de un dato calculado arriba.
 */
function construirRecomendaciones(
  comp: Map<string, MetricaComparada>,
  porRed: FilaRanking[],
  topPiezas: FilaPiezaInforme[],
  pctEstrella: number,
  multiploEstrella: number,
  mix: InformeProps["desgloseMix"],
  mesAnterior: string,
): string[] {
  const etiquetas: Record<string, string> = {
    visualizaciones: "las visualizaciones",
    alcance: "el alcance",
    interacciones: "las interacciones",
    engagement_pct: "el engagement",
  };
  const recs: string[] = [];

  // 1 · Pieza estrella → replicar el ángulo que funcionó (con el múltiplo, que impresiona más).
  if (topPiezas.length && pctEstrella > 0) {
    const t = topPiezas[0].titulo;
    const corto = t.length > 60 ? `${t.slice(0, 57)}…` : t;
    const rendimiento =
      multiploEstrella > 1
        ? `rindió ${multiploEstrella}× la pieza media`
        : `valió el ${pctEstrella}\u202f% de las vistas del mes`;
    recs.push(`Replica el ángulo de «${corto}»: ${rendimiento}.`);
  }

  // 2 · La métrica que más cayó → recuperarla (acción correctiva).
  let peor: { metrica: string; v: number } | null = null;
  for (const [metrica, c] of comp) {
    const v = Math.round(num(c.variacion_pct) * 10) / 10;
    if (v < 0 && etiquetas[metrica] && (peor === null || v < peor.v)) peor = { metrica, v };
  }
  if (peor) {
    recs.push(
      `Recupera ${etiquetas[peor.metrica]}: cayó ${variacion(peor.v)} frente a ${mesAnterior}.`,
    );
  }

  // 3 · Red infrautilizada (si la menor pesa poco) o doblar la apuesta en la dominante.
  if (porRed.length >= 2) {
    const menor = porRed[porRed.length - 1];
    if (menor.pct <= 12) {
      recs.push(
        `Prueba más en ${menor.nombre}: aporta solo el ${menor.pct}\u202f% de las vistas, es margen sin explotar.`,
      );
    } else {
      recs.push(`Dobla la apuesta en ${porRed[0].nombre}, donde se concentra tu audiencia.`);
    }
  }

  // 4 · Interacción de alto valor (relleno si faltan recomendaciones de las anteriores).
  if (recs.length < 3 && mix.total > 0) {
    recs.push(
      mix.altoValorPct >= 20
        ? `Apuesta por contenido que se comparte y se guarda: ya es el ${mix.altoValorPct}\u202f% de las interacciones.`
        : `Pide compartir y guardar: la interacción de alto valor es solo el ${mix.altoValorPct}\u202f%.`,
    );
  }

  return recs.slice(0, 3);
}
