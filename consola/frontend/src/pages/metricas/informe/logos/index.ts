/**
 * Logos reales de marca para la portada del informe, INCRUSTADOS como data-URI (`?inline` de
 * Vite) dentro del chunk del deck: si el JS de la exportación cargó, el logo existe sí o sí.
 * Un asset con URL de hash puede dar 404 en una pestaña abierta desde antes de un deploy
 * (el hash viejo ya no se sirve) y la portada saldría sin marca; el data-URI no viaja por red.
 * Una marca sin entrada aquí cae al wordmark tipográfico.
 */
import claroSports from "./claro-sports.png?inline";
import fundacion from "./fundacion.png?inline";
import nacionGamer from "./nacion-gamer.png?inline";
import piso15 from "./piso-15.png?inline";
import unotv from "./unotv.png?inline";

/** marcaId → data-URI del logo (vacío si la marca no tiene logo; entonces se usa el wordmark). */
export const LOGOS_MARCA: Record<string, string> = {
  unotv,
  "claro-sports": claroSports,
  "nacion-gamer": nacionGamer,
  "piso-15": piso15,
  fundacion,
};
