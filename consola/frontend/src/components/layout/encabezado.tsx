import { ArrowLeft } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import {
  TiraPestanasSeccion,
  type PestanaSeccion,
} from "@/components/layout/pestanas-seccion";

import type { LucideIcon } from "lucide-react";

export type { PestanaSeccion } from "@/components/layout/pestanas-seccion";

/**
 * Cabecera de sección UNIFICADA (misma altura, ancho y posición en todas las páginas).
 *
 * Regla de diseño: una sola barra superior por página, con el mismo formato.
 *   - Hub por RUTA (2+ pestañas) → la barra son las PESTAÑAS (las pinta `EncabezadoSeccion`).
 *   - Sección por ESTADO (una página plana cuyas sub-vistas conmutan por `?param=`/`useState`) →
 *     la barra son sus pestañas, vía `<PestanasSeccion/>` (mismo formato que un hub por ruta).
 *   - Página plana sin sub-vistas → la barra es UN título con el MISMO formato que una pestaña
 *     activa (mismo tamaño, icono y subrayado). Lo aporta la página vía `<TituloPagina/>`.
 * Los tres son EXCLUYENTES: una página usa uno. Pestañas (ruta o estado) y título caen en el
 * mismo hueco izquierdo de la barra.
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
 *
 * SUBPÁGINA de detalle: con `onAtras` pinta una flecha «←» (volver) ANTES del icono+título,
 * dentro del mismo hueco. Así una página de detalle lleva su «atrás» en la barra superior
 * (el header persistente), no como una fila suelta en el cuerpo. Sin `onAtras` solo pinta
 * icono + título. La PRESENTACIÓN del «atrás» vive aquí; la LÓGICA de a dónde se vuelve la
 * pone la página en el callback.
 */
export function TituloPagina({
  titulo,
  icono: Icono,
  onAtras,
}: {
  titulo: string;
  icono?: LucideIcon;
  /** Si está presente, pinta una flecha «←» (volver) antes del icono+título. */
  onAtras?: () => void;
}) {
  const ctx = useEncabezado();
  React.useEffect(() => ctx?.registrarTitulo(), [ctx]);
  const elemento = (
    // `min-w-0` en el contenedor flex: sin él, el span se niega a encoger por debajo de su
    // contenido y el `truncate` del texto nunca actúa (en móvil el control de marca de la
    // topbar acababa pisando el título).
    <span className="flex h-8 min-w-0 items-center gap-2 px-2 text-sm font-medium text-foreground">
      {onAtras && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          // El cromo de la barra mide 32px (h-8): encogemos el botón a 28px para que entre sin
          // estirar la fila; `-ml-1` lo pega al borde izquierdo del hueco.
          className="-ml-1 shrink-0"
          aria-label="Volver"
          onClick={onAtras}
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
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
 * Navegación de SECCIÓN de una página plana cuyas sub-vistas conmutan por ESTADO (no por ruta):
 * se portaliza al MISMO hueco izquierdo que `<TituloPagina/>` (son EXCLUYENTES — una página usa
 * una u otra) y se pinta con el formato de la subnav por ruta del topbar. Así una página con
 * pestañas-por-estado (Turnos, Investigación, Contexto, Sistema) arranca idéntica a un hub por
 * ruta (Métricas/Campañas): misma tira en escritorio, mismo dropdown en móvil, mismos estados.
 *
 * La página posee el estado (qué sección está activa) y lo refleja donde quiera (un `?param=` o
 * un `useState`); aquí solo se presenta y se notifica el cambio vía `onSelect`.
 */
export function PestanasSeccion({
  pestanas,
  activo,
  onSelect,
}: {
  pestanas: PestanaSeccion[];
  activo: string;
  onSelect: (valor: string) => void;
}) {
  const ctx = useEncabezado();
  // Igual que el título: marca que la barra tiene contenido propio (no-op estable hoy).
  React.useEffect(() => ctx?.registrarTitulo(), [ctx]);
  const elemento = (
    <TiraPestanasSeccion pestanas={pestanas} activo={activo} onSelect={onSelect} />
  );
  // Mismas tres ramas que `TituloPagina`: portal al hueco, inline sin proveedor (tests sueltos),
  // o nada mientras el hueco aún no está montado.
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
