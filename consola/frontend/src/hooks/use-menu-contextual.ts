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
      // Click derecho (contextmenu): monta el menú EN el cursor, no debajo del item.
      // No filtres por `detail`: el evento `contextmenu` real llega con `detail === 0`
      // en varios navegadores (Chrome), así que gatear en él hacía caer al anclado
      // bajo el disparador. La rama sin `ancla` solo la dispara el click derecho.
      const evMouse = e as React.MouseEvent;
      if (e.type === "contextmenu" && typeof evMouse.clientX === "number") {
        setPos({ x: evMouse.clientX, y: evMouse.clientY });
        return;
      }
      // Activación por teclado (Shift+F10 / tecla Menú) sin ancla: ancla al disparador.
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
