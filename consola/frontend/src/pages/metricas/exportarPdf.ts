/**
 * Exportación del dashboard de Métricas a un PDF "presentación" (deck 16:9). Monta el informe
 * REAL (`<Informe>`: los mismos componentes Tremor que la app, marca protagonista, esquema
 * Sereno, conclusiones) fuera de pantalla a tamaño real, rasteriza cada diapositiva con
 * `html-to-image` y compone un jsPDF (una página por diapositiva, 1280×720). Los datos salen
 * de las queries activas de React Query (`desdeEntradas`), los mismos que el CSV.
 */
import { createElement } from "react";

import { recargaSegura } from "@/lib/version";
import type { RangoMetrica } from "@/types";

import { desdeEntradas } from "./informe/desdeEntradas";
import { diasDePeriodo, partesMes, partesRango } from "./rango";

/**
 * `import()` de un módulo pesado (motor del PDF, deck, rasterizador) resistente a chunks
 * OBSOLETOS: tras un deploy, una pestaña abierta apunta a un hash que ya dio 404 y el import
 * falla con "Failed to fetch dynamically imported module". En ese caso recargamos en silencio
 * (`recargaSegura` lleva guard anti-bucle); si se suprime, devolvemos un error legible.
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
  /** Id de métricas de la marca (`claro_sports`, …) para resolver su logo; ausente si todas. */
  marcaId?: string;
}

const W = 1280;
const H = 720;
/** Fondo del informe = lienzo gris de la app. */
const FONDO = "#fafafa";

/** Espera dos frames + un margen para que recharts mida el contenedor y pinte antes de rasterizar. */
function esperarPintado(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() =>
      requestAnimationFrame(() => setTimeout(() => resolve(), 500)),
    );
  });
}

/**
 * Hornea el color COMPUTADO (fill/stroke/stop-color) como atributo inline en cada elemento
 * SVG. `html-to-image` no captura el color de los SVG cuando viene por CLASE CSS (las gráficas
 * Tremor lo aplican así); en el bundle de producción el CSS es externo y el rasterizado salía
 * en negro/gris. Con el color ya inline en el atributo, el clon que rasteriza lo conserva.
 */
function hornearColoresSvg(raiz: HTMLElement): void {
  raiz.querySelectorAll("svg").forEach((svg) => {
    svg.querySelectorAll<SVGElement>("*").forEach((el) => {
      const cs = getComputedStyle(el);
      if (cs.fill && cs.fill !== "none") el.setAttribute("fill", cs.fill);
      if (cs.stroke && cs.stroke !== "none") el.setAttribute("stroke", cs.stroke);
      if (el.tagName.toLowerCase() === "stop" && cs.stopColor) el.setAttribute("stop-color", cs.stopColor);
    });
  });
}

/**
 * Genera y DESCARGA el PDF presentación: monta `<Informe>` oculto a tamaño real, rasteriza
 * cada `.informe-slide` y la coloca como página del jsPDF. Lanza si no hay datos.
 */
export async function descargarPresentacion(
  entradas: Array<[readonly unknown[], unknown]>,
  ctx: ContextoDeck,
  nombreArchivo: string,
): Promise<void> {
  if (entradas.length === 0) throw new Error("No hay datos cargados para el PDF.");
  const props = desdeEntradas(entradas, ctx);

  const [{ createRoot }, { Informe }, { toJpeg }, { jsPDF }] = await Promise.all([
    importarModulo(() => import("react-dom/client")),
    importarModulo(() => import("./informe/Informe")),
    importarModulo(() => import("html-to-image")),
    importarModulo(() => import("jspdf")),
  ]);

  // Monta el deck fuera de pantalla, a tamaño real (1280px de ancho), sobre el fondo del informe.
  const host = document.createElement("div");
  host.style.cssText = `position:fixed; left:-100000px; top:0; width:${W}px; background:${FONDO};`;
  document.body.appendChild(host);
  const root = createRoot(host);

  try {
    root.render(createElement(Informe, { data: props }));
    if (document.fonts?.ready) await document.fonts.ready;
    await esperarPintado();

    const slides = Array.from(host.querySelectorAll<HTMLElement>(".informe-slide"));
    if (slides.length === 0) throw new Error("No se pudo construir el informe.");
    hornearColoresSvg(host);

    const doc = new jsPDF({ orientation: "landscape", unit: "px", format: [W, H] });
    for (let i = 0; i < slides.length; i++) {
      // JPEG (no PNG): el PNG sin pérdida dispara el peso a cientos de MB; el JPEG de calidad
      // alta sobre lienzo plano mantiene nitidez con un archivo ligero. pixelRatio 3 da texto
      // crujiente (a 2× se veía algo borroso) y sigue pesando poco al ser fondo casi plano.
      const img = await toJpeg(slides[i], {
        width: W,
        height: H,
        pixelRatio: 3,
        backgroundColor: FONDO,
        quality: 0.97,
        cacheBust: true,
      });
      if (i > 0) doc.addPage([W, H], "landscape");
      doc.addImage(img, "JPEG", 0, 0, W, H);
    }
    doc.save(`informe-${nombreArchivo}.pdf`);
  } finally {
    root.unmount();
    host.remove();
  }
}
