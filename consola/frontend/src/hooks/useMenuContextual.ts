import * as React from "react";

import type { PosicionMenu } from "@/components/comunes/MenuContextual";

/**
 * Estado mínimo para abrir un `MenuFlotante` desde cualquier disparador (click derecho,
 * tecla de menú o un botón kebab). Centraliza el cálculo de la coordenada: usa las
 * coordenadas del ratón cuando existen y, si la apertura vino del teclado (sin
 * coordenadas), ancla el menú al elemento disparador.
 */
export function useMenuContextual() {
  const [pos, setPos] = React.useState<PosicionMenu | null>(null);

  const abrirEn = React.useCallback(
    (e: React.MouseEvent | React.KeyboardEvent, ancla?: HTMLElement | null) => {
      e.preventDefault();
      e.stopPropagation();
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
      const el = ancla ?? (e.currentTarget as HTMLElement);
      const r = el.getBoundingClientRect();
      setPos({ x: r.left, y: r.bottom + 4 });
    },
    [],
  );

  const cerrar = React.useCallback(() => setPos(null), []);

  return { pos, abierto: pos !== null, abrirEn, cerrar };
}
