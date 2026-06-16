// Barrel del cliente API. Conserva la superficie `@/lib/api` (api + helpers + tipos).
// Cada dominio vive en su propio fichero (./<dominio>.ts); aquí se componen.

import { apiCatalogo } from "./catalogo";
import { apiAuth } from "./auth";
import { apiUsuarios } from "./usuarios";
import { apiSistema } from "./sistema";
import { apiConfig } from "./config";
import { apiActividad } from "./actividad";
import { apiPipelines } from "./pipelines";
import { apiGeneraciones } from "./generaciones";
import { apiPrompts } from "./prompts";
import { apiLimites } from "./limites";
import { apiPublicaciones } from "./publicaciones";
import { apiMedia } from "./media";
import { apiImagen } from "./imagen";
import { apiVideo } from "./video";
import { apiMarcaActivos } from "./marcaActivos";
import { apiPlantillasDiseno } from "./plantillasDiseno";
import { apiBloques } from "./bloques";
import { apiPlantillasMarca } from "./plantillasMarca";
import { apiRevision } from "./revision";
import { apiHashtags } from "./hashtags";
import { apiFuentes } from "./fuentes";
import { apiAlgoritmos } from "./algoritmos";
import { apiMetricool } from "./metricool";
import { apiFranjas } from "./franjas";
import { apiContenido } from "./contenido";
import { apiEtiquetas } from "./etiquetas";
import { apiEvergreen } from "./evergreen";
import { apiWebhooks } from "./webhooks";
import { apiColaboracion } from "./colaboracion";
import { apiRota } from "./rota";
import { apiParrilla } from "./parrilla";
import { apiMetricas } from "./metricas";
import { apiConexiones } from "./conexiones";
import { apiSugerencias } from "./sugerencias";
import { apiCampanias } from "./campanias";
import { apiNotificaciones } from "./notificaciones";
import { apiInsumos } from "./insumos";
import { apiPresidencia } from "./presidencia";
import { apiClips } from "./clips";
import { apiBreaking } from "./breaking";
import { apiNoticias } from "./noticias";
import { apiFuentesAcciones } from "./fuentesAcciones";
import { apiMarcas } from "./marcas";

/** Cliente fetch tipado de la Consola Keni: composición de todos los fragmentos. */
export const api = {
  ...apiCatalogo,
  ...apiAuth,
  ...apiUsuarios,
  ...apiSistema,
  ...apiConfig,
  ...apiActividad,
  ...apiPipelines,
  ...apiGeneraciones,
  ...apiPrompts,
  ...apiLimites,
  ...apiPublicaciones,
  ...apiMedia,
  ...apiImagen,
  ...apiVideo,
  ...apiMarcaActivos,
  ...apiPlantillasDiseno,
  ...apiBloques,
  ...apiPlantillasMarca,
  ...apiRevision,
  ...apiHashtags,
  ...apiFuentes,
  ...apiAlgoritmos,
  ...apiMetricool,
  ...apiFranjas,
  ...apiContenido,
  ...apiEtiquetas,
  ...apiEvergreen,
  ...apiWebhooks,
  ...apiColaboracion,
  ...apiRota,
  ...apiParrilla,
  ...apiMetricas,
  ...apiConexiones,
  ...apiSugerencias,
  ...apiCampanias,
  ...apiNotificaciones,
  ...apiInsumos,
  ...apiPresidencia,
  ...apiClips,
  ...apiBreaking,
  ...apiNoticias,
  ...apiFuentesAcciones,
  ...apiMarcas,
};

// Helpers + clase de error que consumen páginas/componentes vía `@/lib/api`.
export { mensajeError, BASE_API, urlMedia, urlS3Objeto, ApiError } from "./_core";
// Tipos públicos re-exportados (los consumen el editor y tests).
export type { ActivoMarca, PlantillaDiseno, Bloque } from "./_core";
