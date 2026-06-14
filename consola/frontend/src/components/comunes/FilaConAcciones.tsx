import * as React from "react";
import { createPortal } from "react-dom";
import { MoreVertical } from "lucide-react";

import { cn } from "@/lib/utils";
import { useMenuContextual } from "@/hooks/use-menu-contextual";
import {
  MenuFlotante,
  type EntradaMenuContextual,
  type ItemMenuContextual,
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
  /**
   * Realce de tarjeta: en hover/foco el borde vira a naranja de marca (señal sutil de que
   * la tarjeta es accionable). Pensado para hosts `div`/`li` con aspecto de tarjeta; no
   * aplica a filas de tabla (`tr`). Es la pista de descubribilidad cuando el kebab está oculto.
   */
  realce?: boolean;
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
  realce = false,
  className,
  claseKebab,
  etiquetaKebab = "Más acciones",
  children,
}: FilaConAccionesProps) {
  const menu = useMenuContextual();
  const kebabRef = React.useRef<HTMLButtonElement>(null);
  // Long-press táctil: abre el menú secundario tras mantener pulsado (equivale al click
  // derecho del ratón). Cancela en scroll/levantar; suprime el click "fantasma" posterior.
  const tempLargo = React.useRef<number | null>(null);
  const suprimirClick = React.useRef(false);
  const tieneAcciones = acciones.length > 0;
  const esClicable = typeof onPrimaria === "function";

  // Si solo hay UNA acción, mostrarla como botón-icono directo en vez de un kebab que
  // abre un menú de un solo item (sobreingeniería). El menú solo aparece con 2+ acciones.
  // EXCEPCIÓN: con `kebab="nunca"` no hay botón visible, así que incluso una sola acción
  // DEBE enrutarse por el menú (click derecho / long-press / teclado) o sería inalcanzable.
  const itemsReales = acciones.filter(
    (a): a is ItemMenuContextual => !("separador" in a),
  );
  const accionUnica =
    kebab !== "nunca" && itemsReales.length === 1 ? itemsReales[0] : null;
  const hayMenu = tieneAcciones && !accionUnica;

  function alClick(e: React.MouseEvent) {
    if (!esClicable) return;
    // Tras un long-press que abrió el menú, ignora el click "fantasma" que dispara el toque.
    if (suprimirClick.current) {
      suprimirClick.current = false;
      return;
    }
    // Ignora clicks originados en controles internos (incluido el kebab) o marcados.
    const objetivo = e.target as HTMLElement;
    if (objetivo.closest("button, a, input, select, textarea, label, [data-no-primaria]"))
      return;
    onPrimaria!();
  }

  function cancelarLargo() {
    if (tempLargo.current !== null) {
      window.clearTimeout(tempLargo.current);
      tempLargo.current = null;
    }
  }

  function alTocarInicio(e: React.TouchEvent) {
    if (!hayMenu) return;
    // No abras por long-press si el toque empieza en un control interno.
    if ((e.target as HTMLElement).closest("button, a, input, select, textarea, label, [data-no-primaria]"))
      return;
    const t = e.touches[0];
    if (!t) return;
    const x = t.clientX;
    const y = t.clientY;
    cancelarLargo();
    tempLargo.current = window.setTimeout(() => {
      suprimirClick.current = true;
      menu.abrirEnPunto(x, y);
    }, 500);
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
    // Shift+F10 o tecla Menú abren las acciones secundarias (solo si hay menú).
    if (hayMenu && ((e.shiftKey && e.key === "F10") || e.key === "ContextMenu")) {
      menu.abrirEn(e, e.currentTarget as HTMLElement);
    }
  }

  // Realce naranja de marca al hover/foco: pista de descubribilidad cuando no hay kebab.
  // Solo en hosts tipo tarjeta (no `tr`) y cuando hay algo que accionar.
  const usaRealce = realce && como !== "tr" && (esClicable || hayMenu);

  const propsHost = {
    className: cn(
      "group",
      esClicable && "cursor-pointer select-none [-webkit-touch-callout:none]",
      usaRealce &&
        "transition-colors hover:border-keni-300 focus-visible:border-keni-300 focus-visible:outline-none",
      className,
    ),
    onClick: esClicable ? alClick : undefined,
    // El click derecho abre el menú solo cuando hay 2+ acciones; con una sola, el
    // botón-icono directo ya la ofrece.
    onContextMenu: hayMenu ? (e: React.MouseEvent) => menu.abrirEn(e) : undefined,
    onKeyDown: esClicable || hayMenu ? alTeclear : undefined,
    // Long-press táctil → menú secundario (equivalente al click derecho).
    onTouchStart: hayMenu ? alTocarInicio : undefined,
    onTouchEnd: hayMenu ? cancelarLargo : undefined,
    onTouchMove: hayMenu ? cancelarLargo : undefined,
    onTouchCancel: hayMenu ? cancelarLargo : undefined,
    tabIndex: esClicable ? 0 : undefined,
    role: esClicable ? "button" : undefined,
  };

  const claseControl = cn(
    "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground",
    "transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    kebab === "hover" &&
      "opacity-0 group-hover:opacity-100 focus-visible:opacity-100 focus-within:opacity-100",
  );

  let botonKebab: React.ReactNode = null;
  if (accionUnica && kebab !== "nunca") {
    const Icono = accionUnica.icono ?? MoreVertical;
    botonKebab = (
      <button
        ref={kebabRef}
        type="button"
        aria-label={accionUnica.etiqueta}
        title={accionUnica.etiqueta}
        disabled={accionUnica.deshabilitado}
        onClick={(e) => {
          e.stopPropagation();
          accionUnica.onClick();
        }}
        className={cn(
          claseControl,
          "disabled:cursor-not-allowed disabled:opacity-50",
          accionUnica.destructivo
            ? "hover:bg-destructive/10 hover:text-destructive focus-visible:bg-destructive/10"
            : "hover:bg-accent hover:text-foreground focus-visible:bg-accent",
        )}
      >
        <Icono className="h-4 w-4" />
      </button>
    );
  } else if (hayMenu && kebab !== "nunca") {
    botonKebab = (
      <button
        ref={kebabRef}
        type="button"
        aria-label={etiquetaKebab}
        aria-haspopup="menu"
        title={etiquetaKebab}
        onClick={(e) => {
          e.stopPropagation();
          menu.abrirEn(e, kebabRef.current);
        }}
        className={cn(claseControl, "hover:bg-accent hover:text-foreground focus-visible:bg-accent")}
      >
        <MoreVertical className="h-4 w-4" />
      </button>
    );
  }

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
