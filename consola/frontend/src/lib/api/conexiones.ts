// Fragmento del cliente API: dominio «conexiones». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoGuardarConexionImagen,
  CuerpoGuardarMetricool,
  CuerpoGuardarModeloImagen,
  CuerpoPerfilesMetricool,
  RespuestaConexionImagen,
  RespuestaGuardarConexionImagen,
  RespuestaGuardarMetricool,
  RespuestaGuardarModeloImagen,
  RespuestaMensaje,
  RespuestaMetricool,
  RespuestaPerfilesMetricool,
  RespuestaProbarConexionImagen,
  RespuestaProbarMetricool,
} from "@/types";

export const apiConexiones = {
  // --- Conexiones (imagen IA + tokens de redes) ---
  // Los secretos son write-only: solo se envían (PUT); del servidor llega
  // únicamente el estado y, para la imagen, una pista no sensible.
  conexionImagen: (signal?: AbortSignal) =>
    peticion<RespuestaConexionImagen>("/conexiones/imagen", { signal }),
  guardarConexionImagen: (cuerpo: CuerpoGuardarConexionImagen) =>
    peticion<RespuestaGuardarConexionImagen>("/conexiones/imagen", { metodo: "PUT", json: cuerpo }),
  guardarModeloImagen: (cuerpo: CuerpoGuardarModeloImagen) =>
    peticion<RespuestaGuardarModeloImagen>("/conexiones/imagen/modelo", {
      metodo: "PUT",
      json: cuerpo,
    }),
  probarConexionImagen: () =>
    peticion<RespuestaProbarConexionImagen>("/conexiones/imagen/probar", { metodo: "POST" }),
  eliminarConexionImagen: () =>
    peticion<RespuestaMensaje>("/conexiones/imagen", { metodo: "DELETE" }),

  // Metricool por marca: cada marca es una cuenta Metricool con su propio token.
  // El user_token es write-only: solo se envía (PUT); del servidor llega el estado.
  conexionesMetricool: (signal?: AbortSignal) =>
    peticion<RespuestaMetricool>("/conexiones/metricool", { signal }),
  // Descubre las marcas (blogId) de un token. NO persiste nada y el token nunca vuelve.
  descubrirPerfilesMetricool: (cuerpo: CuerpoPerfilesMetricool) =>
    peticion<RespuestaPerfilesMetricool>("/conexiones/metricool/perfiles", {
      metodo: "POST",
      json: cuerpo,
    }),
  guardarMetricool: (marca: string, cuerpo: CuerpoGuardarMetricool) =>
    peticion<RespuestaGuardarMetricool>(`/conexiones/metricool/${encodeURIComponent(marca)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarMetricool: (marca: string) =>
    peticion<RespuestaMensaje>(`/conexiones/metricool/${encodeURIComponent(marca)}`, {
      metodo: "DELETE",
    }),
  probarMetricool: (marca: string) =>
    peticion<RespuestaProbarMetricool>(
      `/conexiones/metricool/${encodeURIComponent(marca)}/probar`,
      { metodo: "POST" },
    ),

};
