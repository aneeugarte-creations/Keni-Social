import { ETIQUETA_CATEGORIA, etiquetaCategoria } from "@/lib/categorias";
import type { OpcionesPiezas } from "@/types";

/**
 * Rótulo legible de la categoría de una pieza para la cabecera del editor.
 *
 * `pieza.categoria` puede ser:
 *  - el ID de una etiqueta categoria (un hash, p. ej. "06ad3588a80e") — el caso del Plan y la
 *    programación: se resuelve a su nombre con la lista `categorias_catalogo` de `/piezas/opciones`;
 *  - un slug de categoría conocido (señal del motor o ingesta: "breaking", "evergreen", "mx"…)
 *    — se resuelve con `etiquetaCategoria` (mismo catálogo que la Mesa de Noticias).
 *
 * Devuelve cadena vacía (no se pinta etiqueta) cuando la pieza no tiene categoría o cuando el id
 * NO se puede resolver (catálogo aún sin cargar, categoría retirada…): NUNCA se muestra un id crudo.
 */
export function etiquetaCategoriaPieza(
  categoria: string | null | undefined,
  categoriasCatalogo: OpcionesPiezas["categorias_catalogo"] | undefined,
): string {
  const id = (categoria ?? "").trim();
  if (!id) return "";
  const cat = (categoriasCatalogo ?? []).find((l) => l.id === id);
  if (cat) return cat.nombre;
  if (ETIQUETA_CATEGORIA[id]) return etiquetaCategoria(id);
  return "";
}
