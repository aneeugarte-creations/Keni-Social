// Fragmento del cliente API: dominio «etiquetasPlantilla» (catálogo de categorías editable por marca).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + su tipo.
import { peticion } from "./_core";

/**
 * Rótulo personalizado de una categoría de plantilla, POR MARCA. La categoría sigue siendo el `slug`
 * (texto libre de `plantillas_diseno.categoria`); `etiqueta` es el rótulo legible que el equipo le
 * puso al renombrarla. Vacío = usar el rótulo por defecto del catálogo (`lib/categoriasPlantilla.ts`).
 */
export interface EtiquetaPlantilla {
  marca: string;
  slug: string;
  etiqueta: string;
}

export const apiEtiquetasPlantilla = {
  etiquetasPlantilla: (filtros: { marca?: string } = {}, signal?: AbortSignal) => {
    const qp = new URLSearchParams();
    if (filtros.marca) qp.set("marca", filtros.marca);
    const cola = qp.toString();
    return peticion<{ etiquetas: EtiquetaPlantilla[] }>(
      `/etiquetas-plantilla${cola ? `?${cola}` : ""}`,
      { signal },
    );
  },
  // Crea o RENOMBRA el rótulo de `(marca, slug)` (no mueve plantillas: el slug es la identidad).
  guardarEtiquetaPlantilla: (marca: string, slug: string, etiqueta: string) =>
    peticion<{ etiqueta: EtiquetaPlantilla }>(
      `/etiquetas-plantilla/${encodeURIComponent(marca)}/${encodeURIComponent(slug)}`,
      { metodo: "PUT", json: { etiqueta } },
    ),
  // Borra el rótulo personalizado (409 si alguna plantilla usa esa categoría).
  borrarEtiquetaPlantilla: (marca: string, slug: string) =>
    peticion<{ mensaje: string }>(
      `/etiquetas-plantilla/${encodeURIComponent(marca)}/${encodeURIComponent(slug)}`,
      { metodo: "DELETE" },
    ),
};
