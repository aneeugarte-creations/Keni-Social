// Fragmento del cliente API: dominio «bloques». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type { Bloque } from "./_core";

export const apiBloques = {
  // --- Almacén de bloques (grupos de capas reutilizables) ---
  bloques: (filtros: { marca?: string; q?: string } = {}, signal?: AbortSignal) => {
    const qp = new URLSearchParams();
    for (const [k, v] of Object.entries(filtros)) if (v) qp.set(k, v);
    const cola = qp.toString();
    return peticion<{ bloques: Bloque[] }>(`/bloques${cola ? `?${cola}` : ""}`, { signal });
  },
  crearBloque: (cuerpo: { marca?: string; nombre?: string; capas: unknown[]; lineas?: string[]; miniatura?: string }) =>
    peticion<{ bloque: Bloque }>("/bloques", { metodo: "POST", json: cuerpo }),
  borrarBloque: (id: string) =>
    peticion<{ mensaje: string }>(`/bloques/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

};
