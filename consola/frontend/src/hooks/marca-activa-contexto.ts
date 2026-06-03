import * as React from "react";

import type { MarcaDisponible } from "@/types";

/**
 * Contexto de la MARCA ACTIVA: el "workspace" de marca en el que trabaja la
 * persona. Toda la consola está pensada por marca (no mezclar): un editor de
 * Claro Sports ve Claro Sports en todas partes SIN tener que filtrar, y solo
 * cambia de marca de forma deliberada y visible.
 *
 * La marca activa DERIVA del perfil (`usuario.marcas`, la relación N:M del
 * organigrama AMX):
 *   - Marca primaria = la primera marca asignada (su "marca de casa").
 *   - Por defecto FUERTE: la consola arranca en la marca primaria.
 *   - El cambio es deliberado (switch en la barra superior) y se PERSISTE por
 *     usuario, pero el estado "estás fuera de tu marca" queda siempre visible.
 *
 * Quién puede cambiar (`marcasParaSwitch`):
 *   - Editor con 1 marca → no hay switch (queda fijado a su marca).
 *   - Editor con varias marcas → cambia entre SUS marcas (sin opción "Todas":
 *     "Todas" mezcla, y el principio es no mezclar).
 *   - Admin → cambia entre TODAS las marcas y además puede elegir "Todas"
 *     (vista agregada para supervisión operativa).
 *
 * El provider (en `use-marca-activa.tsx`) resuelve el catálogo de nombres y la
 * persistencia; este archivo solo declara el contrato (separado del .tsx para
 * cumplir `react-refresh/only-export-components`, igual que la sesión y el tema).
 */
export interface ValorMarcaActiva {
  /** Id canónico de la marca activa, o `null` para la vista agregada ("Todas"). */
  marcaActiva: string | null;
  /** Marca "de casa" del perfil (primera asignada), o `null` si no cubre ninguna. */
  marcaPrimaria: string | null;
  /**
   * `true` si se está viendo la marca de casa (o, para quien no tiene marca
   * asignada, la vista "Todas"). Si es `false`, la UI avisa "estás fuera de tu
   * marca" y ofrece volver.
   */
  enMarcaPrimaria: boolean;
  /** `true` si hay más de una opción de marca: entonces se muestra el switch. */
  esMultiMarca: boolean;
  /** `true` si la persona puede elegir la vista agregada "Todas" (solo admin). */
  puedeTodas: boolean;
  /** Opciones del switch, con nombre legible (las marcas del perfil, o todas si admin). */
  marcasParaSwitch: MarcaDisponible[];
  /** Nombre legible de la marca activa, o `null` para "Todas". */
  nombreActiva: string | null;
  /** Cambia la marca activa (id canónico, o `null` para "Todas"). Persiste por usuario. */
  cambiarMarca: (id: string | null) => void;
  /** Vuelve a la marca de casa (o a "Todas" si no hay marca primaria). */
  volverAPrimaria: () => void;
}

export const MarcaActivaContexto = React.createContext<ValorMarcaActiva | null>(null);

/**
 * Hook para leer la marca activa. Debe usarse dentro del `MarcaActivaProvider`.
 * Las páginas lo usan para inicializar sus filtros: `marcaActiva ?? undefined`
 * es el parámetro de marca para la API (null = no filtrar / agregado).
 */
export function useMarcaActiva(): ValorMarcaActiva {
  const valor = React.useContext(MarcaActivaContexto);
  if (!valor) {
    throw new Error("useMarcaActiva debe usarse dentro de <MarcaActivaProvider>.");
  }
  return valor;
}

/** Centinela de persistencia para "Todas" (localStorage no guarda `null`). */
export const MARCA_ACTIVA_TODAS = "__todas__";

/** Clave de localStorage de la marca activa, por usuario (sobrevive recargas). */
export function claveMarcaActiva(usuarioId: string): string {
  return `keni:marca-activa:${usuarioId}`;
}
