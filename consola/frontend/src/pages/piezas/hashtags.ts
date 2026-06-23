/**
 * Utilidades de hashtags compartidas: normalizar y añadir hashtags al copy. Las usa la
 * sugerencia de hashtags del editor para inyectar al aceptar.
 */

/** Normaliza un token a un hashtag válido (con `#`, sin espacios). */
export function normalizarHashtag(valor: string): string {
  const limpio = valor.trim().replace(/^#+/, "").replace(/\s+/g, "");
  return limpio ? `#${limpio}` : "";
}

/**
 * Parsea texto libre (separado por comas, espacios o saltos de línea) en una
 * lista de hashtags normalizados y sin duplicados.
 */
export function parsearHashtags(texto: string): string[] {
  const vistos = new Set<string>();
  const salida: string[] = [];
  for (const trozo of texto.split(/[\s,]+/)) {
    const h = normalizarHashtag(trozo);
    if (h && !vistos.has(h.toLowerCase())) {
      vistos.add(h.toLowerCase());
      salida.push(h);
    }
  }
  return salida;
}

/**
 * ¿El contenido ya lleva este hashtag? Compara el cuerpo en minúscula (insensible a
 * mayúsculas, sensible a acentos: mismo criterio que el gate `falta_hashtags` del backend).
 */
export function contieneHashtag(contenido: string, tag: string): boolean {
  const objetivo = normalizarHashtag(tag).toLowerCase();
  if (!objetivo) return false;
  return parsearHashtags(contenido).some((h) => h.toLowerCase() === objetivo);
}

/**
 * Añade hashtags al final de un contenido evitando duplicados. Si el copy YA termina en hashtags
 * (un bloque de hashtags), los nuevos se unen a esa MISMA línea con un espacio; si termina en prosa,
 * se separan con un par de saltos de línea. Sin contenido previo, van tal cual.
 */
export function agregarHashtags(contenido: string, hashtags: string[]): string {
  if (hashtags.length === 0) return contenido;
  const existentes = new Set(
    parsearHashtags(contenido).map((h) => h.toLowerCase()),
  );
  const nuevos = hashtags
    .map(normalizarHashtag)
    .filter((h) => h && !existentes.has(h.toLowerCase()));
  if (nuevos.length === 0) return contenido;
  const base = contenido.replace(/\s+$/, "");
  // El copy termina en un hashtag -> los nuevos van en la misma línea (no en un párrafo aparte).
  const terminaEnHashtag = /#[\p{L}\p{N}_]+$/u.test(base);
  const sep = base ? (terminaEnHashtag ? " " : "\n\n") : "";
  return `${base}${sep}${nuevos.join(" ")}`;
}
