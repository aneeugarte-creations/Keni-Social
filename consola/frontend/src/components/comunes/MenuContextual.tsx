import * as React from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";
import { origenBajoDisparador, type PosicionMenu } from "./menuPos";

export type { PosicionMenu } from "./menuPos";

/** Item del menú contextual. Click izquierdo dispara `onClick`. */
export interface ItemMenuContextual {
  /** Texto del item. */
  etiqueta: string;
  /** Icono lucide (opcional). */
  icono?: React.ComponentType<{ className?: string }>;
  /** Acción al hacer click. */
  onClick: () => void;
  /** Si está activo (chip a la izquierda). Útil para "Cambiar franja". */
  activo?: boolean;
  /** Si el item es destructivo (rojo). */
  destructivo?: boolean;
  /** Si el item está deshabilitado. */
  deshabilitado?: boolean;
}

/** Separador entre grupos de items. */
export interface SeparadorMenuContextual {
  separador: true;
}

export type EntradaMenuContextual = ItemMenuContextual | SeparadorMenuContextual;

function esSeparador(e: EntradaMenuContextual): e is SeparadorMenuContextual {
  return (e as SeparadorMenuContextual).separador === true;
}

/**
 * Cuerpo del menú flotante (popup) reutilizable. Se renderiza en `position: fixed`
 * en la coordenada dada, se cierra al hacer click fuera o pulsar Escape, se reubica
 * si se sale del viewport y gestiona el foco por teclado (enfoca el primer item al
 * abrir, navega con ↑/↓/Home/End). Lo consumen tanto `MenuContextual` (trigger
 * envolvente) como `FilaConAcciones` (fila clicable con kebab).
 */
export function MenuFlotante({
  pos,
  items,
  etiqueta = "Acciones",
  onClose,
}: {
  pos: PosicionMenu;
  items: EntradaMenuContextual[];
  /** Etiqueta accesible del menú (aria-label). */
  etiqueta?: string;
  onClose: () => void;
}) {
  const menuRef = React.useRef<HTMLDivElement>(null);
  const [ajustada, setAjustada] = React.useState<PosicionMenu>(pos);

  // Si cambia la coordenada de apertura, reinicia la posición ajustada.
  React.useEffect(() => {
    setAjustada(pos);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pos.x, pos.y]);

  React.useEffect(() => {
    function alPulsarFuera(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose();
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [onClose]);

  // Tras montar el menú, mídelo y desplázalo si se sale del viewport. Sin esto, un
  // trigger pegado al borde derecho deja el menú saliéndose por la derecha (o por
  // la parte de abajo si la fila está al final del scroll).
  React.useLayoutEffect(() => {
    if (!menuRef.current) return;
    const r = menuRef.current.getBoundingClientRect();
    const margen = 8;
    let { x, y } = pos;
    if (r.right > window.innerWidth - margen) {
      x = Math.max(margen, window.innerWidth - r.width - margen);
    }
    if (r.bottom > window.innerHeight - margen) {
      y = Math.max(margen, window.innerHeight - r.height - margen);
    }
    if (x !== ajustada.x || y !== ajustada.y) setAjustada({ x, y });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pos.x, pos.y]);

  // Al abrir, enfoca el primer item para que el teclado funcione sin ratón.
  React.useEffect(() => {
    const primero = menuRef.current?.querySelector<HTMLButtonElement>(
      '[role="menuitem"]:not([disabled])',
    );
    primero?.focus();
  }, []);

  function alTeclearMenu(e: React.KeyboardEvent) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Home" && e.key !== "End")
      return;
    e.preventDefault();
    const elementos = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="menuitem"]:not([disabled])',
      ) ?? [],
    );
    if (elementos.length === 0) return;
    const actual = elementos.indexOf(document.activeElement as HTMLButtonElement);
    let siguiente = 0;
    if (e.key === "Home") siguiente = 0;
    else if (e.key === "End") siguiente = elementos.length - 1;
    else if (e.key === "ArrowDown") siguiente = actual < 0 ? 0 : (actual + 1) % elementos.length;
    else siguiente = actual <= 0 ? elementos.length - 1 : actual - 1;
    elementos[siguiente]?.focus();
  }

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label={etiqueta}
      onKeyDown={alTeclearMenu}
      // `pointer-events-auto`: el menú se portaliza a <body>. Dentro de un diálogo modal de Radix,
      // el <body> queda en `pointer-events: none` (solo la capa activa recibe clicks); sin esto, los
      // ítems del kebab abierto sobre un modal (p. ej. «Asignar a…» en el calendario) no serían
      // clicables. Fuera de un modal no cambia nada (es el valor por defecto).
      className="pointer-events-auto fixed z-50 min-w-[12rem] overflow-hidden rounded-md border border-border bg-popover py-1 text-popover-foreground shadow-md"
      style={{ left: ajustada.x, top: ajustada.y }}
    >
      {items.map((entrada, i) => {
        if (esSeparador(entrada)) {
          return (
            <div key={`sep-${i}`} className="my-1 border-t border-border" aria-hidden="true" />
          );
        }
        const Icono = entrada.icono;
        return (
          <button
            key={`${entrada.etiqueta}-${i}`}
            type="button"
            role="menuitem"
            disabled={entrada.deshabilitado}
            onClick={() => {
              onClose();
              entrada.onClick();
            }}
            className={cn(
              "flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-sm transition-colors",
              "hover:bg-accent focus-visible:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-50",
              entrada.destructivo
                ? "text-destructive hover:bg-destructive/10"
                : "text-foreground",
            )}
          >
            {Icono && (
              <Icono
                className={cn(
                  "h-4 w-4 shrink-0",
                  entrada.destructivo ? "text-destructive" : "text-muted-foreground",
                )}
              />
            )}
            <span className="flex-1">{entrada.etiqueta}</span>
            {entrada.activo && <span className="text-xs text-muted-foreground">●</span>}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Menú contextual (right-click) reutilizable. El padre envuelve el área disparadora con
 * `<MenuContextual>` y pasa los items; el menú se renderiza en `position: fixed` en la
 * coordenada del click, se cierra al hacer click fuera o pulsar Escape.
 *
 * Para filas/tarjetas con acción primaria + secundarias, prefiere `FilaConAcciones`,
 * que añade click-izquierdo primario y un kebab accesible sobre este mismo menú.
 *
 * No añade dependencias: comparte patrón con `CuentaUsuario` (avatar dropdown).
 */
export function MenuContextual({
  children,
  items,
  disparador = "contextmenu",
  etiqueta,
}: {
  children: React.ReactNode;
  items: EntradaMenuContextual[];
  /**
   * Qué evento abre el menú. `contextmenu` (default) preserva el comportamiento histórico
   * de right-click; `click` lo dispara con left-click; `ambos` acepta cualquiera de los
   * dos. Útil cuando el chip debe responder al toque primario sin botón derecho.
   */
  disparador?: "contextmenu" | "click" | "ambos";
  /** Etiqueta accesible del menú (aria-label). */
  etiqueta?: string;
}) {
  const [pos, setPos] = React.useState<PosicionMenu | null>(null);

  function alAbrir(e: React.MouseEvent) {
    e.preventDefault();
    // Click-izquierdo (botón desplegable): ancla el menú bajo el disparador y alinea su
    // borde para que no se salga de pantalla. Click-derecho: abre en el cursor.
    if (e.type === "click") {
      const disparadorEl =
        ((e.target as HTMLElement).closest("button, [role='button']") as HTMLElement | null) ??
        (e.currentTarget as HTMLElement);
      setPos(origenBajoDisparador(disparadorEl.getBoundingClientRect()));
      return;
    }
    setPos({ x: e.clientX, y: e.clientY });
  }

  const usaContextMenu = disparador === "contextmenu" || disparador === "ambos";
  const usaClick = disparador === "click" || disparador === "ambos";

  return (
    <>
      <div
        onContextMenu={usaContextMenu ? alAbrir : undefined}
        onClick={usaClick ? alAbrir : undefined}
      >
        {children}
      </div>
      {pos &&
        createPortal(
          <MenuFlotante
            pos={pos}
            items={items}
            etiqueta={etiqueta}
            onClose={() => setPos(null)}
          />,
          document.body,
        )}
    </>
  );
}
