/**
 * Logos reales de marca para la portada del informe, importados como assets de Vite: su URL
 * es estable en el bundle, así que la `<img>` carga sin precarga asíncrona (clave para
 * rasterizar a PDF). Una marca sin entrada aquí cae al wordmark tipográfico.
 */
import claroSports from "./claro-sports.png";
import fundacion from "./fundacion.png";
import nacionGamer from "./nacion-gamer.jpg";
import piso15 from "./piso-15.jpg";
import unotv from "./unotv.png";

/** marcaId → URL del logo (vacío si la marca no tiene logo; entonces se usa el wordmark). */
export const LOGOS_MARCA: Record<string, string> = {
  unotv,
  "claro-sports": claroSports,
  "nacion-gamer": nacionGamer,
  "piso-15": piso15,
  fundacion,
};
