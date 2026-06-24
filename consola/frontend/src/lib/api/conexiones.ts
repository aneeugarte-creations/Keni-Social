// Fragmento del cliente API: dominio «conexiones». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoCanalPostproxy,
  CuerpoAppGoogleAnalytics,
  CuerpoCanjearGoogleAnalytics,
  CuerpoConectarGoogleAnalytics,
  CuerpoConectarPostproxy,
  CuerpoGrupoPostproxy,
  CuerpoGuardarConexionImagen,
  CuerpoGuardarMetricool,
  CuerpoGuardarModeloImagen,
  CuerpoGuardarPostproxy,
  CuerpoPerfilesMetricool,
  CuerpoPropiedadGoogleAnalytics,
  RespuestaAppGoogleAnalytics,
  RespuestaCanalPostproxy,
  RespuestaCanjearGoogleAnalytics,
  RespuestaConectarGoogleAnalytics,
  RespuestaConectarPostproxy,
  RespuestaConexionImagen,
  RespuestaGoogleAnalytics,
  RespuestaGrupoPostproxy,
  RespuestaGuardarGoogleAnalytics,
  RespuestaGuardarConexionImagen,
  RespuestaGuardarMetricool,
  RespuestaGuardarModeloImagen,
  RespuestaGuardarPostproxy,
  RespuestaMensaje,
  RespuestaMetricool,
  RespuestaPerfilesMetricool,
  RespuestaPostproxy,
  RespuestaProbarConexionImagen,
  RespuestaProbarGoogleAnalytics,
  RespuestaProbarMetricool,
  RespuestaProbarPostproxy,
  RespuestaPropiedadesGoogleAnalytics,
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

  // Postproxy: UNA api_key GLOBAL (write-only) + un grupo de perfiles por marca.
  // La api_key solo se envía (PUT); del servidor llega el estado + una pista no
  // sensible. Conectar una red es un OAuth: el back devuelve la URL a abrir.
  conexionesPostproxy: (signal?: AbortSignal) =>
    peticion<RespuestaPostproxy>("/conexiones/postproxy", { signal }),
  guardarPostproxy: (cuerpo: CuerpoGuardarPostproxy) =>
    peticion<RespuestaGuardarPostproxy>("/conexiones/postproxy", {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarPostproxy: () =>
    peticion<RespuestaMensaje>("/conexiones/postproxy", { metodo: "DELETE" }),
  probarPostproxy: () =>
    peticion<RespuestaProbarPostproxy>("/conexiones/postproxy/probar", { metodo: "POST" }),
  // Crea (o regenera) el grupo de perfiles de una marca en Postproxy.
  grupoPostproxy: (marca: string, cuerpo: CuerpoGrupoPostproxy = {}) =>
    peticion<RespuestaGrupoPostproxy>(
      `/conexiones/postproxy/${encodeURIComponent(marca)}/grupo`,
      { metodo: "PUT", json: cuerpo },
    ),
  // Inicia el OAuth para conectar una red de una marca; devuelve la URL a abrir.
  conectarPostproxy: (marca: string, cuerpo: CuerpoConectarPostproxy) =>
    peticion<RespuestaConectarPostproxy>(
      `/conexiones/postproxy/${encodeURIComponent(marca)}/conectar`,
      { metodo: "POST", json: cuerpo },
    ),
  // Fija el canal de publicación de una marca (Metricool | Postproxy).
  canalPostproxy: (marca: string, canal: string) =>
    peticion<RespuestaCanalPostproxy>(
      `/conexiones/postproxy/${encodeURIComponent(marca)}/canal`,
      { metodo: "PUT", json: { canal } as CuerpoCanalPostproxy },
    ),
  // Desconecta un perfil concreto de Postproxy (por su id de perfil).
  eliminarPerfilPostproxy: (perfilId: string) =>
    peticion<RespuestaMensaje>(
      `/conexiones/postproxy/perfil/${encodeURIComponent(perfilId)}`,
      { metodo: "DELETE" },
    ),

  // Google Analytics (GA4): UNA app OAuth GLOBAL (client_secret write-only) que,
  // una vez conectada por OAuth, se mapea a una propiedad GA4 por marca. El secret
  // solo se envía; del servidor llega el estado + el client_id (no secreto).
  conexionesGoogleAnalytics: (signal?: AbortSignal) =>
    peticion<RespuestaGoogleAnalytics>("/conexiones/google-analytics", { signal }),
  guardarAppGoogleAnalytics: (cuerpo: CuerpoAppGoogleAnalytics) =>
    peticion<RespuestaAppGoogleAnalytics>("/conexiones/google-analytics/app", {
      metodo: "PUT",
      json: cuerpo,
    }),
  // Inicia el OAuth; devuelve la URL de Google a abrir en el popup.
  conectarGoogleAnalytics: (cuerpo: CuerpoConectarGoogleAnalytics) =>
    peticion<RespuestaConectarGoogleAnalytics>("/conexiones/google-analytics/conectar", {
      metodo: "POST",
      json: cuerpo,
    }),
  // Canjea el código del OAuth por el refresh_token (lo llama la ventana de retorno).
  canjearGoogleAnalytics: (cuerpo: CuerpoCanjearGoogleAnalytics) =>
    peticion<RespuestaCanjearGoogleAnalytics>("/conexiones/google-analytics/canjear", {
      metodo: "POST",
      json: cuerpo,
    }),
  // Lista las propiedades GA4 de la cuenta conectada (para mapearlas por marca).
  propiedadesGoogleAnalytics: (signal?: AbortSignal) =>
    peticion<RespuestaPropiedadesGoogleAnalytics>(
      "/conexiones/google-analytics/propiedades",
      { signal },
    ),
  guardarPropiedadGoogleAnalytics: (marca: string, cuerpo: CuerpoPropiedadGoogleAnalytics) =>
    peticion<RespuestaGuardarGoogleAnalytics>(
      `/conexiones/google-analytics/${encodeURIComponent(marca)}`,
      { metodo: "PUT", json: cuerpo },
    ),
  eliminarPropiedadGoogleAnalytics: (marca: string) =>
    peticion<RespuestaMensaje>(
      `/conexiones/google-analytics/${encodeURIComponent(marca)}`,
      { metodo: "DELETE" },
    ),
  probarGoogleAnalytics: (marca: string) =>
    peticion<RespuestaProbarGoogleAnalytics>(
      `/conexiones/google-analytics/${encodeURIComponent(marca)}/probar`,
      { metodo: "POST" },
    ),
  // Desconecta la app (borra el refresh_token global).
  eliminarGoogleAnalytics: () =>
    peticion<RespuestaMensaje>("/conexiones/google-analytics", { metodo: "DELETE" }),
};
