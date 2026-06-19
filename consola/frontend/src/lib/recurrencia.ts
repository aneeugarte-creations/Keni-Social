/**
 * Recurrencia de eventos (lado cliente): presets, días de la semana y utilidades de fecha.
 *
 * Convenio de día de semana: 0=lunes … 6=domingo (igual que el backend `dominio.recurrencia`
 * y `datetime.weekday()`). Una serie se define por un conjunto de días + una fecha fin; el
 * backend materializa una ocurrencia por día. Aquí solo se preparan los datos del formulario.
 */

/** Preset de recurrencia elegible en el selector. `"no"` = evento suelto. */
export type PresetRecurrencia =
  | "no"
  | "laborables"
  | "fin_de_semana"
  | "diario"
  | "semanal"
  | "personalizado";

/** Etiquetas de los 7 días, índice = 0=lunes … 6=domingo. */
export const DIAS_SEMANA: { valor: number; corto: string; nombre: string }[] = [
  { valor: 0, corto: "L", nombre: "Lunes" },
  { valor: 1, corto: "M", nombre: "Martes" },
  { valor: 2, corto: "X", nombre: "Miércoles" },
  { valor: 3, corto: "J", nombre: "Jueves" },
  { valor: 4, corto: "V", nombre: "Viernes" },
  { valor: 5, corto: "S", nombre: "Sábado" },
  { valor: 6, corto: "D", nombre: "Domingo" },
];

const LABORABLES = [0, 1, 2, 3, 4];
const FIN_DE_SEMANA = [5, 6];
const DIARIO = [0, 1, 2, 3, 4, 5, 6];

/** Etiqueta legible de un preset (para el selector). */
export const ETIQUETA_PRESET: Record<PresetRecurrencia, string> = {
  no: "No se repite",
  laborables: "Días laborables (L–V)",
  fin_de_semana: "Fines de semana (S–D)",
  diario: "Todos los días",
  semanal: "Cada semana (mismo día)",
  personalizado: "Días personalizados…",
};

/** Parsea "AAAA-MM-DD" a un `Date` LOCAL (sin sorpresas de zona horaria). null si inválida. */
function fechaLocal(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return null;
  const [, a, mes, d] = m;
  const fecha = new Date(Number(a), Number(mes) - 1, Number(d));
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

/** Día de la semana 0=lunes … 6=domingo de una fecha ISO. "" o inválida → 0 (lunes). */
export function diaSemanaLunes0(iso: string): number {
  const d = fechaLocal(iso);
  if (!d) return 0;
  return (d.getDay() + 6) % 7; // getDay(): 0=domingo … 6=sábado.
}

/** Último día del mes de `iso`, en ISO. Es el default de «Repetir hasta». "" → "". */
export function finDeMesISO(iso: string): string {
  const d = fechaLocal(iso);
  if (!d) return "";
  const ultimo = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  const mm = String(ultimo.getMonth() + 1).padStart(2, "0");
  const dd = String(ultimo.getDate()).padStart(2, "0");
  return `${ultimo.getFullYear()}-${mm}-${dd}`;
}

/**
 * Días de la semana (0=lun…6=dom) que implica un preset, dada la fecha base (para «semanal»,
 * que repite el mismo día de la semana de la base). `personalizado` y `no` devuelven [].
 */
export function diasDePreset(preset: PresetRecurrencia, fechaBase: string): number[] {
  switch (preset) {
    case "laborables":
      return [...LABORABLES];
    case "fin_de_semana":
      return [...FIN_DE_SEMANA];
    case "diario":
      return [...DIARIO];
    case "semanal":
      return [diaSemanaLunes0(fechaBase)];
    default:
      return [];
  }
}
