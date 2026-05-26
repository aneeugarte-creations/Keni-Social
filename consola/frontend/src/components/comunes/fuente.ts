/**
 * Lógica (sin componentes) de la fuente de datos de Métricas, para que el
 * `.tsx` del badge solo exporte el componente y no rompa el fast-refresh.
 *
 * El campo `fuente` de la respuesta de métricas es OPCIONAL (el backend lo
 * añade en paralelo); estos helpers lo leen de forma defensiva.
 */

/** Centinela: nombre de la fuente de datos ficticios (de muestra). */
export const FUENTE_MUESTRA = "muestra";

/**
 * `true` solo si la fuente activa es de muestra (datos ficticios). Cualquier
 * otro nombre se considera fuente real; `undefined`/`null`/`""` → `false` (no
 * afirmamos nada cuando el dato falta).
 */
export function esFuenteMuestra(fuente: string | null | undefined): boolean {
  return fuente === FUENTE_MUESTRA;
}
