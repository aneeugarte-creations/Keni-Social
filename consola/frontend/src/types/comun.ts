// Tipos transversales usados por varios dominios.

/** Veredicto editorial de una pieza/generación. "" = sin veredicto.
 *  `no_verificado` (rediseño QPC): la pieza nació de una fuente que pasó la criba PERMISIVA
 *  pre-copy sin verificarse a fondo (lleva el aviso ⚠️ hasta que un humano la revise). */
export type Veredicto = "listo" | "revisar" | "no_publicar" | "no_verificado" | "";

/** Una pieza generada para una red concreta. */
export interface PiezaGenerada {
  red: string;
  contenido: string;
  caracteres: number;
}
