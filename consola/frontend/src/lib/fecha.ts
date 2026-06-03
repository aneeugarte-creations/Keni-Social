/**
 * Fechas y horas en zona CDMX (America/Mexico_City) — utilidad central.
 *
 * CONVENCIÓN DEL SISTEMA (importante): el backend SELLA y ALMACENA todos los
 * instantes en UTC. El servidor corre en UTC, así que un timestamp ISO sin zona
 * explícita ("2026-06-03T22:00:00") ES un instante UTC. La consola SIEMPRE los
 * muestra en hora de Ciudad de México, sin depender de la zona del navegador
 * (un revisor desde otra zona ve la MISMA hora CDMX que el equipo en México).
 *
 * Aquí se centraliza el parseo (naive → UTC) y el formateo (→ CDMX) para que toda
 * la app hable la misma hora. Las páginas no deben volver a hacer `new Date(iso)` +
 * `Intl.DateTimeFormat` sin `timeZone`: eso reintroduce el bug de "se ve en UTC".
 */

/** Zona horaria de operación (CDMX). Única fuente del nombre de zona. */
export const ZONA_CDMX = "America/Mexico_City";

/** Detecta si un ISO trae marca de zona explícita ("Z" o "+/-HH:MM"). */
const RE_CON_ZONA = /(?:Z|[+-]\d{2}:?\d{2})$/;

/**
 * Parsea un ISO a `Date`. Si la cadena trae componente horario pero NO trae zona,
 * se asume UTC (convención del backend: instante naive = UTC del servidor). Devuelve
 * `null` para cadena vacía o fecha inválida.
 */
export function aInstante(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const txt = String(iso).trim();
  if (!txt) return null;
  // Con hora y sin zona → anclar a UTC añadiendo "Z". Fechas solo-día ("YYYY-MM-DD")
  // las parsea el motor como UTC por spec; las tratamos aparte en `formatearDia`.
  const norm = txt.includes("T") && !RE_CON_ZONA.test(txt) ? `${txt}Z` : txt;
  const d = new Date(norm);
  return Number.isNaN(d.getTime()) ? null : d;
}

// Formateadores es-MX anclados a CDMX (cacheados: construir un Intl.DateTimeFormat
// no es gratis y estos se usan en tablas/listas con muchas filas).
const _fFechaHora = new Intl.DateTimeFormat("es-MX", {
  timeZone: ZONA_CDMX,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const _fFechaHoraCorta = new Intl.DateTimeFormat("es-MX", {
  timeZone: ZONA_CDMX,
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const _fFecha = new Intl.DateTimeFormat("es-MX", {
  timeZone: ZONA_CDMX,
  day: "2-digit",
  month: "short",
  year: "numeric",
});
const _fFechaCorta = new Intl.DateTimeFormat("es-MX", {
  timeZone: ZONA_CDMX,
  day: "2-digit",
  month: "short",
});
const _fHora = new Intl.DateTimeFormat("es-MX", {
  timeZone: ZONA_CDMX,
  hour: "2-digit",
  minute: "2-digit",
});

/** Fecha + hora CDMX con año. Ej.: "03 jun 2026, 16:00". "" / inválida → "—" o el crudo. */
export function formatearFechaHora(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = aInstante(iso);
  return d ? _fFechaHora.format(d) : String(iso);
}

/** Fecha + hora CDMX SIN año (compacta para listas). Ej.: "03 jun, 16:00". */
export function formatearFechaHoraCorta(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = aInstante(iso);
  return d ? _fFechaHoraCorta.format(d) : String(iso);
}

/** Solo fecha CDMX (con año). Ej.: "03 jun 2026". */
export function formatearFecha(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = aInstante(iso);
  return d ? _fFecha.format(d) : String(iso);
}

/** Solo fecha CDMX corta (sin año). Ej.: "03 jun". */
export function formatearFechaCorta(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = aInstante(iso);
  return d ? _fFechaCorta.format(d) : String(iso);
}

/** Solo hora CDMX (HH:mm). Ej.: "16:00". */
export function formatearHora(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = aInstante(iso);
  return d ? _fHora.format(d) : "";
}

/**
 * Día legible CDMX a partir de `YYYY-MM-DD` (sin componente horario). Se ancla a
 * mediodía UTC para que el día del calendario no se desplace al pasarlo a CDMX.
 * Ej.: "2026-06-03" → "03 jun 2026". Tolera valores inesperados.
 */
export function formatearDia(dia: string | null | undefined): string {
  if (!dia) return "—";
  const d = new Date(`${dia}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? String(dia) : _fFecha.format(d);
}

/**
 * Tiempo relativo legible en es-MX (p. ej. "hace 5 min", "en 2 h"). Es
 * independiente de zona (compara instantes); tolera vacíos/ inválidos → "".
 */
export function tiempoRelativo(iso: string | null | undefined): string {
  const d = aInstante(iso);
  if (!d) return "";
  const seg = Math.round((d.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seg);
  const rtf = new Intl.RelativeTimeFormat("es-MX", { numeric: "auto" });
  const divisiones: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [3600, "minute"],
    [86400, "hour"],
    [604800, "day"],
    [2629800, "week"],
    [31557600, "month"],
    [Infinity, "year"],
  ];
  const factores: Record<string, number> = {
    second: 1,
    minute: 60,
    hour: 3600,
    day: 86400,
    week: 604800,
    month: 2629800,
    year: 31557600,
  };
  for (const [umbral, unidad] of divisiones) {
    if (abs < umbral) {
      return rtf.format(Math.round(seg / factores[unidad]), unidad);
    }
  }
  return rtf.format(Math.round(seg / factores.year), "year");
}

/**
 * Offset (en minutos) de CDMX respecto a UTC para un instante dado. Se calcula con
 * `Intl` (robusto ante cualquier cambio de horario de verano), no con una constante
 * fija. Positivo si CDMX va por delante de UTC; negativo si va por detrás (lo normal).
 */
function offsetCdmxMin(fecha: Date): number {
  const dtf = new Intl.DateTimeFormat("en-US", {
    timeZone: ZONA_CDMX,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const p: Record<string, string> = {};
  for (const part of dtf.formatToParts(fecha)) {
    if (part.type !== "literal") p[part.type] = part.value;
  }
  const comoSiUtc = Date.UTC(
    Number(p.year),
    Number(p.month) - 1,
    Number(p.day),
    Number(p.hour),
    Number(p.minute),
    Number(p.second),
  );
  return (comoSiUtc - fecha.getTime()) / 60000;
}

/**
 * Convierte un ISO (instante UTC) al valor de un `<input type="datetime-local">`
 * (`YYYY-MM-DDTHH:mm`) expresado en HORA CDMX (no en la del navegador). "" si no
 * hay fecha válida.
 */
export function isoADatetimeLocal(iso: string | null | undefined): string {
  const d = aInstante(iso);
  if (!d) return "";
  // sv-SE da "YYYY-MM-DD HH:mm"; sustituimos el espacio por "T" para datetime-local.
  const dtf = new Intl.DateTimeFormat("sv-SE", {
    timeZone: ZONA_CDMX,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  return dtf.format(d).replace(" ", "T");
}

/**
 * Convierte un valor de `<input type="datetime-local">` —interpretado como HORA
 * CDMX— a un instante ISO 8601 UTC (con "Z"). Devuelve `null` para vacío/ inválido.
 * Así el usuario programa "18:00 CDMX" y el backend recibe el instante UTC correcto,
 * sin importar la zona de su navegador.
 */
export function datetimeLocalAIso(valor: string): string | null {
  if (!valor) return null;
  const completo = valor.length === 16 ? `${valor}:00` : valor; // añade segundos si faltan
  // Interpretamos los componentes COMO SI fueran UTC y luego corregimos por el
  // offset real de CDMX en ese instante (CDMX no aplica horario de verano: -06:00).
  const ingenuoUtcMs = new Date(`${completo}Z`).getTime();
  if (Number.isNaN(ingenuoUtcMs)) return null;
  const off = offsetCdmxMin(new Date(ingenuoUtcMs));
  return new Date(ingenuoUtcMs - off * 60000).toISOString();
}
