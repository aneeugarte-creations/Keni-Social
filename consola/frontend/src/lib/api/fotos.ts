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

/** Respuesta de `POST /api/fotos/autorizar`: la URL loopback de retorno con el token. */
export interface RespuestaFotosAutorizar {
  redirect: string;
}

export const apiFotos = {
  // Info del lanzador: versión, changelog, prompt de Claude, comandos y pasos.
  fotosInfo: (signal?: AbortSignal) =>
    peticion<RespuestaFotosInfo>("/fotos/info", { signal }),
  // Descarga el `.dmg` de la app de escritorio Tauri (macOS): vía principal.
  descargarFotosApp: () => descargar("/fotos/app"),
  // Descarga el código `keni-fotos.zip`: modo avanzado (montar con Claude).
  descargarFotosBundle: () => descargar("/fotos/bundle"),
  // Login OPCIONAL del escritorio: emite el token y devuelve la URL loopback de retorno
  // (`cb?token=&state=`), a la que la página redirige el navegador.
  autorizarFotos: (datos: { cb: string; state: string }) =>
    peticion<RespuestaFotosAutorizar>("/fotos/autorizar", { metodo: "POST", json: datos }),
};
