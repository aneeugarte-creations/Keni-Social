import * as React from "react";
import { createPortal } from "react-dom";
import { MoreVertical } from "lucide-react";

import { cn } from "@/lib/utils";
import { useMenuContextual } from "@/hooks/useMenuContextual";
import {
  MenuFlotante,
  type EntradaMenuContextual,
} from "@/components/comunes/MenuContextual";

type ComoFila = "tr" | "div" | "li";

interface FilaConAccionesProps {
  /**
   * Acción primaria (click izquierdo / Enter / Espacio sobre el cuerpo de la fila).
   * Si se omite, la fila no es "click-primario" (no cursor pointer ni role button).
   */
  onPrimaria?: () => void;
  /**
   * Acciones secundarias: alimentan a la vez el menú contextual (click derecho),
   * la apertura por teclado (Shift+F10 / tecla Menú) y el kebab. Fuente única.
   */
  acciones: EntradaMenuContextual[];
  /** Etiqueta accesible del menú (aria-label). */
  etiquetaAcciones?: string;
  /** Elemento host: `tr` para tablas, `div`/`li` para tarjetas/listas. */
  como?: ComoFila;
  /**
   * Visibilidad del kebab "⋮". `hover` (default, desktop) lo muestra al pasar el ratón
   * o enfocar; `siempre` (recomendado en táctil) lo deja fijo; `nunca` lo oculta y deja
   * las acciones solo en click derecho/teclado.
   */
  kebab?: "hover" | "siempre" | "nunca";
  className?: string;
  /** Clase aplicada a la celda/contenedor del kebab. */
  claseKebab?: string;
  /** Etiqueta accesible del botón kebab. */
  etiquetaKebab?: string;
  children: React.ReactNode;
}

/**
 * Fila/tarjeta con modelo de interacción "item-first": la acción primaria se dispara
 * con click izquierdo sobre el cuerpo (o Enter/Espacio), y las secundarias viven en un
 * único menú abierto por click derecho, por teclado (Shift+F10 / tecla Menú) o por el
 * kebab "⋮". Sustituye a las filas con hilera de botones-icono.
 *
 * Los controles interactivos internos (botones, enlaces, inputs) no disparan la acción
 * primaria: se detectan con `closest` y se ignoran. Usa `data-no-primaria` para excluir
 * cualquier otro elemento.
 */
export function FilaConAcciones({
  onPrimaria,
  acciones,
  etiquetaAcciones = "Acciones",
  como = "div",
  kebab = "hover",
  className,
  claseKebab,
  etiquetaKebab = "Más acciones",
  children,
}: FilaConAccionesProps) {
  const menu = useMenuContextual();
  const kebabRef = React.useRef<HTMLButtonElement>(null);
  const tieneAcciones = acciones.length > 0;
  const esClicable = typeof onPrimaria === "function";

  function alClick(e: React.MouseEvent) {
    if (!esClicable) return;
    // Ignora clicks originados en controles internos (incluido el kebab) o marcados.
    const objetivo = e.target as HTMLElement;
    if (objetivo.closest("button, a, input, select, textarea, label, [data-no-primaria]"))
      return;
    onPrimaria!();
  }

  function alTeclear(e: React.KeyboardEvent) {
    if (esClicable && (e.key === "Enter" || e.key === " ")) {
      // Solo si el foco está en la propia fila, no en un control interno.
      if (e.target === e.currentTarget) {
        e.preventDefault();
        onPrimaria!();
        return;
      }
    }
    // Shift+F10 o tecla Menú abren las acciones secundarias.
    if (tieneAcciones && ((e.shiftKey && e.key === "F10") || e.key === "ContextMenu")) {
      menu.abrirEn(e, e.currentTarget as HTMLElement);
    }
  }

  const propsHost = {
    className: cn(
      "group",
      esClicable && "cursor-pointer",
      className,
    ),
    onClick: esClicable ? alClick : undefined,
    onContextMenu: tieneAcciones ? (e: React.MouseEvent) => menu.abrirEn(e) : undefined,
    onKeyDown: esClicable || tieneAcciones ? alTeclear : undefined,
    tabIndex: esClicable ? 0 : undefined,
    role: esClicable ? "button" : undefined,
  };

  const botonKebab =
    tieneAcciones && kebab !== "nunca" ? (
      <button
        ref={kebabRef}
        type="button"
        aria-label={etiquetaKebab}
        aria-haspopup="menu"
        title={`${etiquetaKebab} (click derecho)`}
        onClick={(e) => {
          e.stopPropagation();
          menu.abrirEn(e, kebabRef.current);
        }}
        className={cn(
          "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground",
          "transition-colors hover:bg-accent hover:text-foreground focus-visible:bg-accent",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          kebab === "hover" &&
            "opacity-0 group-hover:opacity-100 focus-visible:opacity-100 focus-within:opacity-100",
        )}
      >
        <MoreVertical className="h-4 w-4" />
      </button>
    ) : null;

  const portal = menu.pos
    ? createPortal(
        <MenuFlotante
          pos={menu.pos}
          items={acciones}
          etiqueta={etiquetaAcciones}
          onClose={menu.cerrar}
        />,
        document.body,
      )
    : null;

  if (como === "tr") {
    return (
      <tr {...propsHost}>
        {children}
        {kebab !== "nunca" && (
          <td className={cn("w-10 text-right align-middle", claseKebab)}>{botonKebab}</td>
        )}
        {portal}
      </tr>
    );
  }

  const Host = como === "li" ? "li" : "div";
  return (
    <Host {...propsHost} className={cn("relative", propsHost.className)}>
      {children}
      {botonKebab && (
        <span className={cn("absolute right-2 top-2", claseKebab)}>{botonKebab}</span>
      )}
      {portal}
    </Host>
  );
}
