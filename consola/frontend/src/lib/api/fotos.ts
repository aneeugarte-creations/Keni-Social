// Fragmento del cliente API: dominio «fotos» (lanzador de la herramienta local keni-fotos).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + su tipo de respuesta.
import { descargar, peticion } from "./_core";

/** Texto del lanzador que sirve `GET /api/fotos/info` (espejo de `api/fotos.py`). */
export interface RespuestaFotosInfo {
  version: string;
  prompt_claude: string;
  comandos: string[];
  instrucciones: string[];
}

export const apiFotos = {
  // Info del lanzador: prompt de Claude, comandos y pasos para montar/ejecutar keni-fotos.
  fotosInfo: (signal?: AbortSignal) =>
    peticion<RespuestaFotosInfo>("/fotos/info", { signal }),
  // Descarga el bundle `keni-fotos.zip` (la cookie de sesión cubre el `window.open`).
  descargarFotosBundle: () => descargar("/fotos/bundle"),
};
