/**
 * Helpers de presentacion del apartado Campañas (fechas es-MX).
 *
 * Los formateadores numéricos se reutilizan de Métricas (`../metricas/formato`)
 * para que toda la consola hable el mismo idioma visual.
 */
import { formatearDia, formatearFechaCorta, formatearFechaHoraCorta } from "@/lib/fecha";
import type { EnlacePublicoCampania, PiezaCampania } from "@/types";

// Fechas en hora CDMX (los instantes del backend son UTC): el formateo vive en
// `@/lib/fecha`. Aquí solo se conserva el fallback "—" propio de Campañas.

/** Fecha corta es-MX a partir de un ISO (día + mes). Ej.: "25 may". */
export function fechaCorta(iso: string): string {
  return formatearFechaCorta(iso) || "—";
}

/** Fecha con hora es-MX a partir de un ISO. Ej.: "25 may, 12:00". */
export function fechaHora(iso: string): string {
  return formatearFechaHoraCorta(iso) || "—";
}

/** Día legible es-MX a partir de `YYYY-MM-DD`. */
export function fechaDia(dia: string): string {
  return formatearDia(dia);
}

/** Visualizaciones a MOSTRAR de una pieza: en modo cliente (ocultarAds) se suman las pagadas
 * a las orgánicas para que el inorgánico se vea como un post normal. */
export function visEfectivas(p: PiezaCampania, ocultarAds: boolean): number {
  return p.visualizaciones + (ocultarAds ? p.visualizaciones_pagadas : 0);
}

/** URL pública (capability-URL) de un enlace de campaña a partir de su token. */
export function urlEnlace(token: string): string {
  return `${window.location.origin}/c/${token}`;
}

/** Enlace público VIGENTE que congela el mismo periodo/modo que se está viendo ahora, si
 * existe (para cerrar el PDF con su QR). `null` si no hay ninguno que coincida. */
export function enlaceVigentePara(
  enlaces: EnlacePublicoCampania[],
  rango: string,
  ocultarAds: boolean,
): EnlacePublicoCampania | null {
  return enlaces.find((e) => e.vigente && e.rango === rango && e.ocultar_ads === ocultarAds) ?? null;
}
