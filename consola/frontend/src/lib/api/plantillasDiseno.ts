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
    lineas?: string[];
  }) => peticion<{ plantilla: PlantillaDiseno }>("/plantillas-diseno", { metodo: "POST", json: cuerpo }),
  // Actualiza una plantilla existente (PATCH): «Guardar» sobre la plantilla ya creada.
  actualizarPlantillaDiseno: (
    id: string,
    cuerpo: { nombre?: string; categoria?: string; tipo?: "foto" | "miniatura"; documento?: unknown; miniatura?: string; lineas?: string[]; activo?: boolean; rotar?: boolean },
  ) => peticion<{ plantilla: PlantillaDiseno }>(`/plantillas-diseno/${encodeURIComponent(id)}`, { metodo: "PATCH", json: cuerpo }),
  borrarPlantillaDiseno: (id: string) =>
    peticion<{ mensaje: string }>(`/plantillas-diseno/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

};
