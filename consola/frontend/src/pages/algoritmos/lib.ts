import type { NivelAlgoritmo } from "@/types";

export const TODAS = "__todas__";

/** Variante de badge según el nivel de importancia. */
export function badgeNivel(
  nivel: NivelAlgoritmo,
): { variante: "ok" | "secondary" | "outline"; texto: string } {
  if (nivel === "alta") return { variante: "ok", texto: "Importante" };
  if (nivel === "media") return { variante: "secondary", texto: "Media" };
  return { variante: "outline", texto: "Baja" };
}
