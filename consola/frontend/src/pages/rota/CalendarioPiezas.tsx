// Piezas del calendario de la rota: celdas, chips de turno/evento, dropdowns y diálogos
// de edición (evento/turno) + popup de carga del equipo. Partido de pages/Rota.tsx.
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BellRing,
  Copy,
  Loader2,
  Pencil,
  Plane,
  Plus,
  ShieldCheck,
  Trash2,
  User,
  Users,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import {
  MenuContextual,
  type EntradaMenuContextual,
} from "@/components/comunes/MenuContextual";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import {
  COBERTURA,
  COLOR_PRIORIDAD,
} from "@/lib/rota-calendario";
import { cn } from "@/lib/utils";
import type {
  AusenciaRota,
  CoordinacionTurno,
  CuerpoCrearTurnoRota,
  EventoRota,
  FranjaSemana,
  FranjaTurno,
  MiembroRota,
  PrioridadEvento,
  TipoCoberturaEvento,
  TurnoRota,
} from "@/types";

import {
  BotonMarcarAvisado,
  PRIORIDADES,
  TIPOS_COBERTURA,
  filtrarEquipoPorMarca,
  type ItemEventoCalendario,
  type RecuadroPersona,
} from "./comun";


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
              Esta persona ya cubrió el sábado anterior. Confirma solo si es una
              cobertura estratégica intencional.
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

/** Diálogo de edición rápida de evento: lo que más se cambia desde el calendario. */
export function DialogEditarEvento({
  evento,
  onCerrar,
  onCambio,
}: {
  evento: EventoRota;
  onCerrar: () => void;
  onCambio: () => void;
}) {
  const [titulo, setTitulo] = React.useState(evento.titulo);
  const [fecha, setFecha] = React.useState(evento.fecha);
  const [hora, setHora] = React.useState(evento.hora);
  const [tipoCobertura, setTipoCobertura] = React.useState<TipoCoberturaEvento>(
    evento.tipo_cobertura,
  );
  const [prioridad, setPrioridad] = React.useState<PrioridadEvento>(evento.prioridad);
  const [contenido, setContenido] = React.useState(evento.contenido);

  const guardar = useMutation({
    mutationFn: () =>
      api.actualizarEventoRota(evento.id, {
        titulo: titulo.trim(),
        fecha,
        hora: hora.trim(),
        tipo_cobertura: tipoCobertura,
        prioridad,
        contenido: contenido.trim(),
      }),
    onSuccess: () => {
      toast.success("Evento guardado.");
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarEventoRota(evento.id),
    onSuccess: () => {
      toast.success("Evento eliminado.");
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar evento</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="ce-titulo">Evento / transmisión</Label>
            <Input
              id="ce-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              maxLength={200}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ce-fecha">Fecha</Label>
              <Input
                id="ce-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ce-hora">Hora</Label>
              <Input
                id="ce-hora"
                value={hora}
                onChange={(e) => setHora(e.target.value)}
                placeholder="16:00"
                maxLength={40}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Cobertura</Label>
              <Select
                value={tipoCobertura}
                onValueChange={(v) => setTipoCobertura(v as TipoCoberturaEvento)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIPOS_COBERTURA.map((t) => (
                    <SelectItem key={t.valor} value={t.valor}>
                      {t.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Prioridad</Label>
              <Select value={prioridad} onValueChange={(v) => setPrioridad(v as PrioridadEvento)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORIDADES.map((p) => (
                    <SelectItem key={p.valor} value={p.valor}>
                      {p.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ce-contenido">Qué sacar</Label>
            <Textarea
              id="ce-contenido"
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              rows={3}
              maxLength={2000}
            />
          </div>
        </div>
        <DialogFooter className="flex-row justify-between gap-2 sm:justify-between">
          <Button
            variant="outline"
            className="text-destructive hover:text-destructive"
            onClick={async () => {
              if (
                await confirmar({
                  mensaje: "¿Borrar este evento? Sus turnos también se perderán.",
                  destructivo: true,
                  textoConfirmar: "Borrar",
                })
              )
                borrar.mutate();
            }}
            disabled={borrar.isPending}
          >
            {borrar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Borrar
          </Button>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button onClick={() => guardar.mutate()} disabled={guardar.isPending}>
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

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
 * seed de cargos del organigrama AMX aún no se ha aplicado a la BD), degrada al
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

// La antigua pestaña `Turnos` (rejilla CRUD por dropdown) se fusionó con el Calendario:
// su cabecera de acciones (badges/copia/aprobar/despublicar/franjas/exportar) y la
// rejilla con dropdown + `ChipTurnoCM` ahora viven dentro de `Calendario` arriba.
// `ChipTurnoCM` y `DialogEditarTurno` (debajo) siguen siendo reutilizables.

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

/** Diálogo para editar detalles de un turno (persona, motivo, nota de relevo). */
export function DialogEditarTurno({
  turno,
  equipo,
  onCerrar,
  onGuardado,
}: {
  turno: TurnoRota;
  equipo: MiembroRota[];
  onCerrar: () => void;
  onGuardado: () => void;
}) {
  const [fecha, setFecha] = React.useState(turno.fecha);
  const [miembroId, setMiembroId] = React.useState(turno.miembro_id);
  const [franja, setFranja] = React.useState<FranjaTurno>(turno.franja);
  const [motivo, setMotivo] = React.useState(turno.motivo);
  const [notaRelevo, setNotaRelevo] = React.useState(turno.nota_relevo);
  // Si el backend devuelve 409 requiere_override, mostramos botón "forzar".
  const [pendienteOverride, setPendienteOverride] = React.useState<{ mensaje: string } | null>(
    null,
  );

  const guardar = useMutation({
    mutationFn: (override: boolean) => {
      const cuerpo: {
        fecha?: string;
        miembro_id?: string;
        franja?: FranjaTurno;
        motivo?: string;
        nota_relevo?: string;
        override?: boolean;
      } = {};
      if (fecha !== turno.fecha) cuerpo.fecha = fecha;
      if (miembroId !== turno.miembro_id) cuerpo.miembro_id = miembroId;
      if (franja !== turno.franja) cuerpo.franja = franja;
      if (motivo !== turno.motivo) cuerpo.motivo = motivo;
      if (notaRelevo !== turno.nota_relevo) cuerpo.nota_relevo = notaRelevo;
      if (override) cuerpo.override = true;
      return api.actualizarTurno(turno.id, cuerpo);
    },
    onSuccess: () => {
      toast.success("Turno actualizado.");
      onGuardado();
    },
    onError: (e) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        (e.cuerpo?.requiere_override as boolean | undefined)
      ) {
        setPendienteOverride({ mensaje: e.message });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const sinCambios =
    fecha === turno.fecha &&
    miembroId === turno.miembro_id &&
    franja === turno.franja &&
    motivo === turno.motivo &&
    notaRelevo === turno.nota_relevo;

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar turno</DialogTitle>
          <DialogDescription>
            Edita los detalles del turno. Las reglas se validan al guardar.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="et-fecha">Fecha</Label>
              <Input
                id="et-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Franja</Label>
              <Select value={franja} onValueChange={(v) => setFranja(v as FranjaTurno)}>
                <SelectTrigger aria-label="Franja">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="matutino">Mañana</SelectItem>
                  <SelectItem value="vespertino">Tarde</SelectItem>
                  <SelectItem value="descanso">Descanso</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Persona</Label>
            <Select value={miembroId} onValueChange={setMiembroId}>
              <SelectTrigger aria-label="Persona del turno">
                <SelectValue placeholder="Sin asignar" />
              </SelectTrigger>
              <SelectContent>
                {equipo.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="et-motivo">
              Motivo <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Input
              id="et-motivo"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Cobertura forzada por evento crítico…"
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="et-nota">
              Nota de relevo{" "}
              <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Textarea
              id="et-nota"
              value={notaRelevo}
              onChange={(e) => setNotaRelevo(e.target.value)}
              placeholder="Qué queda pendiente para el siguiente turno…"
              rows={3}
              maxLength={1000}
            />
          </div>
          {pendienteOverride && (
            <div className="rounded-md border border-amber-300/60 bg-amber-50/40 p-3 text-sm text-amber-900 dark:bg-amber-950/20 dark:text-amber-300">
              <p className="font-medium">{pendienteOverride.mensaje}</p>
              <p className="mt-1 text-xs">
                Confirma solo si es una cobertura estratégica intencional.
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          {pendienteOverride ? (
            <Button
              variant="outline"
              className="text-amber-700 hover:text-amber-700 dark:text-amber-400"
              onClick={() => guardar.mutate(true)}
              disabled={guardar.isPending}
            >
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              <AlertTriangle className="h-4 w-4" /> Forzar override
            </Button>
          ) : (
            <Button onClick={() => guardar.mutate(false)} disabled={sinCambios || guardar.isPending}>
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Popup "Carga del equipo" -----------------------------------------------

/**
 * Resumen de carga del equipo de la semana, en un diálogo. Antes era un panel
 * colapsable bajo el calendario; ahora se invoca bajo demanda desde el menú "Más"
 * para no alargar la vista. El componente sólo se monta cuando el popup está abierto,
 * así que la query arranca al abrir.
 */
export function DialogCargaEquipo({ lunes, onCerrar }: { lunes: string; onCerrar: () => void }) {
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "carga", lunes, marcaActiva],
    queryFn: ({ signal }) =>
      api.cargaRota({ lunes, marca: marcaActiva ?? undefined }, signal),
    enabled: !!lunes,
  });
  const miembros = q.data?.miembros ?? [];
  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="h-4 w-4" /> Carga del equipo
          </DialogTitle>
          <DialogDescription>
            Cuánto trabajo lleva cada persona esta semana.
          </DialogDescription>
        </DialogHeader>
        {q.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : q.isError ? (
          <BloqueError
            titulo="No se pudo cargar el resumen"
            mensaje={mensajeError(q.error)}
            onReintentar={() => void q.refetch()}
            cargando={q.isFetching}
          />
        ) : miembros.length === 0 ? (
          <EstadoVacio
            icono={Users}
            titulo="Sin datos"
            texto="No hay miembros del equipo todavía."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Persona</TableHead>
                <TableHead className="text-right">Eventos</TableHead>
                <TableHead className="text-right">Días trabajados</TableHead>
                <TableHead>Sábado</TableHead>
                <TableHead className="text-right">Descansos</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {miembros.map((m) => (
                <TableRow key={m.miembro_id}>
                  <TableCell className="font-medium">{m.nombre}</TableCell>
                  <TableCell
                    className={
                      m.eventos >= 7
                        ? "text-right font-medium text-red-600 dark:text-red-400"
                        : "text-right"
                    }
                  >
                    {m.eventos}
                  </TableCell>
                  <TableCell className="text-right">{m.dias_trabajados}</TableCell>
                  <TableCell>
                    {m.sabado ? (
                      <Badge variant="outline" className="font-normal">
                        Sábado
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">{m.descansos}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
    </Dialog>
  );
}

