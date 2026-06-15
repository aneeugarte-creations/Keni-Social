// Helpers compartidos del calendario de la rota. Extraído verbatim de CalendarioPiezas.tsx
// (refactor de pura reubicación): la antigua librería de componentes se troceó por familias.
import type { MiembroRota } from "@/types";

import { filtrarEquipoPorMarca } from "../comun";

// --- Helpers de la rejilla CRUD (consumidos por el Calendario fusionado) --
//
// Modelo: un turno NO está ligado a un evento. Es el horario que cada persona tiene
// en (fecha, franja_id). La cobertura es derivada. El CRUD vive ahora dentro del
// Calendario fusionado (la antigua pestaña "Turnos" se absorbió aquí); estas
// utilidades se conservan porque siguen siendo la fuente de la lista de CMs y de
// los chips de persona con menú.

/**
 * Restringe el equipo a los community managers de la marca activa que cubren hoy.
 *
 * Aplica los tres filtros pedidos por Bernardo:
 *  - `marcas.includes(marcaActiva)` (vertical correcta; "Todas"/`null` no filtra).
 *  - `cobertura === true` (la persona está disponible para cubrir hoy).
 *  - `cargo === "community_manager"` (los coordinadores quedan fuera; Elías
 *    coordina pero no se asigna a una franja).
 *
 * Si los tres filtros dejan la lista vacía (puede ocurrir en entornos donde el
 * seed de cargos del organigrama del cliente aún no se ha aplicado a la BD), degrada al
 * filtro por marca+cobertura para no romper la rejilla.
 */
export function cmsDeMarca(equipo: MiembroRota[], marcaActiva: string | null): MiembroRota[] {
  const porMarca = filtrarEquipoPorMarca(equipo, marcaActiva).filter(
    (m) => m.cobertura !== false,
  );
  const estrictos = porMarca.filter((m) => m.cargo === "community_manager");
  if (estrictos.length > 0) return estrictos;
  return porMarca;
}
