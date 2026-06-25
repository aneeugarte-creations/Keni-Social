/**
 * Verificación FIEL del PDF: en vez de capturar el DOM con el render nativo de Chrome (lo que
 * hace captura-deck.sh), reproduce el pipeline EXACTO de exportarPdf.ts —montar el deck oculto,
 * hornear colores SVG, `html-to-image.toJpeg` por lámina a pixelRatio 3— y pinta los JPEG
 * resultantes como <img data-slide>. Esos píxeles SON los que van a cada página del jsPDF. Una
 * captura/volcado de esta página = lo que verá el directivo en el PDF, no una aproximación.
 * Solo dev (no entra al build de producción).
 */
import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { toJpeg } from "html-to-image";

import "@/index.css";

import { Informe } from "@/pages/metricas/informe/Informe";
import { desdeEntradas } from "@/pages/metricas/informe/desdeEntradas";
import { MUESTRAS } from "./datos";

const W = 1280;
const H = 720;
const FONDO = "#fafafa";

function esperarPintado(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(resolve, 600)));
  });
}

/** Igual que exportarPdf.ts: hornea fill/stroke/stop-color computados como atributo inline. */
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

async function main() {
  const params = new URLSearchParams(location.search);
  const clave = params.get("marca") ?? "unotv";
  const muestra = MUESTRAS[clave] ?? MUESTRAS.unotv;
  const props = desdeEntradas(muestra.entradas, muestra.ctx);

  const host = document.createElement("div");
  host.style.cssText = `position:fixed; left:-100000px; top:0; width:${W}px; background:${FONDO};`;
  document.body.appendChild(host);
  const root = createRoot(host);
  root.render(createElement(Informe, { data: props }));

  if (document.fonts?.ready) await document.fonts.ready;
  await esperarPintado();

  const slides = Array.from(host.querySelectorAll<HTMLElement>(".informe-slide"));
  hornearColoresSvg(host);

  // Sink opcional: empuja cada JPEG real a un receptor HTTP local (verificacion headless fiable
  // sin depender del timing de --dump-dom). Sin `?sink=` la pagina solo pinta los <img>.
  const sink = params.get("sink");

  const salida = document.getElementById("root")!;
  salida.innerHTML = "";
  for (let i = 0; i < slides.length; i++) {
    const fondoSlide = getComputedStyle(slides[i]).backgroundColor || FONDO;
    const dataUrl = await toJpeg(slides[i], {
      width: W,
      height: H,
      pixelRatio: 3,
      backgroundColor: fondoSlide,
      quality: 0.97,
      cacheBust: true,
    });
    const img = document.createElement("img");
    img.setAttribute("data-slide", String(i));
    img.src = dataUrl;
    img.style.cssText = "display:block; width:1280px; height:720px;";
    salida.appendChild(img);
    if (sink) await fetch(`http://localhost:${sink}/slide?i=${i}`, { method: "POST", body: dataUrl });
  }

  root.unmount();
  host.remove();
  const marca = document.createElement("div");
  marca.id = "pdf-real-listo";
  marca.textContent = `LISTO ${slides.length}`;
  document.body.appendChild(marca);
  if (sink) await fetch(`http://localhost:${sink}/done?n=${slides.length}`, { method: "POST" });
}

void main();
