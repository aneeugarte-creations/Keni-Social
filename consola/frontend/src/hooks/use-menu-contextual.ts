import * as React from "react";

import {
  origenBajoDisparador,
  type PosicionMenu,
} from "@/components/comunes/menuPos";

/**
 * Estado mínimo para abrir un `MenuFlotante` desde cualquier disparador. Si se pasa un
 * `ancla` (un botón kebab), el menú se abre como desplegable anclado bajo él y alineado
 * para no salirse de pantalla. Si no, se usa la coordenada del cursor (click derecho) o,
 * en activación por teclado sin coordenadas, se ancla al propio disparador.
 */
export function useMenuContextual() {
  const [pos, setPos] = React.useState<PosicionMenu | null>(null);

  const abrirEn = React.useCallback(
    (e: React.MouseEvent | React.KeyboardEvent, ancla?: HTMLElement | null) => {
      e.preventDefault();
      e.stopPropagation();
      // Kebab/botón disparador conocido: desplegable anclado y alineado al borde.
      if (ancla) {
        setPos(origenBajoDisparador(ancla.getBoundingClientRect()));
        return;
      }
      const evMouse = e as React.MouseEvent;
      const tieneCoords =
        typeof evMouse.clientX === "number" &&
        (evMouse.clientX > 0 || evMouse.clientY > 0) &&
        // detail 0 = activación por teclado sobre un botón; ignora sus coords (0,0).
        (e.nativeEvent as MouseEvent).detail !== 0;
      if (tieneCoords) {
        setPos({ x: evMouse.clientX, y: evMouse.clientY });
        return;
      }
      const el = e.currentTarget as HTMLElement;
      setPos(origenBajoDisparador(el.getBoundingClientRect()));
    },
    [],
  );

  // Apertura directa en una coordenada (sin evento React): la usa el long-press táctil,
  // que tiene las coordenadas del toque pero no un `MouseEvent`/`KeyboardEvent`.
  const abrirEnPunto = React.useCallback((x: number, y: number) => setPos({ x, y }), []);

  const cerrar = React.useCallback(() => setPos(null), []);

  return { pos, abierto: pos !== null, abrirEn, abrirEnPunto, cerrar };
}
