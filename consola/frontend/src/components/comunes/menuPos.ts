/** Posición (px) donde abrir un menú flotante. */
export interface PosicionMenu {
  x: number;
  y: number;
}

/** Ancho estimado del menú (min-w 12rem); se corrige al medir tras montar. */
const ANCHO_MENU_ESTIMADO = 224;

/**
 * Calcula el origen (top-left) de un menú desplegable anclado bajo un disparador,
 * alineándolo a su borde derecho cuando no cabe a la derecha (evita que se salga de
 * pantalla, que era el comportamiento por defecto). Para menús de click-derecho se usa
 * la coordenada del cursor directamente.
 */
export function origenBajoDisparador(rect: DOMRect): PosicionMenu {
  const alineaDerecha = rect.left + ANCHO_MENU_ESTIMADO > window.innerWidth - 8;
  return {
    x: alineaDerecha ? rect.right - ANCHO_MENU_ESTIMADO : rect.left,
    y: rect.bottom + 4,
  };
}
