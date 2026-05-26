/**
 * Utilidades de formato es-MX compartidas por toda la consola.
 *
 * Centraliza el formateo de números, porcentajes, variaciones, costes y
 * duraciones para que todas las páginas hablen el mismo idioma visual:
 * separadores de miles mexicanos y abreviaturas legibles (mil / M) en KPIs,
 * ejes de gráficas, tablas y tooltips.
 *
 * Antes estas funciones vivían en `pages/metricas/formato.ts`; ahora ese
 * módulo re-exporta desde aquí para mantener la compatibilidad de importes
 * existentes mientras se migra progresivamente al path canónico `@/lib/formato`.
 */

/** Formateador base es-MX con separador de miles (ej. 1234567 → "1,234,567"). */
const nfEntero = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });

/** Formateador compacto es-MX (ej. 221621046 → "221.6 M"). */
const nfCompacto = new Intl.NumberFormat("es-MX", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/**
 * Número compacto y legible. Para valores < 1000 muestra el entero tal cual;
 * a partir de ahí abrevia con "mil" / "M" en español de México.
 * Ej.: 221621046 → "221.6 M", 1830 → "1.8 mil", 842 → "842".
 */
export function numeroCompacto(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  if (Math.abs(valor) < 1000) return nfEntero.format(valor);
  return nfCompacto.format(valor);
}

/** Número completo con separadores de miles (para tablas y tooltips). */
export function numeroCompleto(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  return nfEntero.format(valor);
}

/**
 * Porcentaje con un decimal y el símbolo "%". El backend ya entrega el valor en
 * puntos porcentuales (ej. 1.8 → "1.8 %"), así que no multiplicamos por 100.
 */
export function porcentaje(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  return `${valor.toLocaleString("es-MX", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} %`;
}

/**
 * Variación porcentual con signo explícito (+/−) y un decimal.
 * Ej.: 12.345 → "+12.3 %", -4 → "−4.0 %", 0 → "0.0 %".
 */
export function variacion(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  const abs = Math.abs(valor).toLocaleString("es-MX", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const signo = valor > 0 ? "+" : valor < 0 ? "−" : "";
  return `${signo}${abs} %`;
}

/**
 * Coste en dólares estadounidenses (es-MX). Usa más decimales para importes
 * pequeños típicos de un run para no perder precisión visual.
 * Ej.: 0.0381 → "$0.038", 1.5 → "$1.50", 0 → "$0.00".
 */
export function costeUsd(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  // Importes muy pequeños (< $0.10): 3 decimales; el resto, 2.
  const decimales = Math.abs(valor) > 0 && Math.abs(valor) < 0.1 ? 3 : 2;
  return valor.toLocaleString("es-MX", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
}

/**
 * Duración legible a partir de milisegundos (es-MX).
 * Ej.: 850 → "0.9 s", 4200 → "4.2 s", 95000 → "1 min 35 s".
 */
export function duracion(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const segundosTotales = ms / 1000;
  if (segundosTotales < 60) {
    return `${segundosTotales.toLocaleString("es-MX", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    })} s`;
  }
  const minutos = Math.floor(segundosTotales / 60);
  const segundos = Math.round(segundosTotales % 60);
  return `${minutos} min ${segundos} s`;
}
