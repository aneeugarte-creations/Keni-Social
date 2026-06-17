/**
 * Gating de navegación por MARCA (multitenant).
 *
 * La app es multitenant por marca, pero no de forma restrictiva: sirve para SEPARAR
 * CONTEXTOS entre equipos que trabajan juntos. Algunas superficies podrían tener sentido
 * solo para una marca concreta y se ocultarían del nav (y se bloquearía su ruta) cuando la
 * marca activa es otra. La marca activa la fija el selector global de la barra superior
 * (`useMarcaActiva`): es el id canónico, o `null` para la vista agregada "Todas" (admin).
 *
 * El mecanismo se usa en el Sidebar y el SubnavHub para superficies que aplican solo a una
 * marca concreta.
 */

/**
 * Rutas restringidas a una marca concreta: `{ruta, marca}`. Una ruta restringida solo es
 * visible cuando la marca activa coincide, o en "Todas" (`marcaActiva === null`, admin).
 * Añadir una entrada aquí basta para ocultar su nav/pestaña y bloquear su ruta para el
 * resto de marcas.
 */
const RUTAS_RESTRINGIDAS_POR_MARCA: ReadonlyArray<{ ruta: string; marca: string }> = [];

/**
 * Rutas del PANEL DE NOTICIAS, visibles solo para marcas de noticias (`tipo='noticias'`). Las
 * marcas de contenido propio (`tipo='propio'`) se saltan la investigación, así que estas rutas
 * se ocultan de su nav. `exacta` = solo la ruta literal (sin subrutas): el índice del hub de
 * Investigación ("Noticias") se oculta sin tocar a sus hermanas (Publicaciones, Fuentes).
 */
const RUTAS_SOLO_NOTICIAS: ReadonlyArray<{ ruta: string; exacta?: boolean }> = [
  { ruta: "/datos/investigacion", exacta: true }, // pestaña "Noticias" del hub Investigación
  { ruta: "/maquina/investigacion" }, // cockpit de Investigación (la Mesa)
];

/**
 * ¿Es `ruta` visible para la marca activa? `true` salvo que (a) la ruta esté restringida a una
 * marca y la activa sea otra concreta, o (b) sea una ruta del panel de Noticias y la marca
 * activa NO sea de noticias (`esNoticias=false`). "Todas" (admin, `marcaActiva===null`) ve todo.
 * Lo usan el Sidebar (para ocultar la entrada) y el SubnavHub (para ocultar la pestaña).
 */
export function rutaVisibleParaMarca(
  ruta: string,
  marcaActiva: string | null,
  esNoticias = true,
): boolean {
  if (marcaActiva === null) return true; // "Todas" (admin): lo ve todo.
  const restriccion = RUTAS_RESTRINGIDAS_POR_MARCA.find(
    (r) => ruta === r.ruta || ruta.startsWith(`${r.ruta}/`),
  );
  if (restriccion && restriccion.marca !== marcaActiva) return false;
  if (!esNoticias) {
    const soloNoticias = RUTAS_SOLO_NOTICIAS.find((r) =>
      r.exacta ? ruta === r.ruta : ruta === r.ruta || ruta.startsWith(`${r.ruta}/`),
    );
    if (soloNoticias) return false;
  }
  return true;
}
