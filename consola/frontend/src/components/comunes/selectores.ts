/**
 * Centinelas y helpers compartidos por los selectores de marca y red.
 *
 * Vive en su propio módulo (sin componentes) para no romper el fast-refresh de
 * los `.tsx` y para tener una única fuente de verdad de los centinelas:
 * `MARCA_TODAS` y `RED_TODAS` (ambos `"__todas__"`). Antes había tres centinelas
 * distintos (`"todas"`, `"__todos__"`, `"__ninguna__"`) repartidos por la app.
 */

/** Valor único que representa "todas las marcas" / "sin marca concreta". */
export const MARCA_TODAS = "__todas__";

/** Valor único que representa "todas las redes" / "cualquier red". */
export const RED_TODAS = "__todas__";

/**
 * Traduce el valor del control de marca al parámetro de la API: el centinela se
 * vuelve `undefined` (no filtrar / sin marca).
 */
export function marcaParam(valor: string): string | undefined {
  return valor === MARCA_TODAS ? undefined : valor;
}

/**
 * Traduce un valor de la API (`""`/`null` = sin marca) al valor del control,
 * usando el centinela para representar "sin marca".
 */
export function desdeMarca(marca: string | null | undefined): string {
  return marca ? marca : MARCA_TODAS;
}

/** Traduce el valor del control de red al parámetro de la API (centinela → undefined). */
export function redParam(valor: string): string | undefined {
  return valor === RED_TODAS ? undefined : valor;
}

/** Traduce un valor de la API (`""`/`null` = cualquier red) al valor del control. */
export function desdeRed(red: string | null | undefined): string {
  return red ? red : RED_TODAS;
}
