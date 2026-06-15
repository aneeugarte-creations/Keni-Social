// Chips del calendario de la rota: badge de coordinador, chip de evento y chip de turno
// (con menú contextual de CRUD).
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  BellRing,
  Copy,
  Loader2,
  Pencil,
  Plane,
  ShieldCheck,
  Trash2,
  User,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import { confirmar } from "@/components/comunes/confirmar";
import {
  MenuContextual,
  type EntradaMenuContextual,
} from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { ApiError, api, mensajeError } from "@/lib/api";
import {
  COBERTURA,
  COLOR_PRIORIDAD,
} from "@/lib/rota-calendario";
import { cn } from "@/lib/utils";
import { AvatarPersona } from "@/pages/tareas/AvatarPersona";
import type {
  AusenciaRota,
  CoordinacionTurno,
  FranjaSemana,
  MiembroRota,
  TurnoRota,
} from "@/types";

import { BotonMarcarAvisado, type ItemEventoCalendario } from "../comun";
import { DialogEditarTurno } from "./dialogs";


export function BadgeCoordinador({
  lunes,
  fecha,
  franja,
  coordinacion,
  candidatos,
  editable,
  onCambio,
}: {
  lunes: string;
  fecha: string;
  franja: FranjaSemana;
  coordinacion?: CoordinacionTurno;
  candidatos: MiembroRota[];
  editable: boolean;
  onCambio: () => void;
}) {
  const [open, setOpen] = React.useState(false);

  const asignar = useMutation({
    mutationFn: (coordinador_id: string) =>
      api.setCoordinador({
        lunes,
        fecha,
        franja_id: franja.id,
        coordinador_id,
      }),
    onSuccess: () => {
      toast.success("Coordinador asignado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const quitar = useMutation({
    mutationFn: () =>
      api.quitarCoordinador({ fecha, franja_id: franja.id }),
    onSuccess: () => {
      toast.success("Coordinador quitado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cargando = asignar.isPending || quitar.isPending;

  if (!editable) {
    // Solo lectura: si hay coordinador, lo mostramos; si no, badge muted "Sin coord".
    return coordinacion ? (
      <span
        className="inline-flex max-w-full items-center gap-1 rounded border border-sky-300/70 bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-800 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-300"
        title={`Coordina: ${coordinacion.coordinador_nombre}`}
      >
        <ShieldCheck className="h-3 w-3 shrink-0" />
        <span className="truncate">
          Coord: {coordinacion.coordinador_nombre || "—"}
        </span>
      </span>
    ) : (
      <span className="inline-flex max-w-full items-center gap-1 rounded border border-dashed border-border/60 bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground/60">
        Sin coord
      </span>
    );
  }

  // Editable: Select para asignar/cambiar + X para borrar (si hay).
  return (
    <div className="flex items-center gap-1">
      <Select
        value={coordinacion?.coordinador_id ?? ""}
        open={open}
        onOpenChange={setOpen}
        onValueChange={(id) => {
          if (!id) return;
          asignar.mutate(id);
        }}
        disabled={cargando || candidatos.length === 0}
      >
        <SelectTrigger
          aria-label={`Coordinador de ${franja.nombre} del ${fecha}`}
          className={cn(
            "h-6 flex-1 gap-1 px-1.5 text-[10px]",
            coordinacion
              ? "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-300"
              : "border-dashed border-border bg-background text-muted-foreground",
          )}
        >
          <ShieldCheck className="h-3 w-3 shrink-0" />
          <span className="truncate">
            {coordinacion
              ? `Coord: ${coordinacion.coordinador_nombre || "—"}`
              : candidatos.length === 0
                ? "Sin candidatos"
                : "Sin coord"}
          </span>
        </SelectTrigger>
        <SelectContent>
          {candidatos.map((c) => (
            <SelectItem key={c.id} value={c.id}>
              {c.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {coordinacion && (
        <Button
          size="icon"
          variant="ghost"
          className="h-6 w-6 text-muted-foreground hover:text-destructive"
          aria-label="Quitar coordinador"
          title="Quitar coordinador"
          onClick={() => quitar.mutate()}
          disabled={cargando}
        >
          {quitar.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <X className="h-3 w-3" />
          )}
        </Button>
      )}
    </div>
  );
}

/** Primer nombre (lo que cabe en el chip): "Tezcucano Pérez" → "Tezcucano". */
const primerNombre = (n: string) => n.trim().split(/\s+/)[0] || n;

/** Chip de evento dentro de un recuadro de persona (clicable: abre edición). */
export function ChipEventoCalendario({
  item,
  onClick,
  onCambio,
}: {
  item: ItemEventoCalendario;
  onClick: () => void;
  onCambio: () => void;
}) {
  const cob = COBERTURA[item.evento.tipo_cobertura] ?? COBERTURA.transmision;
  const Icono = cob.icono;
  const tieneOverride = item.cobertura.some((c) => c.override);
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group/chip flex flex-col gap-0.5 rounded-sm border px-1.5 py-1 text-left text-[11px] leading-tight transition hover:ring-1 hover:ring-primary/40 ${cob.chip}`}
      aria-label={`Editar ${item.evento.titulo}`}
    >
      <span className="flex items-start gap-1">
        <Icono className="mt-0.5 h-2.5 w-2.5 shrink-0" />
        <span className="min-w-0 break-words font-medium">{item.evento.titulo}</span>
      </span>
      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 opacity-90">
        {item.evento.hora && <span>{item.evento.hora}</span>}
        <span className={COLOR_PRIORIDAD[item.evento.prioridad]}>· {item.evento.prioridad}</span>
        {item.evento.cambiado && (
          <Badge variant="aviso" className="h-3.5 gap-0.5 px-1 text-[9px] font-normal">
            <BellRing className="h-2.5 w-2.5" /> cambió
          </Badge>
        )}
        {tieneOverride && (
          <span className="inline-flex items-center gap-0.5 text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-2.5 w-2.5" /> override
          </span>
        )}
      </span>
      {/* Quién lo cubre: el mismo avatar redondo (color por persona) + primer nombre que
          se ve en el tablero de Cobertura, para que el evento del calendario diga de un
          vistazo su equipo. Vacío en «Sin turno a esa hora» (evento sin cobertura). */}
      {item.cobertura.length > 0 && (
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          {item.cobertura.map((c) => (
            <span key={c.turno_id} className="inline-flex items-center gap-1">
              <AvatarPersona id={c.miembro_id} nombre={c.miembro_nombre} size="sm" />
              <span className="truncate font-medium">{primerNombre(c.miembro_nombre)}</span>
            </span>
          ))}
        </span>
      )}
      {item.evento.cambiado && (
        <span
          // Stop propagation: marcar avisado no debe abrir el modal de edición.
          onClick={(e) => e.stopPropagation()}
          className="mt-0.5"
        >
          <BotonMarcarAvisado evento={item.evento} onCambio={onCambio} />
        </span>
      )}
    </button>
  );
}

export function ChipTurnoCM({
  turno,
  equipo,
  ausencia,
  editable,
  onCambio,
}: {
  turno: TurnoRota;
  /** Equipo de la rota (para que `DialogEditarTurno` pueda reasignar). */
  equipo: MiembroRota[];
  ausencia?: AusenciaRota;
  editable: boolean;
  onCambio: () => void;
}) {
  const [editandoDetalles, setEditandoDetalles] = React.useState(false);

  const borrar = useMutation({
    mutationFn: () => api.borrarTurno(turno.id),
    onSuccess: () => {
      toast.success("Turno eliminado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const duplicar = useMutation({
    mutationFn: () => api.duplicarTurno(turno.id, {}),
    onSuccess: () => {
      toast.success("Turno duplicado.");
      onCambio();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        toast.info(e.message);
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  // Tooltip con motivo + ausencia + nota relevo, para no cargar la celda.
  const tooltipPartes: string[] = [];
  if (turno.motivo) tooltipPartes.push(`Motivo: ${turno.motivo}`);
  if (turno.nota_relevo) tooltipPartes.push(`Relevo: ${turno.nota_relevo}`);
  if (ausencia)
    tooltipPartes.push(
      `Ausente (${ausencia.tipo})${ausencia.motivo ? `: ${ausencia.motivo}` : ""}`,
    );
  const tieneTooltip = tooltipPartes.length > 0;
  const etiquetaTooltip = tooltipPartes.join(" · ");

  if (!editable) {
    const chip = (
      <span className="inline-flex max-w-full items-center gap-1 rounded border bg-muted/40 px-1.5 py-0.5 text-xs">
        <User className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="truncate">{turno.miembro_nombre}</span>
        {turno.override && (
          <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600" aria-label="override" />
        )}
        {ausencia && !turno.override && (
          <Plane className="h-3 w-3 shrink-0 text-orange-600" aria-label="ausente" />
        )}
      </span>
    );
    return tieneTooltip ? <Tooltip label={etiquetaTooltip}>{chip}</Tooltip> : chip;
  }

  const itemsMenu: EntradaMenuContextual[] = [
    {
      etiqueta: "Editar detalles…",
      icono: Pencil,
      onClick: () => setEditandoDetalles(true),
    },
    {
      etiqueta: "Duplicar",
      icono: Copy,
      onClick: () => duplicar.mutate(),
      deshabilitado: duplicar.isPending,
    },
    { separador: true },
    {
      etiqueta: "Eliminar",
      icono: Trash2,
      destructivo: true,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Eliminar el turno de ${turno.miembro_nombre}?`,
            destructivo: true,
            textoConfirmar: "Eliminar",
          })
        )
          borrar.mutate();
      },
      deshabilitado: borrar.isPending,
    },
  ];

  const chip = (
    <MenuContextual items={itemsMenu} disparador="ambos">
      <span className="inline-flex max-w-full cursor-pointer items-center gap-1 rounded border bg-background px-1.5 py-0.5 text-xs hover:bg-accent">
        <User className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="truncate">{turno.miembro_nombre}</span>
        {turno.override && (
          <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600" aria-label="override" />
        )}
        {ausencia && !turno.override && (
          <Plane className="h-3 w-3 shrink-0 text-orange-600" aria-label="ausente" />
        )}
        <button
          type="button"
          aria-label={`Borrar turno de ${turno.miembro_nombre}`}
          onClick={async (e) => {
            e.stopPropagation();
            if (borrar.isPending) return;
            if (
              await confirmar({
                mensaje: `¿Borrar el turno de ${turno.miembro_nombre}?`,
                destructivo: true,
                textoConfirmar: "Borrar",
              })
            )
              borrar.mutate();
          }}
          disabled={borrar.isPending}
          className="ml-0.5 rounded text-muted-foreground hover:text-destructive disabled:opacity-50"
        >
          {borrar.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />}
        </button>
      </span>
    </MenuContextual>
  );

  return (
    <>
      {tieneTooltip ? <Tooltip label={etiquetaTooltip}>{chip}</Tooltip> : chip}
      {editandoDetalles && (
        <DialogEditarTurno
          turno={turno}
          equipo={equipo}
          onCerrar={() => setEditandoDetalles(false)}
          onGuardado={() => {
            setEditandoDetalles(false);
            onCambio();
          }}
        />
      )}
    </>
  );
}
