// Fragmento del cliente API: dominio «fuentesAcciones». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";

export const apiFuentesAcciones = {
  // --- Ola D: acciones sobre fuentes RSS ---
  fuentes: {
    /**
     * Reactiva un feed desactivado automáticamente:
     * activo=1, desactivado_auto=0, errores_seguidos=0, proximo_sondeo='' (reintentar ya).
     * POST /api/fuentes/{id}/reactivar
     */
    reactivar: (id: string) =>
      peticion<{ ok: boolean }>(
        `/fuentes/${encodeURIComponent(id)}/reactivar`,
        { metodo: "POST", muestrear: false },
      ),
  },
};
