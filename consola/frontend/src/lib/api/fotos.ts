// Fragmento del cliente API: dominio «fotos» (lanzador de la herramienta local keni-fotos).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + su tipo de respuesta.
import { descargar, peticion } from "./_core";

/** Respuesta de `POST /api/fotos/autorizar`: la URL loopback de retorno con el token. */
export interface RespuestaFotosAutorizar {
  redirect: string;
}

export const apiFotos = {
  // Descarga el `.dmg` de la app de escritorio Tauri (macOS): vía principal.
  descargarFotosApp: () => descargar("/fotos/app"),
  // Login OPCIONAL del escritorio: emite el token y devuelve la URL loopback de retorno
  // (`cb?token=&state=`), a la que la página redirige el navegador.
  autorizarFotos: (datos: { cb: string; state: string }) =>
    peticion<RespuestaFotosAutorizar>("/fotos/autorizar", { metodo: "POST", json: datos }),
};
