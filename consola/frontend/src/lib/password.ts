/**
 * Política de contraseña en el cliente. La VERDAD vive en el backend (mínimo de longitud +
 * blocklist de contraseñas comunes/filtradas + no coincidir con el usuario); aquí solo
 * replicamos el mínimo de longitud para no enviar algo que el servidor va a rechazar y
 * medimos la fortaleza de forma ORIENTATIVA para guiar al usuario.
 */

/** Longitud mínima de contraseña que exige el backend. */
export const MIN_PASSWORD = 12;

/** Nivel de fortaleza estimado: 0 = Débil … 3 = Muy fuerte. */
export type NivelFortaleza = 0 | 1 | 2 | 3;

/**
 * Estima la fortaleza de una contraseña por longitud y variedad de caracteres
 * (minúsculas, mayúsculas, dígitos, símbolos). Es orientativo: no decide si se puede enviar
 * —de eso se encarga el backend con su blocklist—, solo da una pista visual. Por debajo del
 * mínimo de longitud nunca pasa de "Débil", aunque tenga mucha variedad.
 */
export function fortalezaPassword(password: string): NivelFortaleza {
  let puntos = 0;
  if (password.length >= 12) puntos += 1;
  if (password.length >= 16) puntos += 1;
  if (password.length >= 20) puntos += 1;
  const clases = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(password)).length;
  puntos += Math.max(0, clases - 1);
  if (password.length < MIN_PASSWORD) return 0;
  if (puntos >= 5) return 3;
  if (puntos >= 3) return 2;
  return 1;
}
