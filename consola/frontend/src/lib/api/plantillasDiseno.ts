// Fragmento del cliente API: dominio «plantillasDiseno». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type { PlantillaDiseno } from "./_core";

export const apiPlantillasDiseno = {
  // --- Texto de plantillas de diseño (N por marca, etiquetadas por línea) ---
  // `tipo` filtra por "foto" (plantillas de imagen) o "miniatura" (portadas de video).
  plantillasDiseno: (
    filtros: { marca?: string; categoria?: string; linea?: string; q?: string; tipo?: "foto" | "miniatura" } = {},
    signal?: AbortSignal,
  ) => {
    const qp = new URLSearchParams();
    for (const [k, v] of Object.entries(filtros)) if (v) qp.set(k, v);
    const cola = qp.toString();
    return peticion<{ plantillas: PlantillaDiseno[] }>(`/plantillas-diseno${cola ? `?${cola}` : ""}`, { signal });
  },
  crearPlantillaDiseno: (cuerpo: {
    marca?: string;
    nombre?: string;
    categoria?: string;
    /** "foto" (default) | "miniatura" (portada de video). */
    tipo?: "foto" | "miniatura";
    documento: unknown;
    miniatura?: string;
    /** Muestra de la galería (horneada): objeto de la foto + titular/pleca representativos. */
    foto_muestra?: string;
    titular_muestra?: string;
    etiqueta_muestra?: string;
    lineas?: string[];
  }) => peticion<{ plantilla: PlantillaDiseno }>("/plantillas-diseno", { metodo: "POST", json: cuerpo }),
  // Actualiza una plantilla existente (PATCH): «Guardar» sobre la plantilla ya creada.
  // Muestra de la galería: `foto_muestra`/`titular_muestra`/`etiqueta_muestra`; `""` en cada uno limpia
  // ese campo (foto -> huecos grises; titular -> "TITULAR"; pleca -> el texto literal de la capa).
  actualizarPlantillaDiseno: (
    id: string,
    cuerpo: { nombre?: string; categoria?: string; tipo?: "foto" | "miniatura"; documento?: unknown; miniatura?: string; foto_muestra?: string; titular_muestra?: string; etiqueta_muestra?: string; lineas?: string[]; activo?: boolean; rotar?: boolean },
  ) => peticion<{ plantilla: PlantillaDiseno }>(`/plantillas-diseno/${encodeURIComponent(id)}`, { metodo: "PATCH", json: cuerpo }),
  borrarPlantillaDiseno: (id: string) =>
    peticion<{ mensaje: string }>(`/plantillas-diseno/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  // Fija el ORDEN MANUAL de la galería (drag-and-drop): `ids` en la secuencia exacta deseada.
  reordenarPlantillasDiseno: (ids: string[]) =>
    peticion<{ actualizadas: number }>("/plantillas-diseno/reordenar", { metodo: "POST", json: { ids } }),

};
