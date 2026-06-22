import * as React from "react";

import type { LineaEditorialOpcion, RedPieza } from "@/types";

/**
 * Contexto de los FILTROS GLOBALES de contenido (Red + Línea editorial), hermanos
 * del switch de MARCA (`marca-activa-contexto`). Son los filtros que antes vivían
 * por página en el Feed y en Gestión de piezas (Lista/Calendario): ahora la
 * elección la mandan DOS selectores globales de la barra superior, igual que la
 * marca, y las páginas solo leen de aquí.
 *
 * Por defecto FUERTE: ambos en "Todas" (centinela `FILTRO_TODOS`, el mismo que ya
 * usaban las páginas), de modo que el comportamiento inicial NO cambia (se ve todo).
 * La elección se PERSISTE por usuario (localStorage), como la marca.
 *
 * Dependencia marca → línea: las líneas elegibles dependen de la marca activa (las de
 * la marca + las globales). El provider (`use-filtros-contenido.tsx`) resetea la línea
 * a "Todas" si la persistida deja de ser elegible con la marca activa actual. Por eso
 * el provider se monta DEBAJO del de marca.
 *
 * Visibilidad: el provider es global, pero los filtros de Red/Línea solo se ofrecen (dentro
 * del control de contexto unificado de la topbar, `ControlContexto`) en las rutas de
 * contenido/feed donde aplican (ver `RUTAS_FILTROS_CONTENIDO` y `rutaUsaFiltrosPublicacion`);
 * en métricas/ajustes/usuarios no aparecen.
 */
export interface ValorFiltrosPublicacion {
  /** Red activa (id), o `FILTRO_TODOS` para no filtrar por red. */
  red: string;
  /** Línea editorial activa (id), o `FILTRO_TODOS` para no filtrar por línea. */
  linea: string;
  /** Catálogo de redes para el selector (de `/api/piezas/opciones`). */
  redes: RedPieza[];
  /**
   * Líneas elegibles con la marca activa actual: las de la marca + las globales
   * (`marca === ""`). En la vista "Todas" (marca activa null) son todas.
   */
  lineasElegibles: LineaEditorialOpcion[];
  /** Cambia la red activa (persiste por usuario). */
  cambiarRed: (id: string) => void;
  /** Cambia la línea activa (persiste por usuario). */
  cambiarLinea: (id: string) => void;
}

export const FiltrosPublicacionContexto = React.createContext<ValorFiltrosPublicacion | null>(null);

/**
 * Hook para leer los filtros globales de contenido. Debe usarse dentro del
 * `FiltrosPublicacionProvider`. Las páginas de contenido/feed lo usan para acotar sus
 * queries: `red === FILTRO_TODOS ? undefined : red` (igual con `linea`).
 */
export function useFiltrosPublicacion(): ValorFiltrosPublicacion {
  const valor = React.useContext(FiltrosPublicacionContexto);
  if (!valor) {
    throw new Error("useFiltrosPublicacion debe usarse dentro de <FiltrosPublicacionProvider>.");
  }
  return valor;
}

/**
 * Centinela de "todas / sin filtrar" para red y línea. Es el MISMO valor que ya usaban
 * las páginas (`FILTRO_TODOS` / `MARCA_TODAS` / `RED_TODAS`, todos `"__todas__"`), así
 * que al recablear no cambia ningún valor por el cable.
 */
export const FILTRO_TODOS = "__todas__";

/** Clave de localStorage de la red activa, por usuario (sobrevive recargas). */
export function claveRedActiva(usuarioId: string): string {
  return `keni:red-activa:${usuarioId}`;
}

/** Clave de localStorage de la línea activa, por usuario (sobrevive recargas). */
export function claveLineaActiva(usuarioId: string): string {
  return `keni:linea-activa:${usuarioId}`;
}

/**
 * Rutas donde APLICAN (y se pintan) los selectores globales de Red y Línea: las
 * superficies de contenido/feed que antes llevaban esos filtros por página —el Feed
 * de ideación (`/operacion/feed/feed`), la Lista de contenido (`/operacion/feed/lista`)
 * y la Programación (`/operacion/programa/programacion`)—. En métricas/ajustes/usuarios NO se
 * muestran (el provider sigue siendo global; solo se oculta la UI).
 */
export const RUTAS_FILTROS_CONTENIDO = [
  "/operacion/feed/feed",
  "/operacion/feed/lista",
  "/operacion/programa/programacion",
];

/** ¿La ruta actual usa los filtros globales de contenido (Red/Línea)? */
export function rutaUsaFiltrosPublicacion(pathname: string): boolean {
  return RUTAS_FILTROS_CONTENIDO.some(
    (ruta) => pathname === ruta || pathname.startsWith(`${ruta}/`),
  );
}
