/**
 * Etiqueta legible del "token de rango" que el dashboard de Métricas maneja.
 *
 * Traduce los tres modos del selector de tiempo a un texto sobrio para pintar en el
 * toolbar, la portada del PDF y los nombres de archivo:
 *   - preset ("semana"|"mes"|…) → su etiqueta del backend ("Últimos 30 días")
 *   - `mes:AAAA-MM`             → "junio 2026"
 *   - `rango:AAAA-MM-DD_…`      → "2026-06-01 – 2026-06-30"
 */
import type { RangoMetrica } from "@/types";

import { diasDePeriodo, partesMes, partesRango } from "./rango";

const MESES_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** Etiqueta legible de un token de periodo (preset, `mes:` o `rango:`). */
export function etiquetaPeriodo(token: string, rangos: RangoMetrica[]): string {
  const preset = rangos.find((r) => r.id === token);
  if (preset) return preset.etiqueta;
  const mes = partesMes(token);
  if (mes) return `${MESES_ES[mes.mes - 1]} ${mes.anio}`;
  const rango = partesRango(token);
  if (rango) return `${rango.desde} – ${rango.hasta}`;
  const dias = diasDePeriodo(token);
  return dias != null ? `Últimos ${dias} días` : token;
}
