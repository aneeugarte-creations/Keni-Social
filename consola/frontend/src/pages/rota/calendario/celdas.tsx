// Celdas de la rejilla del calendario de la rota: la celda (franja × día) con el recuadro
// por persona (CAPACIDAD), el botón «Añadir turno» y los chips de evento (titularidad real).
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { ApiError, api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  AusenciaRota,
  CuerpoCrearTurnoRota,
  EventoRota,
  FranjaSemana,
  MiembroRota,
  TurnoRota,
} from "@/types";

import type { ConflictoCandidato, ItemEventoCalendario } from "../comun";
import { ChipEventoCalendario, ChipTurnoCM } from "./chips";


/**
 * Una celda (franja × día) de la rejilla. Dos planos separados (ya no anidados):
 *  - CAPACIDAD: quién está de turno esa franja (avatares con CRUD) + «Añadir turno».
 *  - EVENTOS: cada evento de esa franja UNA sola vez, en 3 estados: lo COGIÓ alguien (claim,
 *    titularidad explícita como en el Panorama) · «Cubierto» (nadie lo cogió pero hay turno en
 *    la franja: lo cubre quien esté de turno) · «Sin cubrir» (ni claim ni turno = hueco real).
 * La CAPACIDAD (turnos) se gestiona aquí (avatares + «Añadir turno»); coger un evento a nombre
 * de alguien concreto se hace desde el Panorama y aquí se REFLEJA.
 */
export function CeldaDeRejilla({
  lunes,
  fecha,
  franja,
  franjasSemana,
  personas,
  eventos,
  equipo,
  cmsDisponibles,
  editable,
  finde,
  ausenciaDe,
  conflictoCandidato,
  onEditarEvento,
  onCambio,
}: {
  lunes: string;
  fecha: string;
  franja: FranjaSemana;
  /** TODAS las franjas vivas de la semana (para que el editor de turno ofrezca la franja real). */
  franjasSemana: FranjaSemana[];
  /** Personas de TURNO en esta franja ese día (CAPACIDAD). */
  personas: TurnoRota[];
  /** Eventos de esta franja/día, cada uno UNA vez, con su titularidad real (claims). */
  eventos: ItemEventoCalendario[];
  equipo: MiembroRota[];
  /** CMs que aún no están de turno en esta celda (candidatos para «Añadir turno»). */
  cmsDisponibles: MiembroRota[];
  editable: boolean;
  finde: boolean;
  ausenciaDe: (miembroId: string, fecha: string) => AusenciaRota | undefined;
  /** Aviso inline (ausencia/solape) por candidato del dropdown. */
  conflictoCandidato: (
    miembroId: string,
    fecha: string,
    franja: FranjaSemana,
  ) => ConflictoCandidato;
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
      {/* CAPACIDAD: quién está de turno esta franja (avatares con CRUD) + alta con «Añadir
          turno». NO cuelga eventos: el evento es del día/franja (ver bloque de eventos).
          Solo se pinta si hay turnos o si se puede editar (para mostrar el botón de alta);
          si no, nada — un «Sin turno asignado» en cada celda sería ruido vacío. */}
      {(personas.length > 0 || editable) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {personas.map((t) => (
            <ChipTurnoCM
              key={t.id}
              turno={t}
              equipo={equipo}
              franjas={franjasSemana}
              ausencia={ausenciaDe(t.miembro_id, fecha)}
              editable={editable}
              onCambio={onCambio}
            />
          ))}
          {editable && (
            <DropdownAnadirPersona
              lunes={lunes}
              fecha={fecha}
              franja={franja}
              cmsDisponibles={cmsDisponibles}
              conflictoCandidato={conflictoCandidato}
              onCambio={onCambio}
              placeholder={personas.length === 0 ? "Añadir turno" : "Añadir"}
            />
          )}
        </div>
      )}

      {/* EVENTOS: cada uno UNA vez, con quién lo COGIÓ (titularidad real) o «Por cubrir». */}
      {eventos.length > 0 && (
        <div className="flex flex-col gap-1">
          {eventos.map((item) => (
            <ChipEventoCalendario
              key={item.evento.id}
              item={item}
              cubrenPorTurno={personas.map((t) => ({ id: t.miembro_id, nombre: t.miembro_nombre }))}
              onClick={() => onEditarEvento(item.evento)}
              onCambio={onCambio}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Dropdown «Añadir turno» al pie de cada celda del calendario. Da de alta un turno: asigna
 * un CM a la (fecha, franja_id) creando el turno; maneja el 409 `requiere_override` (regla
 * de sábado consecutivo) abriendo un diálogo de confirmación. Avisa inline (ausencia/solape)
 * por candidato sin bloquear: el admin puede forzar.
 */
export function DropdownAnadirPersona({
  lunes,
  fecha,
  franja,
  cmsDisponibles,
  conflictoCandidato,
  onCambio,
  placeholder = "Añadir turno",
}: {
  lunes: string;
  fecha: string;
  franja: FranjaSemana;
  cmsDisponibles: MiembroRota[];
  /** Aviso inline (ausencia/solape) por candidato. Por defecto: sin conflicto. */
  conflictoCandidato?: (
    miembroId: string,
    fecha: string,
    franja: FranjaSemana,
  ) => ConflictoCandidato;
  onCambio: () => void;
  /** Texto del trigger cuando no hay persona seleccionada. Por defecto "Añadir turno". */
  placeholder?: string;
}) {
  const [pendienteOverride, setPendienteOverride] = React.useState<{
    miembroId: string;
    mensaje: string;
  } | null>(null);
  const [open, setOpen] = React.useState(false);

  const crear = useMutation({
    mutationFn: ({ miembroId, override }: { miembroId: string; override: boolean }) => {
      const cuerpo: CuerpoCrearTurnoRota = {
        lunes,
        fecha,
        miembro_id: miembroId,
        franja_id: franja.id,
      };
      if (override) cuerpo.override = true;
      return api.crearTurno(cuerpo);
    },
    onSuccess: () => {
      setPendienteOverride(null);
      toast.success("Turno creado.");
      onCambio();
    },
    onError: (e, variables) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        (e.cuerpo?.requiere_override as boolean | undefined)
      ) {
        setPendienteOverride({ miembroId: variables.miembroId, mensaje: e.message });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  return (
    <>
      <Select
        value=""
        open={open}
        onOpenChange={setOpen}
        onValueChange={(miembroId) => {
          if (!miembroId) return;
          crear.mutate({ miembroId, override: false });
        }}
        disabled={crear.isPending || cmsDisponibles.length === 0}
      >
        <SelectTrigger
          aria-label={`Añadir turno a ${franja.nombre} del ${fecha}`}
          className="h-7 w-full justify-start gap-1 border-dashed px-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <Plus className="h-3 w-3" />
          <span className="truncate">
            {cmsDisponibles.length === 0 ? "Todos asignados" : placeholder}
          </span>
        </SelectTrigger>
        <SelectContent>
          {cmsDisponibles.map((m) => {
            const conflicto = conflictoCandidato?.(m.id, fecha, franja);
            return (
              <SelectItem key={m.id} value={m.id}>
                <span className="flex flex-wrap items-center gap-1.5">
                  <span>{m.nombre}</span>
                  {conflicto?.ausencia && (
                    <span
                      className="inline-flex items-center gap-0.5 rounded border border-amber-300 bg-amber-50 px-1 text-[10px] font-normal leading-tight text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                      title={`Ausencia (${conflicto.ausencia.tipo}) ese día`}
                    >
                      <AlertTriangle className="h-2.5 w-2.5 shrink-0" /> De ausencia ese día
                    </span>
                  )}
                  {conflicto?.solapa && (
                    <span
                      className="inline-flex items-center gap-0.5 rounded border border-amber-300 bg-amber-50 px-1 text-[10px] font-normal leading-tight text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                      title="Ya tiene otro turno que se solapa ese día"
                    >
                      <AlertTriangle className="h-2.5 w-2.5 shrink-0" /> Ya tiene turno
                    </span>
                  )}
                </span>
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
      {pendienteOverride && (
        <Dialog open onOpenChange={(o) => !o && setPendienteOverride(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>¿Forzar la cobertura?</DialogTitle>
              <DialogDescription>{pendienteOverride.mensaje}</DialogDescription>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              Esta persona cubrió el sábado anterior.
            </p>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setPendienteOverride(null)}>
                Cancelar
              </Button>
              <Button
                variant="outline"
                className="text-amber-700 hover:text-amber-700 dark:text-amber-400"
                onClick={() =>
                  crear.mutate({
                    miembroId: pendienteOverride.miembroId,
                    override: true,
                  })
                }
                disabled={crear.isPending}
              >
                {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                <AlertTriangle className="h-4 w-4" /> Forzar override
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
