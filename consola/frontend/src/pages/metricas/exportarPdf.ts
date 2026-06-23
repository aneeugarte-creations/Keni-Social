/**
 * Exportación del dashboard de Métricas a un PDF "presentación" (deck 16:9), generado
 * DIRECTAMENTE con jsPDF a partir de los datos vivos (los mismos que el CSV: las queries
 * activas de React Query). No rasteriza el DOM ni usa el diálogo de impresión: dibuja
 * diapositivas diseñadas —portada, tiles de KPIs, gráficas vectoriales (barras/líneas) y
 * tablas— con la marca Keni. Resultado: descarga directa, determinista, nítida e imposible
 * que cuelgue, lista para presentar a dirección.
 */
import { numeroCompacto, nombreRed, porcentaje } from "@/lib/formato";
import { colorDe } from "./coloresRed";
import { diasDePeriodo, partesMes, partesRango } from "./rango";
import type { RangoMetrica } from "@/types";

const MESES_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** Etiqueta legible de un token de periodo (preset, `mes:` o `rango:`). */
export function etiquetaPeriodo(token: string, rangos: RangoMetrica[]): string {
  const preset = rangos.find((r) => r.id === token);
  if (preset) return preset.etiqueta;
  const mes = partesMes(token);
  if (mes) return `${MESES_ES[mes.mes - 1]} ${mes.anio}`;
  const rango = partesRango(token);
  if (rango) return `${rango.desde} – ${rango.hasta}`;
  const dias = diasDePeriodo(token);
  return dias != null ? `Últimos ${dias} días` : token;
}

export interface ContextoDeck {
  marca: string;
  red: string;
  periodo: string;
  generadoEn?: string;
}

// Paleta del deck (claro, profesional; independiente del tema de la app).
const BG = "#ffffff";
const INK = "#0f172a";
const MUTED = "#64748b";
const LINEA = "#e2e8f0";
const SUAVE = "#f1f5f9";
const ACENTO = "#7c3aed";

const W = 1280;
const H = 720;
const M = 64;

type Doc = import("jspdf").jsPDF;

function aRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}
const fill = (doc: Doc, hex: string) => doc.setFillColor(...aRgb(hex));
const text = (doc: Doc, hex: string) => doc.setTextColor(...aRgb(hex));
const draw = (doc: Doc, hex: string) => doc.setDrawColor(...aRgb(hex));

function fechaLegible(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("es-MX", {
    day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/** Abre una diapositiva nueva con cabecera (título + acento) y pie (contexto + nº). */
function abrirSlide(doc: Doc, titulo: string, ctx: ContextoDeck, n: number): number {
  if (n > 1) doc.addPage();
  fill(doc, BG);
  doc.rect(0, 0, W, H, "F");
  text(doc, INK);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(24);
  doc.text(titulo, M, M + 6);
  draw(doc, ACENTO);
  doc.setLineWidth(3);
  doc.line(M, M + 18, M + 48, M + 18);
  text(doc, MUTED);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.text(`${ctx.marca} · ${ctx.red} · ${ctx.periodo}`, M, H - 28);
  doc.text(String(n), W - M, H - 28, { align: "right" });
  return M + 56; // y de inicio del contenido
}

function portada(doc: Doc, ctx: ContextoDeck): void {
  fill(doc, INK);
  doc.rect(0, 0, W, H, "F");
  fill(doc, ACENTO);
  doc.rect(M, H / 2 - 96, 8, 192, "F");
  text(doc, "#ffffff");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(56);
  doc.text(ctx.marca, M + 36, H / 2 - 24);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(26);
  text(doc, "#cbd5e1");
  doc.text(`${ctx.red}  ·  ${ctx.periodo}`, M + 36, H / 2 + 22);
  doc.setFontSize(13);
  text(doc, "#94a3b8");
  const pie = ["Keni Social — Analíticas", fechaLegible(ctx.generadoEn)].filter(Boolean).join("   ·   ");
  doc.text(pie, M + 36, H / 2 + 64);
}

/** Fila de tiles de KPI (label arriba, número grande). */
function slideKpis(doc: Doc, total: Record<string, number>, ctx: ContextoDeck, n: number): void {
  const y0 = abrirSlide(doc, "Resumen del periodo", ctx, n);
  const tiles: Array<[string, string]> = [
    ["Visualizaciones", numeroCompacto(total.visualizaciones ?? 0)],
    ["Alcance", total.alcance ? numeroCompacto(total.alcance) : "—"],
    ["Interacciones", numeroCompacto(total.interacciones ?? 0)],
    ["Engagement", porcentaje(total.engagement_pct ?? 0)],
    ["Piezas", numeroCompacto(total.piezas ?? 0)],
  ];
  const gap = 24;
  const cols = tiles.length;
  const tw = (W - 2 * M - gap * (cols - 1)) / cols;
  const th = 150;
  const y = y0 + 40;
  tiles.forEach(([label, valor], i) => {
    const x = M + i * (tw + gap);
    fill(doc, SUAVE);
    draw(doc, LINEA);
    doc.setLineWidth(1);
    doc.roundedRect(x, y, tw, th, 12, 12, "FD");
    text(doc, MUTED);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(13);
    doc.text(label.toUpperCase(), x + 20, y + 34);
    text(doc, INK);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(40);
    doc.text(valor, x + 20, y + 96);
  });
}

/** Gráfica de barras horizontales (vistas por red/marca), con color por red si aplica. */
function slideBarras(
  doc: Doc,
  titulo: string,
  datos: Array<{ etiqueta: string; valor: number; color?: string }>,
  ctx: ContextoDeck,
  n: number,
): void {
  const y0 = abrirSlide(doc, titulo, ctx, n);
  const filas = datos.filter((d) => d.valor > 0).slice(0, 8);
  if (filas.length === 0) {
    text(doc, MUTED);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(14);
    doc.text("Sin datos en el periodo.", M, y0 + 40);
    return;
  }
  const max = Math.max(...filas.map((d) => d.valor));
  const etiquetaW = 180;
  const x0 = M + etiquetaW;
  const anchoMax = W - M - x0 - 140;
  const alto = 34;
  const sep = 22;
  let y = y0 + 30;
  filas.forEach((d) => {
    text(doc, INK);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(13);
    doc.text(d.etiqueta, M, y + alto / 2 + 4);
    const w = Math.max(2, (d.valor / max) * anchoMax);
    fill(doc, d.color ?? ACENTO);
    doc.roundedRect(x0, y, w, alto, 5, 5, "F");
    text(doc, INK);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    doc.text(numeroCompacto(d.valor), x0 + w + 10, y + alto / 2 + 4);
    y += alto + sep;
  });
}

/** Gráfica de líneas (una o varias series sobre el mismo eje X). */
function slideLineas(
  doc: Doc,
  titulo: string,
  series: Array<{ nombre: string; color: string; valores: number[] }>,
  ctx: ContextoDeck,
  n: number,
): void {
  const y0 = abrirSlide(doc, titulo, ctx, n);
  const conDatos = series.filter((s) => s.valores.some((v) => v > 0));
  const npts = Math.max(0, ...conDatos.map((s) => s.valores.length));
  if (conDatos.length === 0 || npts < 2) {
    text(doc, MUTED);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(14);
    doc.text("Sin serie suficiente en el periodo.", M, y0 + 40);
    return;
  }
  const x0 = M + 10;
  const x1 = W - M;
  const yTop = y0 + 40;
  const yBot = H - 120;
  const max = Math.max(1, ...conDatos.flatMap((s) => s.valores));
  draw(doc, LINEA);
  doc.setLineWidth(1);
  doc.line(x0, yBot, x1, yBot);
  text(doc, MUTED);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.text(numeroCompacto(max), x0, yTop - 6);
  const px = (i: number, len: number) => x0 + (i / (len - 1)) * (x1 - x0);
  const py = (v: number) => yBot - (v / max) * (yBot - yTop);
  conDatos.forEach((s) => {
    draw(doc, s.color);
    doc.setLineWidth(2.5);
    for (let i = 1; i < s.valores.length; i++) {
      doc.line(px(i - 1, s.valores.length), py(s.valores[i - 1]), px(i, s.valores.length), py(s.valores[i]));
    }
  });
  let lx = x0;
  const ly = H - 90;
  conDatos.forEach((s) => {
    fill(doc, s.color);
    doc.rect(lx, ly - 8, 12, 12, "F");
    text(doc, INK);
    doc.setFontSize(11);
    doc.text(s.nombre, lx + 18, ly + 2);
    lx += 18 + doc.getTextWidth(s.nombre) + 28;
  });
}

/** Una tabla (autoTable) en su diapositiva, a partir de filas de objetos planos. */
async function slideTabla(
  doc: Doc,
  titulo: string,
  filas: Array<Record<string, unknown>>,
  ctx: ContextoDeck,
  n: number,
  columnas?: Array<{ clave: string; etiqueta: string }>,
): Promise<void> {
  const y0 = abrirSlide(doc, titulo, ctx, n);
  if (filas.length === 0) {
    text(doc, MUTED);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(14);
    doc.text("Sin datos en el periodo.", M, y0 + 40);
    return;
  }
  const cols = columnas ?? Object.keys(filas[0]).map((k) => ({ clave: k, etiqueta: k }));
  const { default: autoTable } = await import("jspdf-autotable");
  autoTable(doc, {
    head: [cols.map((c) => c.etiqueta)],
    body: filas.map((f) => cols.map((c) => formatoCelda(f[c.clave]))),
    startY: y0 + 16,
    margin: { left: M, right: M, bottom: 64 },
    styles: { font: "helvetica", fontSize: 9, cellPadding: 5, textColor: aRgb(INK), lineColor: aRgb(LINEA), lineWidth: 0.5 },
    headStyles: { fillColor: aRgb(ACENTO), textColor: [255, 255, 255], fontStyle: "bold" },
    alternateRowStyles: { fillColor: aRgb(SUAVE) },
  });
}

function formatoCelda(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "number") return Number.isInteger(v) ? numeroCompacto(v) : String(v);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function porDominio(entradas: Array<[readonly unknown[], unknown]>): Map<string, unknown> {
  const m = new Map<string, unknown>();
  for (const [key, dato] of entradas) {
    const dom = String(key[1] ?? "");
    if (dato != null && !m.has(dom)) m.set(dom, dato);
  }
  return m;
}

/** Genera y DESCARGA el PDF presentación. Lanza si no hay datos. */
export async function descargarPresentacion(
  entradas: Array<[readonly unknown[], unknown]>,
  ctx: ContextoDeck,
  nombreArchivo: string,
): Promise<void> {
  const datos = porDominio(entradas);
  if (datos.size === 0) throw new Error("No hay datos cargados para el PDF.");

  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ orientation: "landscape", unit: "px", format: [W, H] });
  let n = 1;

  portada(doc, ctx);

  const reporte = datos.get("reporte") as
    | { total?: Record<string, number>; por_red?: any[]; cuentas?: any[] }
    | undefined;
  if (reporte?.total) slideKpis(doc, reporte.total, ctx, ++n);
  if (reporte?.por_red?.length) {
    slideBarras(
      doc,
      "Por red · visualizaciones",
      reporte.por_red.map((r) => ({
        etiqueta: nombreRed(String(r.red)),
        valor: Number(r.visualizaciones) || 0,
        color: colorDe(String(r.red)),
      })),
      ctx,
      ++n,
    );
  }
  if (reporte?.cuentas?.length) {
    slideBarras(
      doc,
      "Por marca · visualizaciones",
      reporte.cuentas.map((c) => ({
        etiqueta: String(c.marca ?? c.marca_id ?? ""),
        valor: Number(c.visualizaciones) || 0,
      })),
      ctx,
      ++n,
    );
  }

  const tendencia = datos.get("tendencia") as { puntos?: any[] } | undefined;
  if (tendencia?.puntos?.length) {
    slideLineas(
      doc,
      "Tendencia diaria",
      [
        { nombre: "Visualizaciones", color: ACENTO, valores: tendencia.puntos.map((p) => Number(p.visualizaciones) || 0) },
        { nombre: "Interacciones", color: "#0ea5e9", valores: tendencia.puntos.map((p) => Number(p.interacciones) || 0) },
      ],
      ctx,
      ++n,
    );
  }

  const seguidores = datos.get("seguidores") as { puntos?: any[] } | undefined;
  if (seguidores?.puntos?.length) {
    slideLineas(
      doc,
      "Crecimiento de seguidores",
      [{ nombre: "Seguidores", color: "#16a34a", valores: seguidores.puntos.map((p) => Number(p.total) || 0) }],
      ctx,
      ++n,
    );
  }

  const piezas = datos.get("piezas") as { top?: any[]; peores?: any[] } | undefined;
  const colsPieza = [
    { clave: "titulo", etiqueta: "Título" },
    { clave: "plataforma", etiqueta: "Red" },
    { clave: "publicado", etiqueta: "Publicado" },
    { clave: "visualizaciones", etiqueta: "Vistas" },
    { clave: "interacciones", etiqueta: "Interac." },
    { clave: "engagement_pct", etiqueta: "Eng. %" },
  ];
  if (piezas?.top?.length) await slideTabla(doc, "Top piezas", piezas.top, ctx, ++n, colsPieza);
  if (piezas?.peores?.length) await slideTabla(doc, "Peores piezas", piezas.peores, ctx, ++n, colsPieza);

  // Resto de dominios con datos tabulares → tabla genérica (desglose, crosstab, etc.).
  const TITULOS_TABLA: Record<string, [string, string]> = {
    desglose: ["Desglose de interacciones", "celdas"],
    crosstab: ["Cruce de métricas", "celdas"],
    correlacion: ["Correlación con seguidores", "items"],
    ads: ["Publicidad pagada", "ads"],
    "piezas-listado": ["Listado de piezas", "piezas"],
  };
  for (const [dom, [titulo, clave]] of Object.entries(TITULOS_TABLA)) {
    const d = datos.get(dom) as Record<string, any> | undefined;
    const filas = d?.[clave];
    if (Array.isArray(filas) && filas.length) await slideTabla(doc, titulo, filas, ctx, ++n);
  }

  doc.save(`presentacion-${nombreArchivo}.pdf`);
}
