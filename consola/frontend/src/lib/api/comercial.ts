// Fragmento del cliente API: dominio «comercial». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query, descargar } from "./_core";
import type {
  CuerpoActualizarComercial,
  CuerpoCrearComercial,
  FiltrosComercial,
  OpcionesComercial,
  RespuestaMensaje,
  RespuestaPostsComercial,
  RespuestaPublicacionComercial,
  RespuestaPublicacionesComercial,
  RespuestaRefrescarComercial,
  RespuestaReporteComercial,
} from "@/types";

export const apiComercial = {
  // --- Comercial (seguimiento de publicaciones comerciales) ---
  comercialOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesComercial>("/comercial/opciones", { signal }),
  comercialPosts: (
    params: { marca?: string; red?: string; rango?: string } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaPostsComercial>(`/comercial/posts${query(params)}`, { signal }),
  comerciales: (filtros: FiltrosComercial = {}, signal?: AbortSignal) =>
    peticion<RespuestaPublicacionesComercial>(`/comercial/publicaciones${query(filtros)}`, {
      signal,
      validador: "RespuestaPublicacionesComercial",
    }),
  comercial: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaPublicacionComercial>(`/comercial/publicaciones/${encodeURIComponent(id)}`, {
      signal,
      validador: "RespuestaPublicacionComercial",
      muestrear: false,
    }),
  crearComercial: (cuerpo: CuerpoCrearComercial) =>
    peticion<RespuestaPublicacionComercial>("/comercial/publicaciones", {
      metodo: "POST",
      json: cuerpo,
    }),
  actualizarComercial: (id: string, cuerpo: CuerpoActualizarComercial) =>
    peticion<RespuestaPublicacionComercial>(`/comercial/publicaciones/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarComercial: (id: string) =>
    peticion<RespuestaMensaje>(`/comercial/publicaciones/${encodeURIComponent(id)}`, {
      metodo: "DELETE",
    }),
  refrescarComercial: (id: string) =>
    peticion<RespuestaPublicacionComercial>(
      `/comercial/publicaciones/${encodeURIComponent(id)}/refrescar`,
      { metodo: "POST" },
    ),
  refrescarComerciales: () =>
    peticion<RespuestaRefrescarComercial>("/comercial/refrescar", { metodo: "POST" }),
  reporteComercial: (
    params: { publicacion?: string; campania?: string; cliente?: string },
    signal?: AbortSignal,
  ) => peticion<RespuestaReporteComercial>(`/comercial/reporte${query(params)}`, { signal }),
  descargarReporteComercial: (params: { publicacion?: string; campania?: string; cliente?: string }) =>
    descargar(`/comercial/reporte${query({ ...params, formato: "md" })}`),

};
