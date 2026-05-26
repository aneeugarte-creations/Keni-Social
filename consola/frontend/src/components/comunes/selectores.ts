/**
 * Centinelas y helpers compartidos por los selectores de marca y red.
 *
 * Vive en su propio módulo (sin componentes) para no romper el fast-refresh de
 * los `.tsx` y para tener una única fuente de verdad de los centinelas:
 * `MARCA_TODAS` y `RED_TODAS` (ambos `"__todas__"`), más `NINGUNA`
 * (`"__ninguna__"`) para "sin marca / sin red / sin fijar". Antes estos tres
 * centinelas se declaraban localmente con nombres distintos (`"todas"`,
 * `"__todos__"`, `"__ninguna__"`) repartidos por la app.
 */

/** Valor único que representa "todas las marcas" / "sin marca concreta". */
export const MARCA_TODAS = "__todas__";

/** Valor único que representa "todas las redes" / "cualquier red". */
export const RED_TODAS = "__todas__";

/**
 * Valor único que representa "ninguna selección" en campos OPCIONALES:
 * "sin marca", "sin red" o "sin fijar". Radix `Select` no admite `value=""` en
 * un `SelectItem`, así que este centinela ocupa el hueco del valor vacío en el
 * control; al hablar con la API se traduce a `""` con `ningunaParam`.
 *
 * Es distinto de `MARCA_TODAS`/`RED_TODAS`: aquéllos significan "no filtrar"
 * (todas), mientras que `NINGUNA` significa "el campo queda sin valor".
 */
export const NINGUNA = "__ninguna__";

/**
 * Traduce el valor de un control opcional al parámetro de la API: el centinela
 * `NINGUNA` se vuelve `""` (campo sin valor).
 */
export function ningunaParam(valor: string): string {
  return valor === NINGUNA ? "" : valor;
}

/**
 * Traduce un valor de la API (`""`/`null` = sin valor) al valor del control,
 * usando `NINGUNA` para representar "sin marca / sin red / sin fijar".
 */
export function desdeNinguna(valor: string | null | undefined): string {
  return valor ? valor : NINGUNA;
}

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

/**
 * Traduce un id de marca del catálogo de Métricas (forma `id_metricas`, con
 * guion_bajo, p. ej. `claro_sports`) al `id` CANÓNICO que usa el resto de la
 * consola (slug-guion, p. ej. `claro-sports`).
 *
 * La frontera de Métricas habla en `id_metricas`, mientras que Generar copy y
 * Publicaciones trabajan con el id canónico (ver `keni_consola/marcas.py`). La
 * única diferencia entre ambas formas es el separador, así que basta cambiar
 * `_` por `-`. La página destino valida el id contra su propio catálogo: si no
 * existe, su selector simplemente no preselecciona nada (sin inventar datos).
 */
export function marcaCanonicaDesdeMetricas(idMetricas: string): string {
  return idMetricas.replace(/_/g, "-");
}

/**
 * Traducción inversa de `marcaCanonicaDesdeMetricas`: del `id` canónico
 * (slug-guion) al `id_metricas` (guion_bajo) que usa el catálogo de Métricas.
 * Útil para enlazar desde Publicaciones (id canónico) hacia Métricas.
 */
export function marcaMetricasDesdeCanonica(idCanonico: string): string {
  return idCanonico.replace(/-/g, "_");
}
