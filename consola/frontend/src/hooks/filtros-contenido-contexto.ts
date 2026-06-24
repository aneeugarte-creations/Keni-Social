import * as React from "react";

import type { RedPieza } from "@/types";

/**
 * Contexto del FILTRO GLOBAL de RED, hermano del switch de MARCA (`marca-activa-contexto`).
 * La elección la manda el selector global de la barra superior y las páginas solo leen de aquí.
 *
 * La LÍNEA del plan NO vive aquí: se filtra POR PÁGINA (chips del Feed, dropdown de Categoría de
 * la Lista) sobre el eje `categoria` —único eje de línea/categoría— con el catálogo de
 * `opciones.categorias`. Antes había aquí un filtro de "Categoría" (eje de tags) paralelo;
 * se retiró para no tener dos ejes que el usuario veía como lo mismo.
 *
 * Por defecto FUERTE: "Todas" (centinela `FILTRO_TODOS`), de modo que el comportamiento inicial
 * NO cambia (se ve todo). La elección se PERSISTE por usuario (localStorage), como la marca.
 *
 * Visibilidad: el provider es global, pero el filtro de Red solo se ofrece (dentro del control de
 * contexto unificado de la topbar, `ControlContexto`) en las rutas de contenido/feed donde aplica
 * (ver `RUTAS_FILTROS_CONTENIDO` y `rutaUsaFiltrosPublicacion`); en métricas/ajustes/usuarios no.
 */
export interface ValorFiltrosPublicacion {
  /** Red activa (id), o `FILTRO_TODOS` para no filtrar por red. */
  red: string;
  /** Catálogo de redes para el selector (de `/api/piezas/opciones`). */
  redes: RedPieza[];
  /** Cambia la red activa (persiste por usuario). */
  cambiarRed: (id: string) => void;
}

export const FiltrosPublicacionContexto = React.createContext<ValorFiltrosPublicacion | null>(null);

/**
 * Hook para leer el filtro global de Red. Debe usarse dentro del `FiltrosPublicacionProvider`.
 * Las páginas de contenido/feed lo usan para acotar sus queries: `red === FILTRO_TODOS ? undefined : red`.
 */
export function useFiltrosPublicacion(): ValorFiltrosPublicacion {
  const valor = React.useContext(FiltrosPublicacionContexto);
  if (!valor) {
    throw new Error("useFiltrosPublicacion debe usarse dentro de <FiltrosPublicacionProvider>.");
  }
  return valor;
}

/**
 * Centinela de "todas / sin filtrar" para la red. Es el MISMO valor que ya usaban las páginas
 * (`FILTRO_TODOS` / `MARCA_TODAS` / `RED_TODAS`, todos `"__todas__"`).
 */
export const FILTRO_TODOS = "__todas__";

/** Clave de localStorage de la red activa, por usuario (sobrevive recargas). */
export function claveRedActiva(usuarioId: string): string {
  return `keni:red-activa:${usuarioId}`;
}

/**
 * Rutas donde APLICA (y se pinta) el selector global de Red: las superficies de contenido/feed
 * —el Feed de ideación (`/operacion/feed/feed`), la Lista de contenido (`/operacion/feed/lista`)
 * y la Programación (`/operacion/programa/programacion`)—. En métricas/ajustes/usuarios NO se
 * muestra (el provider sigue siendo global; solo se oculta la UI).
 */
export const RUTAS_FILTROS_CONTENIDO = [
  "/operacion/feed/feed",
  "/operacion/feed/lista",
  "/operacion/programa/programacion",
];

/** ¿La ruta actual usa el filtro global de contenido (Red)? */
export function rutaUsaFiltrosPublicacion(pathname: string): boolean {
  return RUTAS_FILTROS_CONTENIDO.some(
    (ruta) => pathname === ruta || pathname.startsWith(`${ruta}/`),
  );
}
