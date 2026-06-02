import * as React from "react";

/**
 * Hook que evalúa una media query CSS y se re-renderiza cuando cambia (resize,
 * rotación). Útil para variar comportamiento (no solo estilos) según el viewport:
 * p. ej. abrir un diálogo a pantalla completa en móvil. Devuelve `false` en SSR /
 * sin `matchMedia` (degradación segura: asume escritorio).
 *
 * Atajo común: `useEsMovil()` para el breakpoint `md` de Tailwind (< 768px).
 */
export function useMediaQuery(query: string): boolean {
  const obtener = React.useCallback(
    () => (typeof window !== "undefined" && window.matchMedia
      ? window.matchMedia(query).matches
      : false),
    [query],
  );
  const [coincide, setCoincide] = React.useState(obtener);

  React.useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(query);
    const alCambiar = () => setCoincide(mq.matches);
    // Sincroniza por si cambió entre el render inicial y el efecto.
    alCambiar();
    mq.addEventListener("change", alCambiar);
    return () => mq.removeEventListener("change", alCambiar);
  }, [query]);

  return coincide;
}

/** `true` en viewport móvil (< breakpoint `md` de Tailwind, 768px). */
export function useEsMovil(): boolean {
  return useMediaQuery("(max-width: 767px)");
}
