import * as React from "react";

import type { MarcaDisponible } from "@/types";

/**
 * Contexto de la MARCA ACTIVA: el "workspace" de marca en el que trabaja la
 * persona. Toda la consola está pensada por marca (no mezclar): un editor de
 * Claro Sports ve Claro Sports en todas partes SIN tener que filtrar, y solo
 * cambia de marca de forma deliberada y visible.
 *
 * La marca activa DERIVA del perfil (`usuario.marcas`, la relación N:M del
 * organigrama del cliente):
 *   - Marca primaria = la primera marca asignada (su "marca de casa").
 *   - Por defecto FUERTE: la consola arranca en la marca primaria.
 *   - El cambio es deliberado (switch en la barra superior) y se PERSISTE por
 *     usuario, pero el estado "estás fuera de tu marca" queda siempre visible.
 *
 * Quién puede cambiar (`marcasParaSwitch`):
 *   - Foco, no restricción: el switch lista SIEMPRE el catálogo completo, así que
 *     cualquiera (editor o admin) puede enfocar cualquier marca; por defecto arranca
 *     en la propia. Si el catálogo tiene una sola marca no hay nada que conmutar.
 *   - Solo el SUPERADMIN ve además la opción "Todas" (vista agregada para supervisión
 *     operativa). Un admin normal es autoridad sobre SUS marcas, no sobre todas.
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
  /**
   * `true` si la marca activa NO es una de las marcas asignadas del usuario (estás enfocando una
   * marca ajena). La UI lo avisa en ámbar y ofrece "Volver a tu marca". `false` cuando enfocas
   * una de tus marcas (aunque no sea la primaria) o la vista agregada "Todas". Opcional: ausente
   * se trata como `false` (default seguro); el provider real siempre lo provee.
   */
  fueraDeCasa?: boolean;
  /** `true` si hay más de una opción de marca: entonces se muestra el switch. */
  esMultiMarca: boolean;
  /** `true` si la persona puede elegir la vista agregada "Todas" (solo superadmin). */
  puedeTodas: boolean;
  /**
   * `true` si la marca activa es de NOTICIAS (pasa por investigación). `false` para marcas de
   * contenido propio (`tipo='propio'`): la UI oculta el panel de Noticias. "Todas" (null) → true.
   * Opcional: ausente se trata como noticias (default seguro); el provider siempre lo provee.
   */
  marcaActivaEsNoticias?: boolean;
  /**
   * Nombre del panel de investigación de la marca activa (p.ej. "Curiosidades" para una marca de
   * datos curiosos). "Noticias" por defecto y para la vista agregada ("Todas"). Opcional: ausente
   * se trata como "Noticias" (default seguro); el provider siempre lo provee.
   */
  etiquetaInvestigacion?: string;
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

/**
 * Mensaje único para acciones que EXIGEN una marca concreta cuando el switch global está en
 * "Todas" (`marcaActiva === null`, solo admin). Ya no hay selectores de marca por página: la
 * marca la manda SIEMPRE el switch global. Si está en "Todas", la acción se deshabilita y este
 * texto va en su tooltip. (Los editores siempre tienen una marca concreta, así que solo afecta
 * a admins en la vista agregada.)
 */
export const MENSAJE_MARCA_REQUERIDA =
  "Elige una marca concreta en el selector de arriba para esta acción.";
