import * as React from "react";

/**
 * Suscripción reactiva a una media query (`window.matchMedia`).
 *
 * Para decisiones de layout que el CSS no puede tomar solo: p. ej. elegir el DESTINO de un
 * portal según el viewport (las acciones de página van a la topbar en escritorio y a su
 * propia fila bajo el header en móvil). En entornos sin `matchMedia` (jsdom de los tests)
 * devuelve `true` —comportamiento de ESCRITORIO— para no cambiar lo que los tests ya ven.
 */
export function useMediaQuery(consulta: string): boolean {
  const [coincide, setCoincide] = React.useState<boolean>(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
    return window.matchMedia(consulta).matches;
  });

  React.useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(consulta);
    const alCambiar = () => setCoincide(mq.matches);
    alCambiar();
    mq.addEventListener("change", alCambiar);
    return () => mq.removeEventListener("change", alCambiar);
  }, [consulta]);

  return coincide;
}

/** `true` en viewports de escritorio (breakpoint `md` de Tailwind, 768px). */
export function useEsEscritorio(): boolean {
  return useMediaQuery("(min-width: 768px)");
}
