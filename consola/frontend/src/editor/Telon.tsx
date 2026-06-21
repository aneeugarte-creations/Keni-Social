/**
 * TELÓN: backdrop clicable accesible para los overlays caseros del editor (flyouts,
 * inspector, menús). Es focusable (`role="button"` + `tabIndex`) —visible para teclado y
 * lector de pantalla— y cierra también con Enter / Espacio / Escape. El cierre global con
 * Escape (sin foco en el telón) lo añade
 * cada overlay con `useCerrarConEscape`.
 */
import * as React from "react";

export function Telon({
  onCerrar,
  className,
  etiqueta = "Cerrar",
}: {
  onCerrar: () => void;
  className?: string;
  etiqueta?: string;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={etiqueta}
      onClick={onCerrar}
      onKeyDown={(e) => {
        if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onCerrar();
        }
      }}
      className={className}
    />
  );
}

/**
 * Cierra un overlay con Escape estando el foco en CUALQUIER parte (listener de window).
 * `activo` evita registrar el listener cuando el overlay está cerrado.
 */
export function useCerrarConEscape(activo: boolean, onCerrar: () => void): void {
  React.useEffect(() => {
    if (!activo) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCerrar();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activo, onCerrar]);
}
