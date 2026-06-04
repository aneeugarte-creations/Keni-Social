/**
 * Gating de navegación por MARCA (multitenant).
 *
 * La app es multitenant por marca, pero no de forma restrictiva: sirve para SEPARAR
 * CONTEXTOS entre equipos que trabajan juntos. Algunas superficies solo tienen sentido
 * para una marca concreta y se ocultan del nav (y se bloquea su ruta) cuando la marca
 * activa es otra. La marca activa la fija el selector global de la barra superior
 * (`useMarcaActiva`): es el id canónico, o `null` para la vista agregada "Todas" (admin).
 */

/** Id canónico de Claro Sports (catálogo de marcas del backend). */
export const MARCA_CLARO_SPORTS = "claro-sports";

/**
 * Prefijos de ruta (hubs) que SOLO aplican a Claro Sports. Para cualquier otra marca
 * específica se ocultan del sidebar y su ruta redirige; en "Todas" (`marcaActiva === null`,
 * vista agregada de admin) sí se permiten, porque incluye a Claro Sports.
 */
const RUTAS_SOLO_CLARO_SPORTS = ["/operacion/calendario"];

/**
 * ¿Es `ruta` visible para la `marcaActiva`? `true` salvo que la ruta esté restringida a
 * Claro Sports y la marca activa sea otra marca concreta (distinta de Claro Sports y de
 * "Todas"). Lo usan el Sidebar (para ocultar la entrada) y el guard de ruta (para redirigir).
 */
export function rutaVisibleParaMarca(ruta: string, marcaActiva: string | null): boolean {
  const restringidaAClaroSports = RUTAS_SOLO_CLARO_SPORTS.some(
    (r) => ruta === r || ruta.startsWith(`${r}/`),
  );
  if (!restringidaAClaroSports) return true;
  // "Todas" (null) y Claro Sports sí; cualquier otra marca, no.
  return marcaActiva === null || marcaActiva === MARCA_CLARO_SPORTS;
}
