/**
 * El diálogo de cobertura del chip del Calendario es modal: Radix lo cierra ante cualquier
 * «interacción fuera» de su contenido. Pero sus acciones se portalizan a <body>, FUERA de ese
 * contenido: el menú del kebab (role="menu"), el sub-diálogo «Asignar a…»/«Editar» (role="dialog")
 * y la confirmación de borrado (role="alertdialog"). Al abrirse roban el foco y reciben clicks;
 * sin esta guarda, el diálogo padre los toma como interacción externa y se cierra, llevándose por
 * delante al hijo. Una interacción originada en cualquiera de esas capas hijas mantiene abierto el
 * padre. Vive en su propio módulo para fijarse en test: jsdom no dispara el onInteractOutside real
 * de Radix.
 */
export function interaccionEnCapaHija(target: HTMLElement | null): boolean {
  return Boolean(target?.closest('[role="menu"],[role="dialog"],[role="alertdialog"]'));
}
