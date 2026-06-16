import type { MiembroRota } from "@/types";

import { filtrarEquipoPorMarca } from "../comun";

// --- Helpers de la rejilla CRUD (consumidos por el Calendario fusionado) --
//
// Modelo: un turno NO está ligado a un evento. Es el horario que cada persona tiene
// en (fecha, franja_id). La cobertura es derivada. El CRUD vive ahora dentro del
// Calendario fusionado; estas utilidades se conservan porque siguen siendo la fuente
// de la lista de CMs y de los chips de persona con menú.

/**
 * Equipo asignable a un turno de la marca activa: quienes cubren hoy.
 *
 * Espejo EXACTO de `_usuarios_asignables` del backend (el que alimenta los carriles por
 * persona del Panorama/Cobertura): el dropdown «Añadir turno» debe ofrecer a TODAS las
 * personas que aparecen ahí, no un subconjunto. Dos filtros:
 *  - `marcas.includes(marcaActiva)` (vertical correcta; "Todas"/`null` no filtra).
 *  - `cobertura === true` (la persona está disponible para cubrir hoy).
 *
 * Antes excluía por `cargo === "community_manager"` (dejaba al coordinador fuera de la
 * grilla), pero eso rompía la paridad con el Panorama: el coordinador cubre y debe poder
 * tener turno. El filtro por cargo se eliminó a petición de dirección.
 */
export function cmsDeMarca(equipo: MiembroRota[], marcaActiva: string | null): MiembroRota[] {
  return filtrarEquipoPorMarca(equipo, marcaActiva).filter((m) => m.cobertura !== false);
}
