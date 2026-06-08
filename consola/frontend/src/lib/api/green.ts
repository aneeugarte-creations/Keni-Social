// Fragmento del cliente API: dominio «green». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoActualizarIdeaGreen,
  CuerpoCrearIdeaGreen,
  CuerpoGenerarIdeaGreen,
  CuerpoProponerGreen,
  RespuestaGeneracion,
  RespuestaIdeaGreen,
  RespuestaIdeasGreen,
  RespuestaMensaje,
} from "@/types";

export const apiGreen = {
  // --- Green: banco de ideas de contenido evergreen (perenne) por marca ---
  // Las ideas se proponen a mano o con IA (`proponerGreen` lanza un trabajo en 2º plano que
  // se SONDEA con `useGeneracion`); al aprobar una idea se puede generar la pieza evergreen.
  ideasGreen: (
    params: { marca?: string; estado?: string } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaIdeasGreen>(`/green/ideas${query(params)}`, { signal }),
  crearIdeaGreen: (cuerpo: CuerpoCrearIdeaGreen) =>
    peticion<RespuestaIdeaGreen>("/green/ideas", { metodo: "POST", json: cuerpo }),
  actualizarIdeaGreen: (id: string, cuerpo: CuerpoActualizarIdeaGreen) =>
    peticion<RespuestaIdeaGreen>(`/green/ideas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarIdeaGreen: (id: string) =>
    peticion<RespuestaMensaje>(`/green/ideas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  proponerGreen: (cuerpo: CuerpoProponerGreen) =>
    peticion<RespuestaGeneracion>("/green/proponer", { metodo: "POST", json: cuerpo }),
  generarIdeaGreen: (id: string, cuerpo: CuerpoGenerarIdeaGreen = {}) =>
    peticion<RespuestaGeneracion>(`/green/ideas/${encodeURIComponent(id)}/generar`, {
      metodo: "POST",
      json: cuerpo,
    }),

};
