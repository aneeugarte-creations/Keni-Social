// Fragmento del cliente API: dominio «plantillasMarca». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, cabecerasAuth, BASE_API, ApiError } from "./_core";
import type {
  PlantillaMarca,
  RespuestaPlantillaMarca,
  RespuestaPlantillasMarca,
} from "@/types";
import type { PlantillaSpec } from "../specPlantilla";

export const apiPlantillasMarca = {
  // --- Plantillas de marca (identidad visual con la que se estampa una imagen) ---
  // Solo lectura del catálogo + edición de la plantilla de una marca (logo, colores,
  // etiqueta/pleca, posición del logo, wordmark de respaldo). El logo se sube antes con
  // `subirMedia` y aquí se guarda su id en `logo`.
  plantillasMarca: (signal?: AbortSignal) =>
    peticion<RespuestaPlantillasMarca>("/plantillas-marca", { signal }),
  plantillaMarca: (marca: string, signal?: AbortSignal) =>
    peticion<RespuestaPlantillaMarca>(`/plantillas-marca/${encodeURIComponent(marca)}`, { signal }),
  guardarPlantillaMarca: (marca: string, datos: Partial<PlantillaMarca>) =>
    peticion<RespuestaPlantillaMarca>(`/plantillas-marca/${encodeURIComponent(marca)}`, {
      metodo: "PUT",
      json: datos,
    }),
  // SPEC de capas del editor visual: leer / guardar / previsualizar (render real del servidor).
  specPlantilla: (marca: string, signal?: AbortSignal) =>
    peticion<{ spec: PlantillaSpec }>(`/plantillas-marca/${encodeURIComponent(marca)}/spec`, { signal }),
  guardarSpecPlantilla: (marca: string, spec: PlantillaSpec) =>
    peticion<{ spec: PlantillaSpec }>(`/plantillas-marca/${encodeURIComponent(marca)}/spec`, {
      metodo: "PUT",
      json: { spec },
    }),
  // La previa del diseñador es EFÍMERA: el back devuelve los BYTES del PNG (no persiste nada) y
  // aquí construimos un object URL para el <img>. El llamante debe revocar el URL anterior.
  previewPlantilla: async (
    marca: string, spec: PlantillaSpec, formato: string, titular?: string,
  ): Promise<string> => {
    let res: Response;
    try {
      res = await fetch(`${BASE_API}/plantillas-marca/${encodeURIComponent(marca)}/preview`, {
        method: "POST",
        headers: { ...cabecerasAuth(), "Content-Type": "application/json" },
        body: JSON.stringify({ spec, formato, titular: titular ?? "" }),
      });
    } catch {
      throw new ApiError("No se pudo contactar con la consola.", 0);
    }
    if (!res.ok) {
      let mensaje = "No se pudo previsualizar la plantilla.";
      try {
        const j = await res.json();
        if (j?.error) mensaje = j.error;
      } catch {
        /* cuerpo no-JSON: mensaje por defecto */
      }
      throw new ApiError(mensaje, res.status);
    }
    return URL.createObjectURL(await res.blob());
  },

};
