// Celdas de la rejilla del calendario de la rota: la celda (franja × día) con el recuadro
// por persona (CAPACIDAD) y los chips de evento (titularidad real).
import { cn } from "@/lib/utils";
import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  MiembroRota,
  TurnoRota,
} from "@/types";

import type { ItemEventoCalendario } from "../comun";
import { ChipEventoCalendario, ChipTurnoCM } from "./chips";


/**
 * Una celda (franja × día) de la rejilla. Dos planos separados (ya no anidados):
 *  - CAPACIDAD: quién está de turno esa franja (avatares con CRUD).
 *  - EVENTOS: cada evento de esa franja UNA sola vez, con quién lo COGIÓ (titularidad real,
 *    la misma que el Panorama) o «Por cubrir» si nadie lo ha cogido.
 * La asignación de cobertura (quién cubre cada evento) y de coordinador se hace desde el
 * Panorama (Cobertura); el calendario solo la REFLEJA, no la edita aquí.
 */
export function CeldaDeRejilla({
  fecha,
  franja,
  personas,
  eventos,
  equipo,
  editable,
  finde,
  ausenciaDe,
  onEditarEvento,
  onCambio,
}: {
  fecha: string;
  franja: FranjaSemana;
  /** Personas de TURNO en esta franja ese día (CAPACIDAD). */
  personas: TurnoRota[];
  /** Eventos de esta franja/día, cada uno UNA vez, con su titularidad real (claims). */
  eventos: ItemEventoCalendario[];
  equipo: MiembroRota[];
  editable: boolean;
  finde: boolean;
  ausenciaDe: (miembroId: string, fecha: string) => AusenciaRota | undefined;
  onEditarEvento: (evento: EventoRota) => void;
  onCambio: () => void;
}) {
  return (
    <div
      className={cn(
        "flex min-h-[8rem] flex-col gap-2 border-l p-2",
        finde && "bg-amber-50/20 dark:bg-amber-950/5",
      )}
    >
      {/* CAPACIDAD: quién está de turno esta franja (avatares con CRUD). NO cuelga eventos:
          el evento ya no es «de la persona», es del día/franja (ver bloque de eventos). */}
      <div className="flex flex-wrap items-center gap-1.5">
        {personas.map((t) => (
          <ChipTurnoCM
            key={t.id}
            turno={t}
            equipo={equipo}
            ausencia={ausenciaDe(t.miembro_id, fecha)}
            editable={editable}
            onCambio={onCambio}
          />
        ))}
        {personas.length === 0 && (
          <span className="text-[11px] text-muted-foreground/60">
            {franja.es_descanso ? "—" : "Sin turno asignado"}
          </span>
        )}
      </div>

      {/* EVENTOS: cada uno UNA vez, con quién lo COGIÓ (titularidad real) o «Por cubrir». */}
      {eventos.length > 0 && (
        <div className="flex flex-col gap-1">
          {eventos.map((item) => (
            <ChipEventoCalendario
              key={item.evento.id}
              item={item}
              onClick={() => onEditarEvento(item.evento)}
              onCambio={onCambio}
            />
          ))}
        </div>
      )}
    </div>
  );
}
