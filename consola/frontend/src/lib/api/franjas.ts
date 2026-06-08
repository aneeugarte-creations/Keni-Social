// Fragmento del cliente API: dominio «franjas». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoCrearFranja,
  CuerpoGuardarCadencia,
  RespuestaCadencia,
  RespuestaCadencias,
  RespuestaFranja,
  RespuestaFranjas,
  RespuestaMensaje,
} from "@/types";

export const apiFranjas = {
  // --- Franjas (colas) ---
  franjas: (signal?: AbortSignal) => peticion<RespuestaFranjas>("/franjas", { signal }),
  crearFranja: (cuerpo: CuerpoCrearFranja) =>
    peticion<RespuestaFranja>("/franjas", { metodo: "POST", json: cuerpo }),
  eliminarFranja: (id: string) =>
    peticion<RespuestaMensaje>(`/franjas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Cadencia por red (margen entre posts) ---
  cadencias: (signal?: AbortSignal) =>
    peticion<RespuestaCadencias>("/cadencias", { signal }),
  guardarCadencia: (cuerpo: CuerpoGuardarCadencia) =>
    peticion<RespuestaCadencia>("/cadencias", { metodo: "PUT", json: cuerpo }),
  eliminarCadencia: (id: string) =>
    peticion<RespuestaMensaje>(`/cadencias/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

};
