/**
 * Tooltip ligero (CSS puro, sin dependencias).
 *
 * Pensado para botones de solo icono: envuelve el disparador y muestra una
 * etiqueta al pasar el ratón o al enfocar con teclado. Para accesibilidad se
 * aplica también `aria-label` al hijo (sin pisar uno existente).
 *
 * No usamos Radix Tooltip para no añadir otra dependencia pesada; este patrón
 * cubre el caso (etiqueta corta sobre un icono) con foco/hover y modo oscuro.
 *
 * El rótulo se pinta en un PORTAL sobre `<body>` con `position: fixed`, así NO
 * lo recortan los contenedores con overflow (rail del sidebar, barras con
 * scroll del lienzo…) ni queda atrapado en contextos de apilamiento. La
 * posición se calcula respecto al ancla en el momento de mostrarse.
 */
import * as React from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

type Lado = "top" | "bottom" | "left" | "right";

// Desplazamiento del rótulo respecto al ancla, por lado.
const TRANSFORM: Record<Lado, string> = {
  top: "translate(-50%, -100%)",
  bottom: "translate(-50%, 0)",
  left: "translate(-100%, -50%)",
  right: "translate(0, -50%)",
};

// ── Temporización ÚNICA de todos los tooltips (patrón Canva / Radix 500/150) ──────────────────
// Reposar ~500 ms muestra el rótulo; al saltar entre disparadores hermanos (si el anterior se
// cerró hace <150 ms) el siguiente aparece al instante, sin re-esperar. El foco con teclado
// muestra SIEMPRE al instante.
const RETARDO_MS = 500;
const VENTANA_SALTO_MS = 150;
let ultimoCierre = 0;

/** Visibilidad temporizada compartida: `mostrar(inmediato?)` arma el retardo, `ocultar` cierra. */
function useTemporizadorTooltip() {
  const [visible, setVisible] = React.useState(false);
  const timerRef = React.useRef<number | null>(null);

  // Limpia el temporizador pendiente al desmontar (evita setState sobre componente muerto).
  React.useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  const mostrar = React.useCallback((inmediato = false) => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    const espera = inmediato || Date.now() - ultimoCierre < VENTANA_SALTO_MS ? 0 : RETARDO_MS;
    timerRef.current = window.setTimeout(() => setVisible(true), espera);
  }, []);

  const ocultar = React.useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    setVisible((v) => {
      if (v) ultimoCierre = Date.now();
      return false;
    });
  }, []);

  return { visible, mostrar, ocultar };
}

export interface TooltipProps {
  /** Texto a mostrar. Si está vacío, se renderiza el hijo sin envoltorio. */
  label: string;
  /** Lado donde aparece (por defecto arriba). */
  side?: Lado;
  children: React.ReactElement;
  className?: string;
}

/**
 * Envuelve un único elemento (normalmente un Button de icono) y le añade un
 * tooltip accesible. El hijo recibe `aria-label` si no tiene uno. El rótulo se
 * pinta en un portal sobre `<body>` (fixed), inmune a overflow y a contextos de
 * apilamiento. Temporización: ~500 ms de reposo, instantáneo entre hermanos y
 * al enfocar con teclado.
 */
export function Tooltip({ label, side = "top", children, className }: TooltipProps) {
  const { visible, mostrar, ocultar } = useTemporizadorTooltip();
  const anclaRef = React.useRef<HTMLSpanElement | null>(null);

  if (!label) return children;

  const hijo = React.isValidElement<{ "aria-label"?: string }>(children)
    ? React.cloneElement(children, {
        "aria-label": children.props["aria-label"] ?? label,
      })
    : children;

  // La posición se calcula EN el render visible (el ancla ya está montada y el rect es el actual).
  const calcular = (): { x: number; y: number } | null => {
    const el = anclaRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (side === "bottom") return { x: r.left + r.width / 2, y: r.bottom + 6 };
    if (side === "left") return { x: r.left - 6, y: r.top + r.height / 2 };
    if (side === "right") return { x: r.right + 6, y: r.top + r.height / 2 };
    return { x: r.left + r.width / 2, y: r.top - 6 };
  };
  const pos = visible ? calcular() : null;

  return (
    <span
      ref={anclaRef}
      className={cn("inline-flex", className)}
      onMouseEnter={() => mostrar()}
      onMouseLeave={ocultar}
      onFocus={() => mostrar(true)}
      onBlur={ocultar}
      // Al pulsar, el rótulo estorba (la acción ya se está ejecutando): se oculta.
      onMouseDown={ocultar}
      // WCAG 1.4.13: descartable con Escape sin mover el foco; sin stopPropagation (el Escape
      // de diálogos sigue funcionando).
      onKeyDown={(e) => {
        if (e.key === "Escape") ocultar();
      }}
    >
      {hijo}
      {pos &&
        createPortal(
          // `aria-hidden`: el nombre accesible ya viaja por el aria-label clonado al hijo.
          <span
            aria-hidden="true"
            style={{ left: pos.x, top: pos.y, transform: TRANSFORM[side] }}
            className="pointer-events-none fixed z-[100] whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 text-xs font-medium text-popover-foreground shadow-md"
          >
            {label}
          </span>,
          document.body,
        )}
    </span>
  );
}
