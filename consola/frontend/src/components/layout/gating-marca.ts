/**
 * Gating de navegación por MARCA (multitenant).
 *
 * La app es multitenant por marca, pero no de forma restrictiva: sirve para SEPARAR
 * CONTEXTOS entre equipos que trabajan juntos. Algunas superficies podrían tener sentido
 * solo para una marca concreta y se ocultarían del nav (y se bloquearía su ruta) cuando la
 * marca activa es otra. La marca activa la fija el selector global de la barra superior
 * (`useMarcaActiva`): es el id canónico, o `null` para la vista agregada "Todas" (admin).
 *
 * HOY NINGUNA ruta está restringida por marca: Turnos (rota de cobertura) pasó a ser POR
 * MARCA —cada marca ve su rota vía `rota_eventos.marca`; "Todas" agrega— y el Carril Rápido
 * de Breaking se retiró junto con la página de Revisión. El mecanismo se conserva (lo usan
 * el Sidebar y el SubnavHub) para futuras superficies que solo apliquen a una marca concreta.
 */

/**
 * Rutas restringidas a una marca concreta: `{ruta, marca}`. Una ruta restringida solo es
 * visible cuando la marca activa coincide, o en "Todas" (`marcaActiva === null`, admin).
 * Hoy está VACÍA (ninguna superficie es mono-marca); añadir una entrada aquí basta para
 * ocultar su nav/pestaña y bloquear su ruta para el resto de marcas.
 */
const RUTAS_RESTRINGIDAS_POR_MARCA: ReadonlyArray<{ ruta: string; marca: string }> = [];

/**
 * ¿Es `ruta` visible para la `marcaActiva`? `true` salvo que la ruta esté restringida a una
 * marca y la marca activa sea otra marca concreta (distinta de la suya y de "Todas"). Lo usan
 * el Sidebar (para ocultar la entrada) y el SubnavHub (para ocultar la pestaña).
 */
export function rutaVisibleParaMarca(ruta: string, marcaActiva: string | null): boolean {
  if (marcaActiva === null) return true; // "Todas" (admin): lo ve todo.
  const restriccion = RUTAS_RESTRINGIDAS_POR_MARCA.find(
    (r) => ruta === r.ruta || ruta.startsWith(`${r.ruta}/`),
  );
  return !restriccion || restriccion.marca === marcaActiva;
}
