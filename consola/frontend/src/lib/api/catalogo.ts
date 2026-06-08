// Fragmento del cliente API: dominio «catalogo». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  RespuestaCatalogo,
} from "@/types";

export const apiCatalogo = {
  // --- Catálogo de apps (ADR 0005): apps activas + navegación data-driven ---
  // El sidebar se hidrata de aquí en vez de hardcodear las entradas. Filtra por los
  // flags de activación del backend; desactivar una app la oculta sin tocar el front.
  catalogo: (signal?: AbortSignal) => peticion<RespuestaCatalogo>("/catalogo", { signal }),

};
