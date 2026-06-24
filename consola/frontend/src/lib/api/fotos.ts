// Fragmento del cliente API: dominio «fotos» (lanzador de la herramienta local keni-fotos).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + su tipo de respuesta.
import { descargar, peticion } from "./_core";

/** Texto del lanzador que sirve `GET /api/fotos/info` (espejo de `api/fotos.py`). */
export interface RespuestaFotosInfo {
  version: string;
  changelog: string[];
  prompt_claude: string;
  comandos: string[];
  instrucciones: string[];
}

export const apiFotos = {
  // Info del lanzador: versión, changelog, prompt de Claude, comandos y pasos.
  fotosInfo: (signal?: AbortSignal) =>
    peticion<RespuestaFotosInfo>("/fotos/info", { signal }),
  // Descarga la app de escritorio `keni-fotos-app.zip` (.app): vía principal.
  descargarFotosApp: () => descargar("/fotos/app"),
  // Descarga el payload `keni-fotos.zip`: modo avanzado (Claude) / auto-update del .app.
  descargarFotosBundle: () => descargar("/fotos/bundle"),
};
