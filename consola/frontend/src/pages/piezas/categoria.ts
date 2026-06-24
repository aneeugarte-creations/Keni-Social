import { ETIQUETA_LINEA, etiquetaLinea } from "@/lib/lineas";
import type { OpcionesPiezas } from "@/types";

/**
 * Rótulo legible de la categoría de una pieza para la cabecera del editor.
 *
 * `pieza.categoria` puede ser:
 *  - el ID de una etiqueta vertical (un hash, p. ej. "06ad3588a80e") — el caso del Plan y la
 *    programación: se resuelve a su nombre con la lista `lineas` de `/piezas/opciones`;
 *  - un slug de categoría conocido (señal del motor o ingesta: "breaking", "evergreen", "mx"…)
 *    — se resuelve con `etiquetaLinea` (mismo catálogo que la Mesa de Noticias).
 *
 * Devuelve cadena vacía (no se pinta etiqueta) cuando la pieza no tiene categoría o cuando el id
 * NO se puede resolver (catálogo aún sin cargar, vertical retirada…): NUNCA se muestra un id crudo.
 */
export function etiquetaCategoriaPieza(
  categoria: string | null | undefined,
  lineas: OpcionesPiezas["lineas"] | undefined,
): string {
  const id = (categoria ?? "").trim();
  if (!id) return "";
  const linea = (lineas ?? []).find((l) => l.id === id);
  if (linea) return linea.nombre;
  if (ETIQUETA_LINEA[id]) return etiquetaLinea(id);
  return "";
}
