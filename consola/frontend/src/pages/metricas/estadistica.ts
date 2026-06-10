/**
 * Estadística descriptiva de la sección "Correlación" (seguidores ↔ piezas).
 *
 * Se usa SPEARMAN (ρ, correlación de rangos) y NO Pearson, a propósito: los pares
 * día–red son CONTEOS con outliers fuertes (un día viral dispara `seguidores_ganados`
 * órdenes de magnitud) y Pearson se deja arrastrar por un solo punto extremo; la
 * correlación de rangos mide la relación monótona y es robusta a esas colas. Los
 * empates (frecuentes: `n_posts` repite valores pequeños) se resuelven con rango
 * promedio, la corrección estándar.
 *
 * La UI exige además una n mínima (`N_MINIMA_CORRELACION`): por debajo, el
 * coeficiente es tan inestable que mostrarlo induce a error («n insuficiente para
 * estimar correlación» en su lugar).
 */

/** Pares mínimos para mostrar un coeficiente (por debajo, ρ no es estimable con
 * ninguna fiabilidad y se suprime). */
export const N_MINIMA_CORRELACION = 8;

/** Rangos 1..n de cada valor, con PROMEDIO en los empates (Spearman estándar). */
function rangosPromedio(valores: number[]): number[] {
  const orden = valores
    .map((v, i) => ({ v, i }))
    .sort((a, b) => a.v - b.v);
  const rangos = new Array<number>(valores.length);
  let i = 0;
  while (i < orden.length) {
    let j = i;
    while (j + 1 < orden.length && orden[j + 1].v === orden[i].v) j++;
    // Rango promedio del grupo empatado (rangos 1-based i+1..j+1).
    const r = (i + j + 2) / 2;
    for (let k = i; k <= j; k++) rangos[orden[k].i] = r;
    i = j + 1;
  }
  return rangos;
}

/** Pearson de dos vectores parejos. null si n < 2 o alguna varianza es 0
 * (coeficiente indefinido: no se inventa un número). */
function pearson(xs: number[], ys: number[]): number | null {
  const n = xs.length;
  if (n !== ys.length || n < 2) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0;
  let sxx = 0;
  let syy = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    sxy += dx * dy;
    sxx += dx * dx;
    syy += dy * dy;
  }
  if (sxx === 0 || syy === 0) return null;
  return sxy / Math.sqrt(sxx * syy);
}

/**
 * ρ de Spearman = Pearson sobre los RANGOS (con rango promedio en empates).
 * null si no es calculable (n < 2 o algún vector constante, p. ej. todos los
 * días con el mismo nº de piezas).
 */
export function spearman(xs: number[], ys: number[]): number | null {
  if (xs.length !== ys.length || xs.length < 2) return null;
  return pearson(rangosPromedio(xs), rangosPromedio(ys));
}
