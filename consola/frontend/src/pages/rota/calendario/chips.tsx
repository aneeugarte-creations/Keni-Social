// Chips del calendario de la rota: chip de evento y chip de turno (con menú contextual
// de CRUD).
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  BellRing,
  Copy,
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
import { Spinner } from "@/components/ui/spinner";
import { ApiError, api, mensajeError } from "@/lib/api";
import { COBERTURA_BADGE } from "@/lib/estado-color";
import {
  COBERTURA,
  COLOR_PRIORIDAD,
  fechaMasDias,
} from "@/lib/rota-calendario";
import { AvatarPersona } from "@/pages/tareas/AvatarPersona";
import type {
  AusenciaRota,
  FranjaSemana,
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
  cubrenPorTurno,
  onClick,
  onCambio,
}: {
  item: ItemEventoCalendario;
  /** Personas de TURNO en la franja de este evento ese día: si nadie lo cogió, son quienes lo cubren. */
  cubrenPorTurno: { id: string; nombre: string }[];
  onClick: () => void;
  onCambio: () => void;
}) {
  const cob = COBERTURA[item.evento.tipo_cobertura] ?? COBERTURA.transmision;
  const Icono = cob.icono;
  // Nombres (primer nombre) de quienes cubren por turno, recortado para no desbordar el chip.
  const nombresTurno = cubrenPorTurno.map((c) => primerNombre(c.nombre));
  const textoTurno =
    nombresTurno.length <= 2
      ? nombresTurno.join(", ")
      : `${nombresTurno.slice(0, 2).join(", ")} +${nombresTurno.length - 2}`;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group/chip flex flex-col gap-0.5 rounded-sm border px-1.5 py-1 text-left text-[11px] leading-tight transition hover:ring-1 hover:ring-primary/40 ${cob.chip}`}
      aria-label={`Cubrir ${item.evento.titulo}`}
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
      {/* Cobertura en 3 estados, de más a menos específico:
          1) Lo COGIÓ alguien (claim) → ese avatar + primer nombre (la misma titularidad que el
             Panorama; es la anulación explícita cuando quieres nombre y apellido / rol).
          2) Nadie lo cogió pero HAY turno en su franja → «Cubierto · <nombres>»: lo cubre quien
             esté de turno ese día, nombrado para saber de un vistazo quién responde.
          3) Nadie lo cogió y NO hay turno en su franja → «Sin cubrir»: hueco real. */}
      {item.cubridores.length > 0 ? (
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          {item.cubridores.map((c) => (
            <span key={c.id} className="inline-flex items-center gap-1">
              <AvatarPersona id={c.id} nombre={c.nombre} size="sm" />
              <span className="truncate font-medium">{primerNombre(c.nombre)}</span>
            </span>
          ))}
        </span>
      ) : cubrenPorTurno.length > 0 ? (
        <span
          className={`inline-flex w-fit items-center rounded border px-1 text-[10px] font-medium ${COBERTURA_BADGE["cubierto-turno"]}`}
        >
          Cubierto · {textoTurno}
        </span>
      ) : (
        <span
          className={`inline-flex w-fit items-center rounded border px-1 text-[10px] font-medium ${COBERTURA_BADGE["sin-cubrir"]}`}
        >
          Sin cubrir
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

/** "HH:MM" → forma compacta para la celda: la hora en punto pierde ":00" ("14:00"→"14"). */
function horaCompacta(hhmm: string): string {
  return hhmm.endsWith(":00") ? String(Number(hhmm.slice(0, 2))) : hhmm;
}

export function ChipTurnoCM({
  turno,
  equipo,
  franjas,
  ausencia,
  editable,
  onCambio,
  variante = "avatar",
}: {
  turno: TurnoRota;
  /** Equipo de la rota (para que `DialogEditarTurno` pueda reasignar). */
  equipo: MiembroRota[];
  /** Franjas vivas de la semana (para que `DialogEditarTurno` ofrezca la franja real). */
  franjas: FranjaSemana[];
  ausencia?: AusenciaRota;
  editable: boolean;
  onCambio: () => void;
  /** "avatar" = círculo con la inicial (rejilla densa); "texto" = el nombre escrito (vista por
   *  días, estilo del calendario mensual). En ambas: × para quitar y menú editar/duplicar/eliminar. */
  variante?: "avatar" | "texto";
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

  // «Duplicar a la semana siguiente»: clona el turno al mismo día de la semana próxima,
  // mismo miembro y franja (el backend mapea la franja por nombre a la semana destino).
  const duplicar = useMutation({
    mutationFn: () =>
      api.duplicarTurno(turno.id, { fecha: fechaMasDias(turno.fecha, 7) }),
    onSuccess: () => {
      toast.success("Turno duplicado a la semana siguiente.");
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

  const esTexto = variante === "texto";
  // Iconos de estado, comunes a ambas variantes (override forzado / ausente ese día).
  const indicadores = (
    <>
      {turno.override && (
        <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400" aria-label="override" />
      )}
      {ausencia && !turno.override && (
        <Plane className="h-3 w-3 shrink-0 text-orange-600 dark:text-orange-400" aria-label="ausente" />
      )}
    </>
  );
  // Identidad + horario a medida según la variante: avatar redondo (rejilla densa) o el nombre
  // escrito con sus horas (vista por días, estilo del mensual).
  const identidad = esTexto ? (
    <>
      <span className="truncate">{turno.miembro_nombre}</span>
      {turno.horario_propio && (
        <span className="shrink-0 tabular-nums text-sky-700/80 dark:text-sky-300/80" aria-label="horario a medida">
          · {horaCompacta(turno.inicio)}–{horaCompacta(turno.fin)}
        </span>
      )}
      {indicadores}
    </>
  ) : (
    <>
      <AvatarPersona id={turno.miembro_id} nombre={turno.miembro_nombre} size="sm" />
      {indicadores}
      {turno.horario_propio && (
        <span
          className="shrink-0 text-[10px] font-medium tabular-nums text-sky-700 dark:text-sky-300"
          aria-label="horario a medida"
        >
          {horaCompacta(turno.inicio)}–{horaCompacta(turno.fin)}
        </span>
      )}
    </>
  );

  if (!editable) {
    // Solo lectura: la identidad (avatar o nombre) con sus iconos; el horario completo y el
    // motivo viven en el rótulo (tooltip flotante en "avatar"; `title` nativo en "texto", que
    // se apila en bloque y no admite el envoltorio inline del Tooltip).
    const chip = (
      <span
        title={esTexto && tieneTooltip ? etiquetaTooltip : undefined}
        className={
          esTexto
            ? "flex w-full items-center gap-1 text-[11px] leading-tight"
            : "inline-flex max-w-full items-center gap-1 text-xs"
        }
      >
        {identidad}
      </span>
    );
    return !esTexto && tieneTooltip ? <Tooltip label={etiquetaTooltip}>{chip}</Tooltip> : chip;
  }

  const itemsMenu: EntradaMenuContextual[] = [
    {
      etiqueta: "Editar detalles…",
      icono: Pencil,
      onClick: () => setEditandoDetalles(true),
    },
    {
      etiqueta: "Duplicar a la semana siguiente",
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
      {/* La identidad (avatar o nombre) + la × para quitar el turno. El click en ella abre el
          menú (editar/duplicar/borrar). En "texto" la × aparece al pasar el ratón. */}
      <span
        title={esTexto && tieneTooltip ? etiquetaTooltip : undefined}
        className={
          esTexto
            ? "group flex w-full cursor-pointer items-center justify-between gap-1 rounded px-1 py-px text-[11px] leading-tight hover:bg-black/[0.04]"
            : "inline-flex max-w-full cursor-pointer items-center gap-1 rounded-full text-xs hover:opacity-80"
        }
      >
        <span className={esTexto ? "inline-flex min-w-0 items-center gap-1" : "contents"}>
          {identidad}
        </span>
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
          className={
            esTexto
              ? "shrink-0 rounded text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-70 disabled:opacity-50"
              : "ml-0.5 rounded text-muted-foreground hover:text-destructive disabled:opacity-50"
          }
        >
          {borrar.isPending ? <Spinner className="h-3 w-3" /> : <X className="h-3 w-3" />}
        </button>
      </span>
    </MenuContextual>
  );

  return (
    <>
      {!esTexto && tieneTooltip ? <Tooltip label={etiquetaTooltip}>{chip}</Tooltip> : chip}
      {editandoDetalles && (
        <DialogEditarTurno
          turno={turno}
          equipo={equipo}
          franjas={franjas}
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
