// Motor de reparto MULTI-SEMANA para «Gestión = Mes único» (variante SELECCIÓN-EN-MES).
//
// La selección de días puede cruzar varias semanas y cada persona puede tener SU patrón
// (matriz editable persona×día, sin plantillas obligatorias). Pero el modelo de datos guarda
// las franjas POR SEMANA: `crearTurno` exige un `franja_id` que pertenece a la semana de esa
// fecha. Por eso, al asignar, hay que AGRUPAR las fechas de cada persona por su semana (su
// lunes) y resolver la franja con las franjas de ESA semana.
//
// Este módulo es lógica pura (sin React): se reutiliza la indulgencia per-celda de
// `asignarDiasTurno` (un día que choca no tumba el resto) y la derivación de franja por horario
// de `franjaParaHorario`. Vive aparte para poder testearlo sin montar el panel.
import type { FranjaSemana } from "@/types";

import {
  asignarDiasTurno,
  franjaParaHorario,
  type ResumenReparto,
} from "@/pages/rota/DialogoAsignarTurnos";

import { lunesSiguiente } from "./rota-calendario";

/** Lunes (ISO) de la semana que contiene `fechaIso`. Reancla al lunes sin desplazar semanas. */
export function lunesDeFecha(fechaIso: string): string {
  return lunesSiguiente(fechaIso, 0);
}

/** Agrupa fechas ISO por el lunes de su semana (orden de inserción preservado). */
export function agruparFechasPorSemana(fechas: string[]): Map<string, string[]> {
  const porSemana = new Map<string, string[]>();
  for (const fecha of fechas) {
    const lunes = lunesDeFecha(fecha);
    const grupo = porSemana.get(lunes);
    if (grupo) grupo.push(fecha);
    else porSemana.set(lunes, [fecha]);
  }
  return porSemana;
}

export interface ResumenMatriz extends ResumenReparto {
  /** Días que no se pudieron crear porque su semana no tiene franjas laborales. */
  sinFranja: number;
}

/**
 * Crea los turnos de una MATRIZ persona×día (cada persona con SU propio conjunto de fechas).
 * Para cada persona: agrupa sus fechas por semana, deriva la franja de cada semana con su propio
 * horario, y crea un turno por (persona, fecha) con la indulgencia de `asignarDiasTurno`. Una
 * semana sin franjas laborales no rompe el reparto: sus días se cuentan en `sinFranja` y se avisa.
 *
 * @param porPersona       miembroId → fechas ISO encendidas para esa persona.
 * @param franjasPorSemana lunes ISO → franjas LABORALES (no descanso) vivas de esa semana.
 */
export async function asignarMatriz(
  porPersona: Map<string, string[]>,
  franjasPorSemana: Map<string, FranjaSemana[]>,
  inicio: string,
  fin: string,
): Promise<ResumenMatriz> {
  const r: ResumenMatriz = {
    creados: 0,
    yaEstaba: 0,
    requierenOverride: 0,
    fallos: 0,
    personasConCreados: 0,
    sinFranja: 0,
  };
  for (const [miembroId, fechas] of porPersona) {
    let creadosPersona = 0;
    for (const [lunes, fechasSemana] of agruparFechasPorSemana(fechas)) {
      const franjas = franjasPorSemana.get(lunes) ?? [];
      const franja = franjaParaHorario(inicio, fin, franjas);
      if (!franja) {
        r.sinFranja += fechasSemana.length;
        continue;
      }
      // Horario A MEDIDA solo si difiere del de la franja (si coincide, hereda → editar la franja
      // luego propaga). Igual criterio que el panel semanal.
      const horasAMedida = inicio !== franja.inicio || fin !== franja.fin;
      const p = await asignarDiasTurno(
        lunes,
        miembroId,
        franja.id,
        fechasSemana,
        horasAMedida ? inicio : "",
        horasAMedida ? fin : "",
      );
      r.creados += p.creados;
      r.yaEstaba += p.yaEstaba;
      r.requierenOverride += p.requierenOverride;
      r.fallos += p.fallos;
      creadosPersona += p.creados;
    }
    if (creadosPersona > 0) r.personasConCreados++;
  }
  return r;
}
