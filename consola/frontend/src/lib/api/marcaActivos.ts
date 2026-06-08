// Fragmento del cliente API: dominio «marcaActivos». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type { ActivoMarca } from "./_core";

export const apiMarcaActivos = {
  // --- Texto de activos por marca (logos, tipografías, artes, infografías, …) ---
  marcaActivos: (
    filtros: { marca?: string; tipo?: string; linea?: string; q?: string } = {},
    signal?: AbortSignal,
  ) => {
    const qp = new URLSearchParams();
    for (const [k, v] of Object.entries(filtros)) if (v) qp.set(k, v);
    const cola = qp.toString();
    return peticion<{ activos: ActivoMarca[] }>(`/marca-activos${cola ? `?${cola}` : ""}`, { signal });
  },
  crearMarcaActivo: (cuerpo: {
    tipo: string;
    marca?: string;
    nombre?: string;
    objeto?: string;
    metadatos?: Record<string, unknown>;
    lineas?: string[];
  }) => peticion<{ activo: ActivoMarca }>("/marca-activos", { metodo: "POST", json: cuerpo }),
  actualizarMarcaActivo: (id: string, cuerpo: Record<string, unknown>) =>
    peticion<{ activo: ActivoMarca }>(`/marca-activos/${encodeURIComponent(id)}`, { metodo: "PATCH", json: cuerpo }),
  borrarMarcaActivo: (id: string, purgar?: boolean) =>
    peticion<{ mensaje: string }>(
      `/marca-activos/${encodeURIComponent(id)}${purgar ? "?purgar=1" : ""}`,
      { metodo: "DELETE" },
    ),

};
