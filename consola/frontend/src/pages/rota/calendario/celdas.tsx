// Celdas de la rejilla del calendario de la rota: la celda (franja × día), el recuadro
// por persona y el dropdown "+ Añadir persona". Extraído verbatim de CalendarioPiezas.tsx
// (refactor de pura reubicación).
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  Loader2,
  Plus,
  User,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
  CoordinacionTurno,
  CuerpoCrearTurnoRota,
  EventoRota,
  FranjaSemana,
  MiembroRota,
} from "@/types";

import type { RecuadroPersona } from "../comun";
import { BadgeCoordinador, ChipEventoCalendario, ChipTurnoCM } from "./chips";


/**
 * Una celda (franja × día) de la rejilla. Mantiene estado local para abrir el dropdown
 * desde dos puntos de entrada: el propio trigger del dropdown al pie de la celda y el
 * recuadro "Sin cubrir" cuando hay eventos sin coverage. La separación a componente es
 * lo que permite tener `useState` por celda sin polucionar el padre con un Map.
 */
export function CeldaDeRejilla({
  lunes,
  fecha,
  franja,
  recuadros,
  equipo,
  cmsDisponibles,
  editable,
  finde,
  ausenciaDe,
  coordinacion,
  candidatosCoordinador,
  coordinacionEditable,
  onEditarEvento,
  onCambio,
}: {
  lunes: string;
  fecha: string;
  franja: FranjaSemana;
  recuadros: RecuadroPersona[];
  equipo: MiembroRota[];
  cmsDisponibles: MiembroRota[];
  editable: boolean;
  finde: boolean;
  ausenciaDe: (miembroId: string, fecha: string) => AusenciaRota | undefined;
  /** Coordinador asignado a esta celda (si lo hay). Ola "coord". */
  coordinacion?: CoordinacionTurno;
  /** Candidatos a coordinador (usuarios con `puede_coordinar=true`). */
  candidatosCoordinador: MiembroRota[];
  /** True si el admin puede editar la coordinación (semana NO aprobada). */
  coordinacionEditable: boolean;
  onEditarEvento: (evento: EventoRota) => void;
  onCambio: () => void;
}) {
  // Cada vez que sube, el dropdown del pie se abre. Se usa para que un click en el header
  // del recuadro "Sin cubrir" abra el dropdown sin necesitar pasar refs.
  const [pedidoAbrir, setPedidoAbrir] = React.useState(0);
  const placeholderDropdown =
    recuadros.length === 0
      ? franja.es_descanso
        ? "—"
        : "Sin turno asignado"
      : "Añadir persona";
  return (
    <div
      className={cn(
        "flex min-h-[8rem] flex-col gap-2 border-l p-2",
        finde && "bg-amber-50/20 dark:bg-amber-950/5",
      )}
    >
      {/* Badge de coordinador (ola "coord"): siempre visible si hay coordinador o si
          la celda es editable; en franja Descanso lo ocultamos porque no aplica. */}
      {!franja.es_descanso && (
        <BadgeCoordinador
          lunes={lunes}
          fecha={fecha}
          franja={franja}
          coordinacion={coordinacion}
          candidatos={candidatosCoordinador}
          editable={coordinacionEditable}
          onCambio={onCambio}
        />
      )}
      {recuadros.length === 0 && !editable && (
        <div className="rounded-md border border-dashed border-border/60 px-2 py-3 text-center text-[11px] text-muted-foreground/60">
          {franja.es_descanso ? "—" : "Sin turno asignado"}
        </div>
      )}
      {recuadros.map((rec) => (
        <RecuadroPersonaCalendario
          key={`${rec.miembro_id}-${rec.sinCubrir ? "sin" : "ok"}`}
          recuadro={rec}
          franja={franja}
          equipo={equipo}
          ausencia={
            rec.sinCubrir ? undefined : ausenciaDe(rec.miembro_id, fecha)
          }
          editable={editable}
          onEditarEvento={onEditarEvento}
          onCambio={onCambio}
          onClickHeaderSinCubrir={
            editable ? () => setPedidoAbrir((n) => n + 1) : undefined
          }
        />
      ))}
      {editable && (
        <DropdownAnadirPersona
          lunes={lunes}
          fecha={fecha}
          franja={franja}
          cmsDisponibles={cmsDisponibles}
          onCambio={onCambio}
          placeholder={placeholderDropdown}
          pedidoAbrir={pedidoAbrir}
        />
      )}
    </div>
  );
}

/**
 * Un recuadro por persona dentro de una celda día-franja del calendario fusionado. La
 * cabecera del recuadro reutiliza `ChipTurnoCM`: cuando `editable=true` y el recuadro
 * representa a una persona real (no "Sin cubrir"), expone el menú contextual de CRUD
 * (editar detalles / duplicar / borrar) y el botón × inline para quitar el turno. Los
 * eventos cubiertos por esa persona aparecen como chips clicables debajo.
 */
export function RecuadroPersonaCalendario({
  recuadro,
  franja,
  equipo,
  ausencia,
  editable,
  onEditarEvento,
  onCambio,
  onClickHeaderSinCubrir,
}: {
  recuadro: RecuadroPersona;
  franja: FranjaSemana;
  /** Equipo de la rota (para que `DialogEditarTurno` pueda reasignar). */
  equipo: MiembroRota[];
  ausencia?: AusenciaRota;
  /** `true` si la semana es borrador (no aprobada): habilita CRUD de turnos. */
  editable: boolean;
  onEditarEvento: (evento: EventoRota) => void;
  onCambio: () => void;
  /**
   * Cuando el recuadro es "Sin cubrir" y el padre quiere abrir el dropdown al hacer
   * click en su header, pasa este callback. Solo lo recibe el header sinCubrir.
   */
  onClickHeaderSinCubrir?: () => void;
}) {
  const esDescanso = franja.es_descanso;
  const estilo = recuadro.sinCubrir
    ? "border-dashed border-amber-300/70 bg-amber-50/30 dark:bg-amber-950/10"
    : esDescanso
      ? "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900/40"
      : "border-border bg-background";
  return (
    <div className={`flex flex-col gap-1 rounded-md border p-1.5 text-xs ${estilo}`}>
      <div className="flex items-center justify-between gap-1">
        {recuadro.sinCubrir ? (
          onClickHeaderSinCubrir ? (
            <button
              type="button"
              onClick={onClickHeaderSinCubrir}
              className="truncate text-left font-medium text-amber-700 hover:underline dark:text-amber-400"
              title="Asignar una persona a esta franja"
            >
              Sin cubrir
            </button>
          ) : (
            <span className="truncate font-medium text-amber-700 dark:text-amber-400">
              Sin cubrir
            </span>
          )
        ) : recuadro.turno ? (
          // `ChipTurnoCM` ya envuelve el nombre en un menú contextual (editar /
          // duplicar / borrar) + botón × para quitar el turno. Reusamos el mismo
          // componente que la rejilla CRUD anterior — una única fuente de verdad.
          <ChipTurnoCM
            turno={recuadro.turno}
            equipo={equipo}
            ausencia={ausencia}
            editable={editable}
            onCambio={onCambio}
          />
        ) : (
          // Coverage huérfana: el backend devolvió un cubridor cuyo TurnoRota local no
          // tenemos (carrera de invalidación). Mostramos el nombre sin menú; la acción
          // CRUD vuelve disponible al siguiente refetch.
          <span className="inline-flex max-w-full items-center gap-1 rounded border bg-muted/40 px-1.5 py-0.5 text-xs">
            <User className="h-3 w-3 shrink-0 text-muted-foreground" />
            <span className="truncate">{recuadro.miembro_nombre}</span>
          </span>
        )}
        {recuadro.eventos.length > 0 && (
          <Badge variant="outline" className="h-4 px-1 text-[10px] font-normal">
            {recuadro.eventos.length}
          </Badge>
        )}
      </div>
      {recuadro.eventos.length === 0 ? (
        <span className="px-0.5 text-[10px] text-muted-foreground/70">
          {esDescanso ? "Descanso" : "Sin eventos"}
        </span>
      ) : (
        <div className="flex flex-col gap-1">
          {recuadro.eventos.map((item) => (
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

/**
 * Dropdown "+ Añadir persona" al pie de cada celda del calendario. Asigna un CM de
 * ClaroSports a la (fecha, franja_id) creando un turno; maneja 409 `requiere_override`
 * (regla de sábado consecutivo) abriendo un dialog de confirmación. Extraído de la
 * antigua `CeldaFranjaDia` para reutilizarlo dentro de la rejilla fusionada.
 */
export function DropdownAnadirPersona({
  lunes,
  fecha,
  franja,
  cmsDisponibles,
  onCambio,
  placeholder = "Añadir persona",
  pedidoAbrir = 0,
}: {
  lunes: string;
  fecha: string;
  franja: FranjaSemana;
  cmsDisponibles: MiembroRota[];
  onCambio: () => void;
  /** Texto del trigger cuando no hay persona seleccionada. Por defecto "Añadir persona". */
  placeholder?: string;
  /**
   * Contador "trigger numérico": cada incremento abre el Select programáticamente. Sirve
   * para que el padre (la celda) abra el dropdown cuando el usuario hace click en otro
   * elemento (p. ej. el header del recuadro "Sin cubrir") sin necesitar refs.
   */
  pedidoAbrir?: number;
}) {
  const [pendienteOverride, setPendienteOverride] = React.useState<{
    miembroId: string;
    mensaje: string;
  } | null>(null);
  const [open, setOpen] = React.useState(false);
  // El primer render (pedidoAbrir=0) no debe abrir el dropdown; sólo los incrementos
  // posteriores cuentan como "el padre pide abrir". Mantengo el valor anterior con un ref.
  const ultimoPedido = React.useRef(pedidoAbrir);
  React.useEffect(() => {
    if (pedidoAbrir > ultimoPedido.current) setOpen(true);
    ultimoPedido.current = pedidoAbrir;
  }, [pedidoAbrir]);

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
          aria-label={`Añadir persona a ${franja.nombre} del ${fecha}`}
          className="h-7 w-full justify-start gap-1 border-dashed px-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <Plus className="h-3 w-3" />
          <span className="truncate">
            {cmsDisponibles.length === 0 ? "Todos asignados" : placeholder}
          </span>
        </SelectTrigger>
        <SelectContent>
          {cmsDisponibles.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              {m.nombre}
            </SelectItem>
          ))}
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
