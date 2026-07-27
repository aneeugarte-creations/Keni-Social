/**
 * Paleta por FAMILIA DE CARGO: el color del avatar de una persona sale de lo que hace, no
 * de su marca (las marcas son multivalor y ya se ven como chips propios). Los 20 cargos se
 * agrupan en 6 familias para que el color siga siendo legible en un punto de 28px.
 *
 * Hermana de `lib/marca-colores.ts` (acento por marca): son ejes distintos y no se mezclan.
 */

import type { CargoUsuario } from "@/types";

/** Familias en que se agrupan los cargos para pintarlos. */
export type FamiliaCargo =
  | "direccion"
  | "coordinacion"
  | "contenido"
  | "editorial"
  | "creativo"
  | "imagen"
  | "sin_cargo";

export interface MetaFamilia {
  /** Etiqueta humana de la familia (tooltip del avatar). */
  etiqueta: string;
  /** Parada clara, base y oscura del degradado (135°, estilo del avatar de cuenta). */
  degradado: [string, string, string];
}

export const META_FAMILIA: Record<FamiliaCargo, MetaFamilia> = {
  direccion: { etiqueta: "Dirección", degradado: ["#94a3b8", "#475569", "#1e293b"] },
  coordinacion: { etiqueta: "Coordinación", degradado: ["#8ab6ff", "#2b7fff", "#0b4bbd"] },
  contenido: { etiqueta: "Contenido y comunidad", degradado: ["#ffcf70", "#f59e0b", "#b45309"] },
  editorial: { etiqueta: "Editorial y redacción", degradado: ["#6ee7b7", "#10b981", "#047857"] },
  creativo: { etiqueta: "Creativo y producción", degradado: ["#c4b5fd", "#8b5cf6", "#5b21b6"] },
  imagen: { etiqueta: "Foto y verificación", degradado: ["#fda4af", "#f43f5e", "#9f1239"] },
  sin_cargo: { etiqueta: "Sin cargo", degradado: ["#e2e8f0", "#cbd5e1", "#94a3b8"] },
};

/** Familia de cada cargo del catálogo (`CargoUsuario` sin la cadena vacía). */
export const FAMILIA_DE_CARGO: Record<Exclude<CargoUsuario, "">, FamiliaCargo> = {
  director: "direccion",
  gerente: "direccion",
  coordinador: "coordinacion",
  coordinador_redes: "coordinacion",
  coordinador_youtube: "coordinacion",
  coordinador_operativo: "coordinacion",
  coordinador_invitados: "coordinacion",
  estrategia: "coordinacion",
  content_manager: "contenido",
  community_manager: "contenido",
  gerente_podcast: "contenido",
  redactor: "editorial",
  guionista: "editorial",
  editorial: "editorial",
  editorial_youtube: "editorial",
  creativo_vertical: "creativo",
  editor_video: "creativo",
  disenador: "creativo",
  fotografia: "imagen",
  fotografia_revision: "imagen",
};

/** Familia de un cargo (vacío o desconocido => `sin_cargo`). */
export function familiaDeCargo(cargo: CargoUsuario | null | undefined): FamiliaCargo {
  if (!cargo) return "sin_cargo";
  return FAMILIA_DE_CARGO[cargo] ?? "sin_cargo";
}

/** Metadata (etiqueta + degradado) de la familia de un cargo. */
export function metaCargo(cargo: CargoUsuario | null | undefined): MetaFamilia {
  return META_FAMILIA[familiaDeCargo(cargo)];
}

/** `background-image` del avatar de una persona según su cargo. */
export function degradadoCargo(cargo: CargoUsuario | null | undefined): string {
  const [claro, base, oscuro] = metaCargo(cargo).degradado;
  return `linear-gradient(135deg, ${claro} 0%, ${base} 45%, ${oscuro} 100%)`;
}
