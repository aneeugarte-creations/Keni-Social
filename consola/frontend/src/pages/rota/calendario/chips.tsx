// Chips del calendario de la rota: chip de evento y chip de turno (con menú contextual
// de CRUD).
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  BellRing,
  Clock,
  Copy,
  Loader2,
  Pencil,
  Plane,
  Trash2,
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
import { ApiError, api, mensajeError } from "@/lib/api";
import {
  COBERTURA,
  COLOR_PRIORIDAD,
} from "@/lib/rota-calendario";
import { AvatarPersona } from "@/pages/tareas/AvatarPersona";
import type {
  AusenciaRota,
  MiembroRota,
  TurnoRota,
} from "@/types";

import { BotonMarcarAvisado, type ItemEventoCalendario } from "../comun";
import { DialogEditarTurno } from "./dialogs";


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
      </span>
      {/* Quién lo COGIÓ: el mismo avatar + primer nombre que muestra el Panorama (titularidad
          real, no quién está de turno), para que calendario y Panorama digan lo mismo. Si nadie
          lo ha cogido → «Por cubrir», igual que en el tablero de Cobertura. */}
      {item.cubridores.length > 0 ? (
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          {item.cubridores.map((c) => (
            <span key={c.id} className="inline-flex items-center gap-1">
              <AvatarPersona id={c.id} nombre={c.nombre} size="sm" />
              <span className="truncate font-medium">{primerNombre(c.nombre)}</span>
            </span>
          ))}
        </span>
      ) : (
        <span className="inline-flex w-fit items-center rounded border border-amber-300 bg-amber-50 px-1 text-[10px] font-medium text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          Por cubrir
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

  // Tooltip con horario + motivo + ausencia + nota relevo, para no cargar la celda.
  const tooltipPartes: string[] = [];
  if (turno.inicio && turno.fin)
    tooltipPartes.push(
      `${turno.horario_propio ? "Horario a medida" : "Horario"}: ${turno.inicio}–${turno.fin}`,
    );
  if (turno.motivo) tooltipPartes.push(`Motivo: ${turno.motivo}`);
  if (turno.nota_relevo) tooltipPartes.push(`Relevo: ${turno.nota_relevo}`);
  if (ausencia)
    tooltipPartes.push(
      `Ausente (${ausencia.tipo})${ausencia.motivo ? `: ${ausencia.motivo}` : ""}`,
    );
  const tieneTooltip = tooltipPartes.length > 0;
  const etiquetaTooltip = tooltipPartes.join(" · ");

  if (!editable) {
    // Cabecera del recuadro = SOLO el avatar redondo (color + inicial; nombre en su
    // `title`). El nombre escrito ya vive en los chips de evento de debajo, así que el
    // píldora gris «👤 nombre» sobraba: una persona = su avatar, sin texto repetido.
    const chip = (
      <span className="inline-flex max-w-full items-center gap-1 text-xs">
        <AvatarPersona id={turno.miembro_id} nombre={turno.miembro_nombre} size="sm" />
        {turno.override && (
          <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600" aria-label="override" />
        )}
        {ausencia && !turno.override && (
          <Plane className="h-3 w-3 shrink-0 text-orange-600" aria-label="ausente" />
        )}
        {turno.horario_propio && (
          <Clock className="h-3 w-3 shrink-0 text-sky-600" aria-label="horario a medida" />
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
      {/* Igual que en solo-lectura: solo el avatar (sin «👤 nombre»), + la × para
          quitar el turno. El click en el avatar abre el menú (editar/duplicar/borrar). */}
      <span className="inline-flex max-w-full cursor-pointer items-center gap-1 rounded-full text-xs hover:opacity-80">
        <AvatarPersona id={turno.miembro_id} nombre={turno.miembro_nombre} size="sm" />
        {turno.override && (
          <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600" aria-label="override" />
        )}
        {ausencia && !turno.override && (
          <Plane className="h-3 w-3 shrink-0 text-orange-600" aria-label="ausente" />
        )}
        {turno.horario_propio && (
          <Clock className="h-3 w-3 shrink-0 text-sky-600" aria-label="horario a medida" />
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
