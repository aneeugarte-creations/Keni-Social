/**
 * Motor compartido para rasterizar un deck de diapositivas (`.informe-slide`, 1280×720) a un
 * PDF descargable. Monta el elemento React dado fuera de pantalla, espera a que fuentes/
 * imágenes/gráficas terminen de pintar, rasteriza cada lámina con `html-to-image` y compone un
 * jsPDF (una página por lámina). Usado por el deck de Métricas y el de Campañas: la lógica de
 * QUÉ se muestra en cada lámina vive en su propio componente; esto solo sabe convertir
 * ".informe-slide" en páginas de PDF.
 */
import type { ReactElement } from "react";

import { recargaSegura } from "@/lib/version";

/**
 * `import()` de un módulo pesado (rasterizador, deck) resistente a chunks OBSOLETOS: tras un
 * deploy, una pestaña abierta apunta a un hash que ya dio 404 y el import falla con "Failed to
 * fetch dynamically imported module". En ese caso recargamos en silencio (`recargaSegura` lleva
 * guard anti-bucle); si se suprime, devolvemos un error legible.
 */
export async function importarModulo<T>(carga: () => Promise<T>): Promise<T> {
  try {
    return await carga();
  } catch {
    if (recargaSegura()) return new Promise<T>(() => {}); // la recarga corta la ejecución
    throw new Error("La app se actualizó. Recarga la página e inténtalo de nuevo.");
  }
}

const W = 1280;
const H = 720;
/** Fondo por defecto del lienzo (gris de la app); cada lámina puede pintar el suyo propio. */
const FONDO = "#fafafa";

/** Espera dos frames + un margen para que las gráficas midan el contenedor y pinten antes de rasterizar. */
function esperarPintado(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() =>
      requestAnimationFrame(() => setTimeout(() => resolve(), 500)),
    );
  });
}

/** Resuelve cuando la `<img>` termina de cargar, con éxito o con error (nunca rechaza). */
function cargaTerminada(img: HTMLImageElement): Promise<void> {
  if (img.complete) return Promise.resolve();
  return new Promise<void>((resolve) => {
    img.addEventListener("load", () => resolve(), { once: true });
    img.addEventListener("error", () => resolve(), { once: true });
  });
}

/** Las `<img>` con src que terminaron SIN píxeles: el asset falló (red caída, hash purgado). */
export function imagenesRotas(imgs: HTMLImageElement[]): HTMLImageElement[] {
  return imgs.filter((img) => img.getAttribute("src") && img.naturalWidth === 0);
}

/**
 * Espera a que cada `<img>` del host esté cargada Y decodificada, y GARANTIZA que ninguna
 * quedó rota: `document.fonts.ready` solo cubre fuentes, y una imagen fallida (red, asset
 * purgado tras un deploy) se rasterizaría como hueco en blanco. Una rota se reintenta una
 * vez; si persiste, se ABORTA la generación con un error legible — nunca se entrega un PDF
 * sin logo/QR. Tras esto el asset vive en la caché del navegador, así que el fetch interno
 * de `html-to-image` lo incrusta desde caché caliente en vez de pedirlo crudo.
 */
async function esperarImagenes(raiz: HTMLElement): Promise<void> {
  const imgs = Array.from(raiz.querySelectorAll("img"));
  await Promise.all(imgs.map(cargaTerminada));

  // Reintento único de las rotas: re-asignar `src` vuelve a disparar la petición del asset.
  const reintentar = imagenesRotas(imgs);
  await Promise.all(
    reintentar.map((img) => {
      const src = img.src;
      img.src = "";
      img.src = src;
      return cargaTerminada(img);
    }),
  );

  const rotas = imagenesRotas(imgs);
  if (rotas.length > 0) {
    throw new Error(
      `No se ${rotas.length === 1 ? "pudo cargar 1 imagen" : `pudieron cargar ${rotas.length} imágenes`} del informe (logo o QR). Revisa la conexión y recarga la página antes de reintentar.`,
    );
  }

  await Promise.all(imgs.map((img) => img.decode?.().catch(() => {})));
}

/**
 * Hornea el color COMPUTADO (fill/stroke/stop-color) como atributo inline en cada elemento SVG.
 * `html-to-image` no captura el color de los SVG cuando viene por CLASE CSS (las gráficas lo
 * aplican así); en el bundle de producción el CSS es externo y el rasterizado salía en
 * negro/gris. Con el color ya inline en el atributo, el clon que rasteriza lo conserva.
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
 * Monta `elemento` fuera de pantalla, rasteriza sus `.informe-slide` y DESCARGA el PDF
 * resultante como `informe-{nombreArchivo}.pdf`. Lanza si no se generó ninguna lámina.
 */
export async function rasterizarDeckAPdf(
  elemento: ReactElement,
  nombreArchivo: string,
): Promise<void> {
  const [{ createRoot }, { toJpeg }, { jsPDF }] = await Promise.all([
    importarModulo(() => import("react-dom/client")),
    importarModulo(() => import("html-to-image")),
    importarModulo(() => import("jspdf")),
  ]);

  // Monta el deck fuera de pantalla, a tamaño real (1280px de ancho), sobre el fondo del informe.
  const host = document.createElement("div");
  host.style.cssText = `position:fixed; left:-100000px; top:0; width:${W}px; background:${FONDO};`;
  document.body.appendChild(host);
  const root = createRoot(host);

  try {
    root.render(elemento);
    if (document.fonts?.ready) await document.fonts.ready;
    await esperarImagenes(host);
    await esperarPintado();

    const slides = Array.from(host.querySelectorAll<HTMLElement>(".informe-slide"));
    if (slides.length === 0) throw new Error("No se pudo construir el informe.");
    hornearColoresSvg(host);

    type Enlace = { x: number; y: number; w: number; h: number; url: string };
    const imagenes: string[] = new Array(slides.length);
    const enlaces: Enlace[][] = new Array(slides.length);

    // Se rasteriza de la ÚLTIMA lámina a la PRIMERA. html-to-image degrada las rasterizaciones
    // sucesivas y encoge las láminas DENSAS capturadas tarde (tabla y cierre salían reducidas en
    // una esquina); como esas láminas densas van al final del deck, capturarlas primero las deja
    // intactas, y las del principio (portada, resumen) aguantan bien aunque caigan tarde. Las
    // páginas se ensamblan luego en el orden correcto.
    for (let i = slides.length - 1; i >= 0; i--) {
      // JPEG (no PNG): el PNG sin pérdida dispara el peso a cientos de MB; el JPEG de calidad
      // alta sobre lienzo plano mantiene nitidez con un archivo ligero. pixelRatio 3 da texto
      // crujiente (a 2× se veía algo borroso) y sigue pesando poco al ser fondo casi plano. El
      // fondo de la imagen = el fondo REAL de la lámina (gris por defecto, o el color de marca en
      // la portada). La opción `backgroundColor` de html-to-image pisa el fondo del nodo, así que
      // hay que leerlo de la propia lámina o la portada saldría gris.
      const fondoSlide = getComputedStyle(slides[i]).backgroundColor || FONDO;
      imagenes[i] = await toJpeg(slides[i], {
        width: W,
        height: H,
        pixelRatio: 3,
        backgroundColor: fondoSlide,
        quality: 0.97,
      });
      // Enlaces clicables (QR/post): la imagen rasterizada no conserva los `<a>`. Guardamos las
      // zonas ahora —la lámina está en el DOM— y superponemos los enlaces al ensamblar el PDF.
      const sRect = slides[i].getBoundingClientRect();
      enlaces[i] = Array.from(slides[i].querySelectorAll<HTMLElement>("[data-pdf-enlace]"))
        .map((el) => {
          const url = el.getAttribute("data-pdf-enlace");
          if (!url) return null;
          const r = el.getBoundingClientRect();
          return { x: r.left - sRect.left, y: r.top - sRect.top, w: r.width, h: r.height, url };
        })
        .filter((e): e is Enlace => e != null);
    }

    const doc = new jsPDF({ orientation: "landscape", unit: "px", format: [W, H] });
    for (let i = 0; i < slides.length; i++) {
      if (i > 0) doc.addPage([W, H], "landscape");
      doc.addImage(imagenes[i], "JPEG", 0, 0, W, H);
      // El lienzo del PDF es 1280×720 px = los mismos px CSS de la diapositiva (1:1).
      for (const e of enlaces[i]) doc.link(e.x, e.y, e.w, e.h, { url: e.url });
    }
    doc.save(`informe-${nombreArchivo}.pdf`);
  } finally {
    root.unmount();
    host.remove();
  }
}
