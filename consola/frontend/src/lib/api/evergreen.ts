// Fragmento del cliente API: dominio «evergreen». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoActualizarIdeaEvergreen,
  CuerpoCrearIdeaEvergreen,
  CuerpoGenerarIdeaEvergreen,
  CuerpoProponerEvergreen,
  RespuestaGeneracion,
  RespuestaIdeaEvergreen,
  RespuestaIdeasEvergreen,
  RespuestaMensaje,
} from "@/types";

export const apiEvergreen = {
  // --- Evergreen: banco de ideas de contenido evergreen (evergreen) por marca ---
  // Las ideas se proponen a mano o con IA (`proponerEvergreen` lanza un trabajo en 2º plano que
  // se SONDEA con `useGeneracion`); al aprobar una idea se puede generar la pieza evergreen.
  ideasEvergreen: (
    params: { marca?: string; estado?: string } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaIdeasEvergreen>(`/evergreen/ideas${query(params)}`, { signal }),
  crearIdeaEvergreen: (cuerpo: CuerpoCrearIdeaEvergreen) =>
    peticion<RespuestaIdeaEvergreen>("/evergreen/ideas", { metodo: "POST", json: cuerpo }),
  actualizarIdeaEvergreen: (id: string, cuerpo: CuerpoActualizarIdeaEvergreen) =>
    peticion<RespuestaIdeaEvergreen>(`/evergreen/ideas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarIdeaEvergreen: (id: string) =>
    peticion<RespuestaMensaje>(`/evergreen/ideas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  proponerEvergreen: (cuerpo: CuerpoProponerEvergreen) =>
    peticion<RespuestaGeneracion>("/evergreen/proponer", { metodo: "POST", json: cuerpo }),
  generarIdeaEvergreen: (id: string, cuerpo: CuerpoGenerarIdeaEvergreen = {}) =>
    peticion<RespuestaGeneracion>(`/evergreen/ideas/${encodeURIComponent(id)}/generar`, {
      metodo: "POST",
      json: cuerpo,
    }),

};
