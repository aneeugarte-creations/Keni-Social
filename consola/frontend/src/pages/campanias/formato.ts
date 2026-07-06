/**
 * Helpers de presentacion del apartado Campañas (fechas es-MX).
 *
 * Los formateadores numéricos se reutilizan de Métricas (`../metricas/formato`)
 * para que toda la consola hable el mismo idioma visual.
 */
import { formatearDia, formatearFechaCorta, formatearFechaHoraCorta } from "@/lib/fecha";
import type { Campania, EnlacePublicoCampania, PiezaCampania } from "@/types";

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

/** Clave ESTABLE y única de una pieza dentro de la tabla de una campaña, para seleccionarla.
 * El `id` del backend NO basta: la misma publicación puede salir en dos redes (mismo `id`,
 * distinta `red`) y las filas de Ads usan un `id` sintético `ad:<nombre>` que podría chocar
 * si dos boosts comparten nombre. Se compone `id|red|org?ad` y, como último seguro, el índice
 * de fila (el orden de `datos.piezas` es estable dentro de una misma analítica). */
export function clavePieza(p: PiezaCampania, indice: number): string {
  return `${p.id}|${p.red}|${p.es_inorganico ? "ad" : "org"}|${indice}`;
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

/** Tope de pauta y disponible restante dado lo gastado en el periodo. `null` si la campaña
 * no tiene precio de venta definido (0). */
export function calcularRentabilidad(
  campania: Pick<Campania, "precio_venta" | "margen_objetivo_pct">,
  gastoPeriodo: number,
): { tope: number; disponible: number; sobreTope: boolean } | null {
  if (campania.precio_venta <= 0) return null;
  const tope = campania.precio_venta * (1 - campania.margen_objetivo_pct / 100);
  const disponible = tope - gastoPeriodo;
  return { tope, disponible, sobreTope: disponible < 0 };
}
