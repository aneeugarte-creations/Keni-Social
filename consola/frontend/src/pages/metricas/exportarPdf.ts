/**
 * Exportación del dashboard de Métricas a un PDF "presentación" (deck 16:9), generado
 * DIRECTAMENTE con jsPDF a partir de los datos vivos (los mismos que el CSV: las queries
 * activas de React Query). No rasteriza el DOM ni usa el diálogo de impresión: dibuja
 * diapositivas diseñadas —portada, tiles de KPIs, gráficas vectoriales (barras/líneas) y
 * tablas— con la marca Keni. Resultado: descarga directa, determinista, nítida e imposible
 * que cuelgue, lista para presentar a dirección.
 */
import { numeroCompacto, nombreFormato, nombreRed, porcentaje } from "@/lib/formato";
import { recargaSegura } from "@/lib/version";
import { colorDe } from "./coloresRed";
import { diasDePeriodo, partesMes, partesRango } from "./rango";
import type { RangoMetrica } from "@/types";

/**
 * `import()` de un módulo pesado (motor del PDF) resistente a chunks OBSOLETOS: tras un
 * deploy, una pestaña abierta conserva el `index.html` viejo que apunta a un hash que ya
 * dio 404, así que el import falla con "Failed to fetch dynamically imported module". En ese
 * caso recargamos en silencio para tomar el bundle nuevo (`recargaSegura` lleva guard
 * anti-bucle); si la recarga se suprime, devolvemos un error legible en vez del críptico.
 */
async function importarModulo<T>(carga: () => Promise<T>): Promise<T> {
  try {
    return await carga();
  } catch {
    if (recargaSegura()) return new Promise<T>(() => {}); // la recarga corta la ejecución
    throw new Error("La app se actualizó. Recarga la página e inténtalo de nuevo.");
  }
}

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
  formato: string;
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
/** Fila de datos genérica (un objeto de claves a valores desconocidos). */
type Fila = Record<string, unknown>;

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
  doc.text(`${ctx.marca} · ${ctx.red} · ${ctx.formato} · ${ctx.periodo}`, M, H - 28);
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
  doc.text(`${ctx.red}  ·  ${ctx.formato}  ·  ${ctx.periodo}`, M + 36, H / 2 + 22);
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

/** Máximo de filas por tabla del deck: una presentación RESUME, no vuelca la tabla entera
 *  (un volcado completo generaba cientos de páginas). El resto se anota al pie. */
const MAX_FILAS_TABLA = 12;

/**
 * Columna de una tabla del deck: ancho FIJO (px) y alineación. El ancho fijo + el elipsado
 * evitan que una columna se estreche hasta escribir el texto casi en vertical (lo que pasaba
 * con anchos automáticos y muchas columnas).
 */
interface ColTabla {
  clave: string;
  etiqueta: string;
  ancho: number;
  align?: "left" | "right" | "center";
}

/**
 * Una tabla (autoTable) en su diapositiva: filas ACOTADAS, columnas de ancho FIJO y texto
 * ELIPSADO (nunca volcado a vertical ni partido en una página por fila). Cabe en UNA
 * diapositiva; si sobran filas respecto al tope, lo anota al pie.
 */
async function slideTabla(
  doc: Doc,
  titulo: string,
  filasTodas: Array<Record<string, unknown>>,
  ctx: ContextoDeck,
  n: number,
  columnas: ColTabla[],
): Promise<void> {
  const y0 = abrirSlide(doc, titulo, ctx, n);
  if (filasTodas.length === 0) {
    text(doc, MUTED);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(14);
    doc.text("Sin datos en el periodo.", M, y0 + 40);
    return;
  }
  const filas = filasTodas.slice(0, MAX_FILAS_TABLA);
  const { default: autoTable } = await importarModulo(() => import("jspdf-autotable"));
  autoTable(doc, {
    head: [columnas.map((c) => c.etiqueta)],
    body: filas.map((f) => columnas.map((c) => formatoCelda(f[c.clave]))),
    startY: y0 + 16,
    margin: { left: M, right: M, bottom: 72 },
    tableWidth: W - 2 * M,
    // Acotadas a una página: ni la tabla ni una fila se parten en páginas nuevas.
    pageBreak: "avoid",
    rowPageBreak: "avoid",
    styles: {
      font: "helvetica",
      fontSize: 12,
      cellPadding: 9,
      minCellHeight: 30,
      overflow: "ellipsize",
      valign: "middle",
      textColor: aRgb(INK),
      lineColor: aRgb(LINEA),
      lineWidth: 0.5,
    },
    headStyles: { fillColor: aRgb(ACENTO), textColor: [255, 255, 255], fontStyle: "bold", fontSize: 12 },
    alternateRowStyles: { fillColor: aRgb(SUAVE) },
    columnStyles: Object.fromEntries(
      columnas.map((c, i) => [i, { cellWidth: c.ancho, halign: c.align ?? "left" }]),
    ),
  });
  if (filasTodas.length > filas.length) {
    text(doc, MUTED);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    doc.text(`Mostrando ${filas.length} de ${numeroCompacto(filasTodas.length)} filas.`, M, H - 46);
  }
}

function formatoCelda(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    return Number.isInteger(v)
      ? numeroCompacto(v)
      : v.toLocaleString("es-MX", { maximumFractionDigits: 1 });
  }
  if (typeof v === "object") return "";
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

/** Etiqueta legible de un estado de cobertura (espejo de `CoberturaRedes`). */
const ESTADO_COBERTURA: Record<string, string> = {
  con_datos: "Con datos",
  sin_metricas: "Sin métricas",
  no_conectada: "No conectada",
  sin_lectura: "Sin lectura",
  no_configurada: "No configurada",
  sin_credenciales: "Sin credenciales",
  presupuesto_agotado: "Límite de API",
};

/** Etiqueta legible para una clave cruda en la tabla genérica de respaldo. */
function etiquetaClave(k: string): string {
  const MAPA: Record<string, string> = {
    marca: "Marca",
    red: "Red",
    formato: "Formato",
    linea: "Línea",
    origen: "Origen",
    tipo: "Tipo",
    etiqueta: "Etiqueta",
    serie: "Serie",
    campania: "Campaña",
    n_piezas: "Piezas",
    piezas: "Piezas",
    visualizaciones: "Vistas",
    interacciones: "Interac.",
    engagement_pct: "Eng. %",
    gasto: "Gasto",
    impresiones: "Impresiones",
    clics: "Clics",
  };
  return MAPA[k] ?? k.charAt(0).toUpperCase() + k.slice(1).replace(/_/g, " ");
}

/**
 * Tabla GENÉRICA acotada para dominios sin slide a medida (líneas, por serie, ads…): toma
 * el array de filas, sus primeras ~6 claves escalares (descarta sub-objetos), reparte el
 * ancho a partes iguales y delega en `slideTabla` (que ya acota filas y elipsa el texto).
 */
async function slideTablaGenerica(
  doc: Doc,
  titulo: string,
  filas: Fila[],
  ctx: ContextoDeck,
  n: number,
): Promise<void> {
  const claves = Object.keys(filas[0])
    .filter((k) => {
      const v = filas[0][k];
      return v == null || typeof v !== "object"; // descarta sub-objetos (post_estrella, etc.)
    })
    .filter((k) => k !== "id" && k !== "marca_id")
    .slice(0, 6);
  if (claves.length === 0) return;
  const ancho = (W - 2 * M) / claves.length;
  const columnas: ColTabla[] = claves.map((k, i) => ({
    clave: k,
    etiqueta: etiquetaClave(k),
    ancho,
    align: i === 0 ? "left" : "right",
  }));
  await slideTabla(doc, titulo, filas, ctx, n, columnas);
}

/** Extrae el primer array de objetos de un payload de dominio (celdas/items/piezas/filas…). */
function filasDeDominio(dato: unknown): Fila[] {
  const d = (dato ?? {}) as Record<string, unknown>;
  for (const v of Object.values(d)) {
    if (Array.isArray(v) && v.length && typeof v[0] === "object" && v[0] != null) {
      return v as Fila[];
    }
  }
  return [];
}

/** Genera y DESCARGA el PDF presentación. Lanza si no hay datos. */
export async function descargarPresentacion(
  entradas: Array<[readonly unknown[], unknown]>,
  ctx: ContextoDeck,
  nombreArchivo: string,
): Promise<void> {
  const datos = porDominio(entradas);
  if (datos.size === 0) throw new Error("No hay datos cargados para el PDF.");

  const { jsPDF } = await importarModulo(() => import("jspdf"));
  const doc = new jsPDF({ orientation: "landscape", unit: "px", format: [W, H] });
  let n = 1;

  portada(doc, ctx);

  const reporte = datos.get("reporte") as
    | {
        total?: Record<string, number>;
        por_red?: Fila[];
        cuentas?: Fila[];
        cobertura_redes?: Fila[];
      }
    | undefined;
  if (reporte?.total) slideKpis(doc, reporte.total, ctx, ++n);

  // Un desglose por una dimensión con UN solo valor no aporta: con una sola marca/red,
  // ni la comparativa ni el detalle de esa dimensión tienen sentido (se omiten).
  const conDato = (f: Fila) =>
    (Number(f.visualizaciones) || 0) > 0 || (Number(f.interacciones) || 0) > 0;
  const nMarcas = reporte?.cuentas?.length ?? 0;
  const redesConDato = (reporte?.por_red ?? []).filter(conDato);
  const variasMarcas = nMarcas > 1;
  const variasRedes = redesConDato.length > 1;

  if (reporte?.por_red?.length && variasRedes) {
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
  if (reporte?.cuentas?.length && variasMarcas) {
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

  const tendencia = datos.get("tendencia") as { puntos?: Fila[] } | undefined;
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

  const seguidores = datos.get("seguidores") as { puntos?: Fila[] } | undefined;
  if (seguidores?.puntos?.length) {
    slideLineas(
      doc,
      "Crecimiento de seguidores",
      [{ nombre: "Seguidores", color: "#16a34a", valores: seguidores.puntos.map((p) => Number(p.total) || 0) }],
      ctx,
      ++n,
    );
  }

  // Top y "a revisar": lo más presentable del periodo (NO el listado completo de piezas, que
  // generaría cientos de páginas). La red se muestra con su nombre legible, el título elipsado.
  const piezas = datos.get("piezas") as { top?: Fila[]; peores?: Fila[] } | undefined;
  const colsPieza: ColTabla[] = [
    { clave: "titulo", etiqueta: "Título", ancho: 540 },
    { clave: "plataforma", etiqueta: "Red", ancho: 110 },
    { clave: "publicado", etiqueta: "Publicado", ancho: 120 },
    { clave: "visualizaciones", etiqueta: "Vistas", ancho: 130, align: "right" },
    { clave: "interacciones", etiqueta: "Interac.", ancho: 130, align: "right" },
    { clave: "engagement_pct", etiqueta: "Eng. %", ancho: 122, align: "right" },
  ];
  const prepPiezas = (arr: Fila[]) =>
    arr.map((p) => ({ ...p, plataforma: nombreRed(String(p.plataforma ?? "")) }));
  if (piezas?.top?.length)
    await slideTabla(doc, "Top piezas", prepPiezas(piezas.top), ctx, ++n, colsPieza);
  if (piezas?.peores?.length)
    await slideTabla(doc, "Piezas a revisar", prepPiezas(piezas.peores), ctx, ++n, colsPieza);

  // Desglose de interacciones por marca×red (resumen acotado, no la rejilla completa).
  const desglose = datos.get("desglose") as { celdas?: Fila[] } | undefined;
  if (desglose?.celdas?.length) {
    const colsDesglose: ColTabla[] = [
      { clave: "marca", etiqueta: "Marca", ancho: 250 },
      { clave: "red", etiqueta: "Red", ancho: 150 },
      { clave: "likes", etiqueta: "Me gusta", ancho: 188, align: "right" },
      { clave: "comentarios", etiqueta: "Comentarios", ancho: 188, align: "right" },
      { clave: "compartidos", etiqueta: "Compartidos", ancho: 188, align: "right" },
      { clave: "guardados", etiqueta: "Guardados", ancho: 188, align: "right" },
    ];
    const filas = desglose.celdas.map((c) => ({
      marca: String(c.marca ?? ""),
      red: nombreRed(String(c.red ?? "")),
      likes: Number(c.likes) || 0,
      comentarios: Number(c.comentarios) || 0,
      compartidos: Number(c.compartidos) || 0,
      guardados: Number(c.guardados) || 0,
    }));
    await slideTabla(doc, "Desglose de interacciones", filas, ctx, ++n, colsDesglose);
  }

  // Detalle por marca (tabla): solo con más de una marca (con una sola no hay nada que comparar).
  if (reporte?.cuentas?.length && variasMarcas) {
    const cols: ColTabla[] = [
      { clave: "marca", etiqueta: "Marca", ancho: 420 },
      { clave: "visualizaciones", etiqueta: "Vistas", ancho: 244, align: "right" },
      { clave: "interacciones", etiqueta: "Interacciones", ancho: 244, align: "right" },
      { clave: "engagement_pct", etiqueta: "Engagement", ancho: 244, align: "right" },
    ];
    const filas = reporte.cuentas.map((c) => ({
      marca: String(c.marca ?? c.marca_id ?? ""),
      visualizaciones: Number(c.visualizaciones) || 0,
      interacciones: Number(c.interacciones) || 0,
      engagement_pct: porcentaje(Number(c.engagement_pct) || 0),
    }));
    await slideTabla(doc, "Detalle por marca", filas, ctx, ++n, cols);
  }

  // Detalle por red (tabla): solo con más de una red con datos.
  if (variasRedes) {
    const cols: ColTabla[] = [
      { clave: "red", etiqueta: "Red", ancho: 420 },
      { clave: "visualizaciones", etiqueta: "Vistas", ancho: 244, align: "right" },
      { clave: "interacciones", etiqueta: "Interacciones", ancho: 244, align: "right" },
      { clave: "engagement_pct", etiqueta: "Engagement", ancho: 244, align: "right" },
    ];
    const filas = redesConDato.map((r) => ({
      red: nombreRed(String(r.red)),
      visualizaciones: Number(r.visualizaciones) || 0,
      interacciones: Number(r.interacciones) || 0,
      engagement_pct: porcentaje(Number(r.engagement_pct) || 0),
    }));
    await slideTabla(doc, "Detalle por red", filas, ctx, ++n, cols);
  }

  // Cobertura por red (aplana marca×red): por qué una red aporta o no datos.
  const cobertura = reporte?.cobertura_redes;
  if (Array.isArray(cobertura) && cobertura.length) {
    const cols: ColTabla[] = [
      { clave: "marca", etiqueta: "Marca", ancho: 220 },
      { clave: "red", etiqueta: "Red", ancho: 160 },
      { clave: "estado", etiqueta: "Estado", ancho: 200 },
      { clave: "visualizaciones", etiqueta: "Vistas", ancho: 190, align: "right" },
      { clave: "interacciones", etiqueta: "Interac.", ancho: 190, align: "right" },
      { clave: "engagement_pct", etiqueta: "Engagement", ancho: 192, align: "right" },
    ];
    const filas: Fila[] = [];
    for (const m of cobertura as Array<Record<string, unknown>>) {
      for (const r of (m.redes as Array<Record<string, unknown>>) ?? []) {
        filas.push({
          marca: String(m.marca ?? m.marca_id ?? ""),
          red: nombreRed(String(r.red)),
          estado: ESTADO_COBERTURA[String(r.estado)] ?? String(r.estado ?? "—"),
          visualizaciones: r.visualizaciones == null ? "—" : Number(r.visualizaciones),
          interacciones: r.interacciones == null ? "—" : Number(r.interacciones),
          engagement_pct: r.engagement_pct == null ? "—" : porcentaje(Number(r.engagement_pct)),
        });
      }
    }
    if (filas.length) await slideTabla(doc, "Cobertura por red", filas, ctx, ++n, cols);
  }

  // Cruce por formato (marca×red×formato).
  const crosstab = datos.get("crosstab") as { celdas?: Fila[] } | undefined;
  if (crosstab?.celdas?.length) {
    const cols: ColTabla[] = [
      { clave: "marca", etiqueta: "Marca", ancho: 210 },
      { clave: "red", etiqueta: "Red", ancho: 150 },
      { clave: "formato", etiqueta: "Formato", ancho: 170 },
      { clave: "n_piezas", etiqueta: "Piezas", ancho: 150, align: "right" },
      { clave: "visualizaciones", etiqueta: "Vistas", ancho: 232, align: "right" },
      { clave: "engagement_pct", etiqueta: "Engagement", ancho: 240, align: "right" },
    ];
    const filas = crosstab.celdas.map((c) => ({
      marca: String(c.marca ?? ""),
      red: nombreRed(String(c.red)),
      formato: nombreFormato(c.formato == null ? null : String(c.formato)),
      n_piezas: Number(c.n_piezas) || 0,
      visualizaciones: Number(c.visualizaciones) || 0,
      engagement_pct: porcentaje(Number(c.engagement_pct) || 0),
    }));
    await slideTabla(doc, "Rendimiento por formato", filas, ctx, ++n, cols);
  }

  // Correlación seguidores ↔ piezas (por día).
  const correlacion = datos.get("correlacion") as { items?: Fila[] } | undefined;
  if (correlacion?.items?.length) {
    const cols: ColTabla[] = [
      { clave: "fecha", etiqueta: "Día", ancho: 180 },
      { clave: "marca", etiqueta: "Marca", ancho: 220 },
      { clave: "red", etiqueta: "Red", ancho: 160 },
      { clave: "seguidores_ganados", etiqueta: "Seguidores", ancho: 210, align: "right" },
      { clave: "n_posts", etiqueta: "Piezas", ancho: 170, align: "right" },
      { clave: "seguidores_por_post", etiqueta: "Seg./pieza", ancho: 212, align: "right" },
    ];
    const filas = correlacion.items.map((it) => ({
      fecha: String(it.fecha ?? ""),
      marca: String(it.marca ?? ""),
      red: nombreRed(String(it.red)),
      seguidores_ganados: Number(it.seguidores_ganados) || 0,
      n_posts: Number(it.n_posts) || 0,
      seguidores_por_post: it.seguidores_por_post == null ? "—" : Number(it.seguidores_por_post),
    }));
    await slideTabla(doc, "Seguidores frente a piezas", filas, ctx, ++n, cols);
  }

  // Piezas del periodo (listado COMPLETO): acotado por `slideTabla` (top N + nota "de M").
  const listado = datos.get("piezas-listado") as { piezas?: Fila[] } | undefined;
  if (listado?.piezas?.length) {
    await slideTabla(doc, "Piezas del periodo", prepPiezas(listado.piezas), ctx, ++n, colsPieza);
  }

  // Resto de tablas en pantalla SIN slide a medida (Rendimiento por serie/línea, Publicidad):
  // tabla genérica acotada para no dejar contenido fuera del deck.
  const GENERICAS: Array<[string, string]> = [
    ["piezas-por-etiqueta", "Rendimiento por serie"],
    ["lineas", "Rendimiento por línea"],
    ["ads", "Publicidad"],
  ];
  for (const [dom, titulo] of GENERICAS) {
    const filas = filasDeDominio(datos.get(dom));
    if (filas.length) await slideTablaGenerica(doc, titulo, filas, ctx, ++n);
  }

  doc.save(`presentacion-${nombreArchivo}.pdf`);
}
