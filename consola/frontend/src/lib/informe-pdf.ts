/**
 * Genera un PDF A4 a partir de un nodo del DOM ya renderizado (el informe de campaña).
 * Captura el nodo a un canvas (html-to-image: usa el render NATIVO del navegador vía
 * foreignObject, así respeta fuente Geist, colores HSL y el SVG de la gráfica) y lo reparte
 * en páginas A4. Las librerías pesadas (html-to-image, jspdf) se cargan SOLO aquí (import
 * dinámico): no entran en el bundle de la ruta hasta que se pulsa «Descargar PDF».
 */
import { descargarBlob } from "@/lib/descargas";

const MARGEN_MM = 8;

export async function generarPdfInforme(nodo: HTMLElement, nombreArchivo: string): Promise<void> {
  // Geist se carga del CDN: esperar a que esté lista evita capturar con la fuente de respaldo.
  if (document.fonts?.ready) await document.fonts.ready;

  const { toCanvas } = await import("html-to-image");
  const { jsPDF } = await import("jspdf");

  const canvas = await toCanvas(nodo, {
    pixelRatio: 2,
    backgroundColor: "#ffffff",
    cacheBust: true,
  });

  const pdf = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const imgW = pageW - MARGEN_MM * 2;
  // px del canvas por mm impreso (el ancho del canvas se escala a `imgW`).
  const pxPorMm = canvas.width / imgW;
  const altoPaginaPx = (pageH - MARGEN_MM * 2) * pxPorMm;

  let yPx = 0;
  let primera = true;
  while (yPx < canvas.height) {
    const trozoPx = Math.min(altoPaginaPx, canvas.height - yPx);
    const trozo = document.createElement("canvas");
    trozo.width = canvas.width;
    trozo.height = Math.ceil(trozoPx);
    const ctx = trozo.getContext("2d");
    if (ctx) {
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, trozo.width, trozo.height);
      ctx.drawImage(canvas, 0, yPx, canvas.width, trozoPx, 0, 0, canvas.width, trozoPx);
    }
    if (!primera) pdf.addPage();
    pdf.addImage(trozo.toDataURL("image/png"), "PNG", MARGEN_MM, MARGEN_MM, imgW, trozoPx / pxPorMm);
    yPx += trozoPx;
    primera = false;
  }

  descargarBlob(pdf.output("blob"), nombreArchivo);
}
