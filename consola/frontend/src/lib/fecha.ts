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
 * ¿Una pieza `programado` ya se pasó de su hora sin publicarse?
 *
 * El instante es absoluto (la conversión de zona ya está en `aInstante`/UTC), así que
 * comparamos contra "ahora" sin más. Solo aplica a `programado`: una `publicado` no está
 * vencida, y una `borrador`/`aprobado` no tiene compromiso de hora.
 */
export function estaVencida(
  estado: string | null | undefined,
  fechaProgramada: string | null | undefined,
): boolean {
  if (estado !== "programado") return false;
  const d = aInstante(fechaProgramada);
  return d != null && d.getTime() < Date.now();
}

// "YYYY-MM-DD" en CDMX (en-CA formatea ISO). Cacheado como el resto de formateadores.
const _fDiaIso = new Intl.DateTimeFormat("en-CA", {
  timeZone: ZONA_CDMX,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/**
 * El día calendario (`YYYY-MM-DD`) de un instante, en zona CDMX (no la del navegador
 * ni UTC). Base de `hoyCDMX` y de la aritmética de semanas de la rota.
 */
export function diaCDMX(d: Date): string {
  return _fDiaIso.format(d);
}

/**
 * El día de HOY (`YYYY-MM-DD`) en zona CDMX, independiente de la zona del navegador.
 * Úsalo en vez de `new Date().toISOString().slice(0, 10)`: eso da el día UTC, que entre
 * las 18:00 y la medianoche CDMX ya es "mañana" (descuadra cajones del día, fechas por
 * defecto de formularios, etc.).
 */
export function hoyCDMX(): string {
  return diaCDMX(new Date());
}

// "HH:MM" → minutos del día. Normaliza la hora «de pared» CDMX antes de anclarla a un instante.
function _aMinutos(hhmm: string | null | undefined): number | null {
  if (!hhmm) return null;
  const m = /^(\d{1,2}):(\d{2})/.exec(String(hhmm).trim());
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

/** Dónde cae un evento respecto a AHORA (CDMX): antes (futuro) · durante · después. */
export type PosicionTemporal = "antes" | "durante" | "despues";

/**
 * Sitúa un evento con `fecha` (YYYY-MM-DD) y `hora` opcional (HH:MM, CDMX) respecto a
 * AHORA en CDMX. `ventanaMin` = cuánto dura «durante» desde la hora (def. 180 ≈ un partido).
 * Sin fecha → `null` (no se puede situar). Base del semáforo de cobertura: el equipo no marca
 * estados a mano; el color se deriva del calendario (gris/ámbar/verde).
 *
 * Con hora concreta la fase se calcula con INSTANTES reales (vía `minutosHastaEvento`), NO
 * comparando el string de día: un partido nocturno (saque >21:00) seguía «en vivo» pasada la
 * medianoche, pero la vieja comparación `dia < hoy` lo mandaba a «después»/«Cubierto» a las 00:00.
 */
export function posicionTemporal(
  fecha: string | null | undefined,
  hora?: string | null,
  ventanaMin = 180,
): PosicionTemporal | null {
  if (!fecha) return null;
  // Sin hora concreta NO hay instante de saque al que anclar una ventana: se sitúa por DÍA CDMX
  // (futuro → antes, hoy → en curso todo el día, pasado → después). Al situar por día (sin ventana
  // horaria) el borde de medianoche no aplica.
  if (_aMinutos(hora) == null) {
    const dia = String(fecha).slice(0, 10);
    const hoy = hoyCDMX();
    if (dia > hoy) return "antes";
    if (dia < hoy) return "despues";
    return "durante";
  }
  // Con hora: fase por instantes reales. `min` = minutos desde AHORA hasta el saque; positivo aún
  // no empieza, 0/negativo ya arrancó. Dura «durante» mientras no se rebase la ventana (cruza la
  // medianoche sin saltar a «después»).
  const min = minutosHastaEvento(fecha, hora);
  if (min == null) return null;
  if (min > 0) return "antes";
  return min > -ventanaMin ? "durante" : "despues";
}

/**
 * Minutos (CDMX) desde AHORA hasta el INICIO de un evento con `fecha` (YYYY-MM-DD) y `hora`
 * opcional (HH:MM, CDMX). Positivo = aún no empieza; negativo = ya arrancó/pasó; `null` sin
 * fecha. Reusa la maquinaria CDMX: normaliza la hora con `_aMinutos` y convierte la hora de
 * pared CDMX a un INSTANTE con `datetimeLocalAIso`, así el cómputo es de instantes reales (cruza
 * medianoche/meses sin líos de pared). Sin hora concreta se ancla al inicio del día CDMX (00:00).
 * Es el reloj maestro del aviso «empieza en X» (cuenta atrás al pitido), hermano de
 * `posicionTemporal`: ésta dice EN QUÉ FASE cae el evento (antes/durante/después); ésta, CUÁNTO falta.
 */
export function minutosHastaEvento(
  fecha: string | null | undefined,
  hora?: string | null,
): number | null {
  if (!fecha) return null;
  const dia = String(fecha).slice(0, 10);
  const min = _aMinutos(hora) ?? 0; // sin hora → arranque del día (00:00)
  const hhmm = `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
  const inicio = aInstante(datetimeLocalAIso(`${dia}T${hhmm}`));
  return inicio ? Math.round((inicio.getTime() - Date.now()) / 60000) : null;
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
 * Tiempo relativo legible en es-MX (p. ej. "hace 5 minutos", "en 2 horas"). Es
 * independiente de zona (compara instantes); tolera vacíos/ inválidos → "".
 *
 * ES LA ÚNICA implementación de tiempo relativo de la consola: Pipelines, Cobertura y
 * Monitor tenían copias locales divergentes ("hace 2 h" / "hace unos segundos") y el
 * mismo instante se leía distinto según la página. Para edades ya medidas en segundos
 * (los `*_hace_s` del monitor de cola) usa `haceSegundos`.
 */
export function tiempoRelativo(iso: string | null | undefined): string {
  const d = aInstante(iso);
  if (!d) return "";
  return _relativo(Math.round((d.getTime() - Date.now()) / 1000));
}

/**
 * Tiempo relativo a partir de una EDAD en segundos ya calculada por el backend
 * (p. ej. `encolado_hace_s`): "hace 5 segundos", "hace 3 minutos". `null` → "—".
 */
export function haceSegundos(segundos: number | null | undefined): string {
  if (segundos == null || !Number.isFinite(segundos)) return "—";
  return _relativo(-Math.round(segundos));
}

/** Cuerpo compartido: delta en segundos (negativo = pasado) → texto es-MX vía Intl. */
function _relativo(seg: number): string {
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


// --- Horas sueltas "HH:MM" entre CDMX y UTC -----------------------------------
// CDMX es UTC-6 FIJO (México abolió el horario de verano en 2022): la conversión de una
// hora sin fecha es un desplazamiento constante. Las usan los editores de horarios (plan
// por línea, cadencia) y los placeholders del calendario: el backend almacena UTC, el
// equipo piensa en hora de Ciudad de México.

const OFFSET_CDMX_H = 6;

/** "HH:MM" almacenada (UTC) → "HH:MM" CDMX. */
export function horaUtcACdmx(hora: string): string {
  const [h, m] = hora.split(":").map(Number);
  return `${String((h - OFFSET_CDMX_H + 24) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** "HH:MM" CDMX → "HH:MM" para almacenar (UTC). */
export function horaCdmxAUtc(hora: string): string {
  const [h, m] = hora.split(":").map(Number);
  return `${String((h + OFFSET_CDMX_H) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
