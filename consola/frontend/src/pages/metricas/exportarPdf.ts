/**
 * Exportación del dashboard de Métricas a un PDF "presentación" (deck 16:9).
 *
 * No re-renderiza nada: captura los bloques YA pintados de la página (los nodos con
 * `data-slide` dentro del contenedor `data-deck-root`), de modo que el PDF refleja el
 * ESTADO VIVO —marca, periodo, red, filtros y orden de columnas aplicados—. Cada bloque
 * es una diapositiva: portada y bandas de título van en vectorial (texto nítido); el
 * contenido del bloque se rasteriza con html2canvas y se encaja en la diapositiva
 * conservando su proporción. Los colores (fondo/texto) se leen del tema vivo para que el
 * deck se sienta idéntico a la página en claro y en oscuro.
 */
import { COLOR_RED } from "./coloresRed";
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

interface OpcionesDeck {
  /** Contenedor con los nodos `[data-slide]` a capturar (el cuerpo del dashboard). */
  raiz: HTMLElement;
  /** Etiqueta de marca (o "Todas las marcas"). */
  marca: string;
  /** Etiqueta de red (o "Todas las redes"). */
  red: string;
  /** Etiqueta del periodo. */
  periodo: string;
  /** ISO de generación del reporte, si lo hay. */
  generadoEn?: string;
  /** Sufijo del nombre de archivo (marca/red/periodo ya normalizados). */
  nombreArchivo: string;
}

/** Parse de un `rgb(r, g, b)` / `rgba(...)` a triplete. Cae a negro si no parsea. */
function aRgb(color: string): [number, number, number] {
  const m = color.match(/(\d+(?:\.\d+)?)/g);
  if (!m || m.length < 3) return [0, 0, 0];
  return [Number(m[0]), Number(m[1]), Number(m[2])];
}

/** Color de acento del deck: el de la red elegida, o violeta neutro si son todas. */
function acento(red: string): [number, number, number] {
  const id = Object.keys(COLOR_RED).find((k) => red.toLowerCase().includes(k));
  return aRgb(id ? COLOR_RED[id] : "#a855f7");
}

function fechaLegible(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("es-MX", {
    day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/**
 * Genera y descarga el PDF presentación. Lanza si no hay diapositivas que capturar.
 * Devuelve el nombre del archivo generado.
 */
export async function exportarPresentacion(opts: OpcionesDeck): Promise<string> {
  const nodos = Array.from(
    opts.raiz.querySelectorAll<HTMLElement>("[data-slide]"),
  ).filter((n) => n.offsetWidth > 0 && n.offsetHeight > 0);
  if (nodos.length === 0) throw new Error("No hay contenido visible para exportar.");

  // Carga diferida: jspdf + html2canvas son pesados y solo hacen falta al exportar, así que
  // no lastran el bundle de la página de métricas (van a su propio chunk bajo demanda).
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import("html2canvas"),
    import("jspdf"),
  ]);

  const estiloBody = getComputedStyle(document.body);
  const fondo = aRgb(estiloBody.backgroundColor);
  const texto = aRgb(estiloBody.color);
  const tenue: [number, number, number] = [
    Math.round((fondo[0] + texto[0]) / 2),
    Math.round((fondo[1] + texto[1]) / 2),
    Math.round((fondo[2] + texto[2]) / 2),
  ];
  const ac = acento(opts.red);

  const doc = new jsPDF({ orientation: "landscape", unit: "px", format: [1280, 720] });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const M = 48; // margen
  const fondoHex = fondo;

  const pintarFondo = () => {
    doc.setFillColor(fondoHex[0], fondoHex[1], fondoHex[2]);
    doc.rect(0, 0, W, H, "F");
  };

  // --- Portada (vectorial) ---
  pintarFondo();
  doc.setFillColor(ac[0], ac[1], ac[2]);
  doc.rect(M, H / 2 - 84, 6, 168, "F"); // barra de acento
  doc.setTextColor(texto[0], texto[1], texto[2]);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(54);
  doc.text(opts.marca, M + 28, H / 2 - 28);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(24);
  doc.setTextColor(tenue[0], tenue[1], tenue[2]);
  doc.text(`${opts.red}  ·  ${opts.periodo}`, M + 28, H / 2 + 14);
  doc.setFontSize(14);
  const pie = ["Keni Social — Analíticas", fechaLegible(opts.generadoEn)]
    .filter(Boolean)
    .join("  ·  ");
  doc.text(pie, M + 28, H / 2 + 56);

  // --- Diapositivas de contenido (rasterizadas) ---
  const fondoCss = estiloBody.backgroundColor;
  for (const nodo of nodos) {
    const titulo = nodo.getAttribute("data-slide") || "";
    const canvas = await html2canvas(nodo, {
      scale: 2,
      backgroundColor: fondoCss,
      useCORS: true,
      logging: false,
      windowWidth: nodo.scrollWidth,
    });

    doc.addPage();
    pintarFondo();

    const bandaY = M;
    if (titulo) {
      doc.setTextColor(texto[0], texto[1], texto[2]);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(26);
      doc.text(titulo, M, bandaY + 12);
      doc.setDrawColor(ac[0], ac[1], ac[2]);
      doc.setLineWidth(3);
      doc.line(M, bandaY + 26, M + 56, bandaY + 26);
    }

    // Área disponible bajo la banda de título.
    const areaY = bandaY + (titulo ? 48 : 0);
    const areaW = W - 2 * M;
    const areaH = H - areaY - M;
    const escala = Math.min(areaW / canvas.width, areaH / canvas.height);
    const w = canvas.width * escala;
    const h = canvas.height * escala;
    const x = M + (areaW - w) / 2;
    doc.addImage(canvas.toDataURL("image/png"), "PNG", x, areaY, w, h, undefined, "FAST");

    // Pie de página discreto.
    doc.setTextColor(tenue[0], tenue[1], tenue[2]);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(11);
    doc.text(`${opts.marca} · ${opts.red} · ${opts.periodo}`, M, H - 18);
  }

  const nombre = `presentacion-${opts.nombreArchivo}.pdf`;
  doc.save(nombre);
  return nombre;
}
