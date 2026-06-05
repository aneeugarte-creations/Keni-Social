/**
 * Gating de navegación por MARCA (multitenant).
 *
 * La app es multitenant por marca, pero no de forma restrictiva: sirve para SEPARAR
 * CONTEXTOS entre equipos que trabajan juntos. Algunas superficies solo tienen sentido
 * para una marca concreta y se ocultan del nav (y se bloquea su ruta) cuando la marca
 * activa es otra. La marca activa la fija el selector global de la barra superior
 * (`useMarcaActiva`): es el id canónico, o `null` para la vista agregada "Todas" (admin).
 *
 * Hoy lo único restringido es la pestaña TURNOS (rota de cobertura) del hub Calendario:
 * es cosa de Claro Sports. El resto del hub —la Programación (calendario de publicaciones)—
 * es relevante para TODAS las marcas y se ve siempre.
 *
 * La pestaña EVENTOS del hub Fuentes (alta/gestión de eventos a cubrir, ola "Calendario =
 * turnos / Fuentes = eventos") NO se restringe: la LISTA de eventos es general (cualquier
 * marca puede consultarla). Lo específico de Claro Sports es la ASIGNACIÓN de cobertura,
 * que vive en Turnos (ya gateado) y a la que la página Eventos solo enlaza para Claro/Todas.
 */

/** Id canónico de Claro Sports (catálogo de marcas del backend). */
export const MARCA_CLARO_SPORTS = "claro-sports";

/**
 * Rutas que SOLO aplican a Claro Sports. Para cualquier otra marca concreta se ocultan
 * (del nav / de su pestaña) y su ruta redirige; en "Todas" (`marcaActiva === null`, vista
 * agregada de admin) sí se permiten, porque incluye a Claro Sports.
 */
const RUTAS_SOLO_CLARO_SPORTS = ["/operacion/calendario/turnos"];

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
