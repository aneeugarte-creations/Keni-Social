/**
 * Utilidades de formato es-MX para el dashboard de Métricas.
 *
 * Centraliza el formateo de números, porcentajes y variaciones para que toda la
 * página hable el mismo idioma visual: separadores de miles mexicanos y
 * abreviaturas legibles (mil / M) en KPIs y ejes de gráficas.
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
