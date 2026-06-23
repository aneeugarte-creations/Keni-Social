import type { OpcionesPiezas } from "@/types";

/**
 * Nombre legible de la categoría del plan de una pieza, resuelto contra el catálogo de
 * `/piezas/opciones` (las MISMAS etiquetas que el selector de «Crear post» y los chips del
 * feed: el backend ya resuelve líneas por su nombre de BD y señales del motor —breaking/
 * evergreen— por su rótulo). Devuelve cadena vacía cuando la pieza no pertenece a ninguna
 * categoría del plan («Fuera del plan», sin franja) o el catálogo aún no cargó; en ese caso
 * la cabecera del editor no pinta etiqueta.
 */
export function nombreCategoriaPlan(
  categoria: string | null | undefined,
  marca: string,
  categorias: OpcionesPiezas["categorias"] | undefined,
): string {
  const id = (categoria ?? "").trim();
  if (!id) return "";
  const cats = categorias?.[marca] ?? [];
  return cats.find((c) => c.id === id)?.nombre ?? "";
}
