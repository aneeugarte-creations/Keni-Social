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
 * Añade hashtags al final de un contenido evitando duplicados. Inserta un par
 * de saltos de línea de separación si el contenido ya tenía texto.
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
  const sep = base ? "\n\n" : "";
  return `${base}${sep}${nuevos.join(" ")}`;
}
