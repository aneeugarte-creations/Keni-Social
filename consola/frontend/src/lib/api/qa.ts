// Fragmento del cliente API: dominio «qa». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type { CuerpoVerificar, RespuestaGeneracion } from "@/types";

// La «página de revisión de copy» (qa-editorial) se RETIRÓ (feature muerta: sin UI). Aquí solo
// queda la verificación de vídeo, que es un workflow independiente. La revisión de IMAGEN sigue
// viva en su propio cliente (`apiImagenes.imagenesRevisar`), no aquí.
export const apiQa = {
  // --- Verificación de video (workflow propio, independiente de Generar copy) ---
  // Lanza el análisis de procedencia en segundo plano; se sondea como cualquier
  // generación (GET /api/generaciones/{id}) y completa con `resultado.verificacion`.
  verificar: (cuerpo: CuerpoVerificar) =>
    peticion<RespuestaGeneracion>("/verificar", { metodo: "POST", json: cuerpo }),
};
