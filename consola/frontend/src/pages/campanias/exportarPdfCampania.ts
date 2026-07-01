/**
 * Exportación de una CAMPAÑA a un PDF "testigo" (deck 16:9): portada, KPIs, tendencia,
 * desglose por red y la tabla de piezas del periodo, más un cierre con QR si hay un enlace
 * público vigente. Mismo motor de rasterización que el PDF de Métricas
 * (`@/lib/rasterizarDeck`); el contenido vive en `informe/DeckCampania.tsx`.
 */
import { createElement } from "react";

import { importarModulo, rasterizarDeckAPdf } from "@/lib/rasterizarDeck";
import { slug } from "@/lib/formato";
import { comprobarVersionNueva, recargaSegura } from "@/lib/version";
import type { AnaliticaCampania } from "@/types";

import { urlEnlace } from "./formato";

export interface ContextoPdfCampania {
  periodoEtiqueta: string;
  /** Modo cliente: la tabla de piezas suma lo pagado a lo orgánico (sin rastro de pauta). */
  ocultarAds: boolean;
  /** Token del enlace público vigente para este periodo/modo, si existe. */
  tokenEnlace?: string | null;
}

/**
 * Genera y DESCARGA el PDF testigo de una campaña. Lanza si `datos` no trae piezas Y tampoco
 * hay tendencia (campaña vacía en el periodo: no tiene sentido un PDF en blanco).
 */
export async function descargarPdfCampania(
  datos: AnaliticaCampania,
  ctx: ContextoPdfCampania,
): Promise<void> {
  if (datos.piezas.length === 0 && datos.tendencia.puntos.length === 0) {
    throw new Error("No hay piezas en este periodo para generar el PDF.");
  }

  // Mismo guard que el PDF de Métricas: si ya hay un deploy más reciente que este bundle,
  // recargamos para generar el PDF con el diseño DESPLEGADO en vez del viejo en memoria.
  {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 2500);
    let hayNueva = false;
    try {
      hayNueva = await comprobarVersionNueva(ac.signal);
    } finally {
      clearTimeout(t);
    }
    if (hayNueva && recargaSegura()) await new Promise<never>(() => {}); // la recarga corta la ejecución
  }

  let enlace: { url: string; qrDataUrl: string } | null = null;
  if (ctx.tokenEnlace) {
    const url = urlEnlace(ctx.tokenEnlace);
    const { default: qrcode } = await importarModulo(() => import("qrcode-generator"));
    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    enlace = { url, qrDataUrl: qr.createDataURL(8, 4) };
  }

  const { DeckCampania } = await importarModulo(() => import("./informe/DeckCampania"));
  const nombreArchivo = `campania-${slug(datos.campania.nombre)}-${slug(ctx.periodoEtiqueta)}`;
  await rasterizarDeckAPdf(
    createElement(DeckCampania, {
      datos,
      periodoEtiqueta: ctx.periodoEtiqueta,
      generadoEn: datos.generado_en,
      ocultarAds: ctx.ocultarAds,
      enlace,
    }),
    nombreArchivo,
  );
}
