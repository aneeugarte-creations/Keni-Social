// Fragmento del cliente API: dominio «qa». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoRevisarQaEditorial,
  CuerpoVerificar,
  OpcionesQaEditorial,
  RespuestaGeneracion,
} from "@/types";

export const apiQa = {
  // --- Verificación de video (workflow propio, independiente de Generar copy) ---
  // Lanza el análisis de procedencia en segundo plano; se sondea como cualquier
  // generación (GET /api/generaciones/{id}) y completa con `resultado.verificacion`.
  verificar: (cuerpo: CuerpoVerificar) =>
    peticion<RespuestaGeneracion>("/verificar", { metodo: "POST", json: cuerpo }),

  // --- QA editorial (revisar el copy ya escrito por el community, ficha F3 / #143) ---
  // Lanza la revisión en segundo plano; se sondea como cualquier generación
  // (GET /api/generaciones/{id}) y completa con `resultado.informe`. NO publica ni reescribe.
  qaEditorialOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesQaEditorial>("/qa-editorial", { signal }),
  revisarQaEditorial: (cuerpo: CuerpoRevisarQaEditorial) =>
    peticion<RespuestaGeneracion>("/qa-editorial/revisar", { metodo: "POST", json: cuerpo }),

};
