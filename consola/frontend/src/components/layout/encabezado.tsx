import * as React from "react";
import { createPortal } from "react-dom";

import type { LucideIcon } from "lucide-react";

/**
 * Cabecera de sección UNIFICADA (misma altura, ancho y posición en todas las páginas).
 *
 * Regla de diseño: una sola barra superior por página, con el mismo formato.
 *   - Hub (2+ pestañas) → la barra son las PESTAÑAS (las pinta `EncabezadoSeccion`). Sin título.
 *   - Página plana → la barra es UN título con el MISMO formato que una pestaña activa
 *     (mismo tamaño, icono y subrayado). Lo aporta la página vía `<TituloPagina/>`.
 * En ambos casos las ACCIONES (un menú "⋯" minimalista, o controles sueltos) van a la
 * DERECHA de esa misma barra, vía `<AccionesPagina/>`. Sin subtítulos.
 *
 * Mecánica: el `AppShell` posee los dos "huecos" (slots) de la barra —inicio y acciones—
 * y los expone por contexto. Las páginas portalizan su título/acciones a esos huecos, de
 * modo que SIEMPRE caen en la misma barra y quedan alineados, sin que cada página repita
 * el layout del encabezado.
 */
export interface EncabezadoCtx {
  /** Hueco izquierdo de la barra (título de página plana). */
  slotInicio: HTMLElement | null;
  /** Hueco derecho de la barra (acciones / menú "⋯"). */
  slotAcciones: HTMLElement | null;
  /**
   * Hueco del FLANCO DERECHO de la barra, junto al contexto de marca (guardado/exportar del
   * editor). Solo lo monta el AppShell en las rutas del editor (donde `slotAcciones` pasa a ser
   * el carril CENTRADO); opcional para no romper a quien construya el ctx a mano (tests):
   * `AccionesPaginaFin` cae a `slotAcciones` si falta.
   */
  slotAccionesFin?: HTMLElement | null;
  /** Marca que hay un título de página montado (para que la barra se pinte y tome borde). */
  registrarTitulo: () => () => void;
}

const EncabezadoContext = React.createContext<EncabezadoCtx | null>(null);

export function ProveedorEncabezado({
  value,
  children,
}: {
  value: EncabezadoCtx;
  children: React.ReactNode;
}) {
  return <EncabezadoContext.Provider value={value}>{children}</EncabezadoContext.Provider>;
}

function useEncabezado(): EncabezadoCtx | null {
  return React.useContext(EncabezadoContext);
}

/**
 * Título de una página PLANA (sin pestañas). Se portaliza al hueco izquierdo de la barra
 * de cabecera con el MISMO formato que el trigger del dropdown de sección: icono + texto
 * `text-sm font-medium`. Así una página con título y un hub con dropdown arrancan idénticos.
 */
export function TituloPagina({ titulo, icono: Icono }: { titulo: string; icono?: LucideIcon }) {
  const ctx = useEncabezado();
  React.useEffect(() => ctx?.registrarTitulo(), [ctx]);
  const elemento = (
    // `min-w-0` en el contenedor flex: sin él, el span se niega a encoger por debajo de su
    // contenido y el `truncate` del texto nunca actúa (en móvil el control de marca de la
    // topbar acababa pisando el título).
    <span className="flex min-w-0 items-center gap-2 px-2 py-2 text-sm font-medium text-foreground">
      {Icono && <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />}
      <span className="truncate">{titulo}</span>
    </span>
  );
  // Con barra disponible, portaliza al hueco. Sin proveedor (p. ej. tests que montan la
  // página suelta, sin AppShell) cae a render inline para no perder el título. Con proveedor
  // pero hueco aún sin montar (un frame), no pinta nada.
  if (ctx?.slotInicio) return createPortal(elemento, ctx.slotInicio);
  if (!ctx) return elemento;
  return null;
}

/**
 * Acciones de página: se portalizan al hueco derecho de la barra de cabecera, alineadas a
 * la derecha de las pestañas o del título. Mete dentro un `<MenuAcciones/>` (menú "⋯") para
 * comandos, o controles sueltos cuando deban verse siempre.
 */
export function AccionesPagina({ children }: { children: React.ReactNode }) {
  const ctx = useEncabezado();
  if (ctx?.slotAcciones) return createPortal(children, ctx.slotAcciones);
  // Sin proveedor (tests sueltos): render inline. Con proveedor pero hueco sin montar: nada.
  if (!ctx) return <>{children}</>;
  return null;
}

/**
 * Acciones del FLANCO DERECHO de la barra (guardado/exportar del editor): se portalizan al
 * hueco junto al contexto de marca. Donde ese hueco no existe (páginas sin carril centrado,
 * o en móvil, donde el AppShell apunta ambos huecos a la fila bajo el header) cae al hueco
 * de acciones normal, así el contenido nunca se pierde.
 */
export function AccionesPaginaFin({ children }: { children: React.ReactNode }) {
  const ctx = useEncabezado();
  const destino = ctx?.slotAccionesFin ?? ctx?.slotAcciones ?? null;
  if (destino) return createPortal(children, destino);
  // Sin proveedor (tests sueltos): render inline. Con proveedor pero hueco sin montar: nada.
  if (!ctx) return <>{children}</>;
  return null;
}
