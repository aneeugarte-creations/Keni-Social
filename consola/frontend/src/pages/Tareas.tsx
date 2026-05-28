import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Calendar,
  CheckCircle2,
  Circle,
  CircleDot,
  ClipboardList,
  ExternalLink,
  Link2,
  Loader2,
  ListTodo,
  Plus,
  Radio,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import { Tooltip } from "@/components/ui/tooltip";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { EventoSinCubrir, ProyectoTarea, Tarea, UsuarioTarea } from "@/types";

const CLAVE_TAREAS = ["tareas"] as const;

const CABECERA = {
  titulo: "Pendientes",
  descripcion:
    "Pendientes del equipo: eventos por cubrir, tareas libres y lo que dejan los relevos. Compartido para todo el equipo: crea, asigna, mueve y márcalo como hecho.",
};

/** Valor del selector de responsable cuando un pendiente queda sin asignar. */
const SIN_RESPONSABLE = "__sin_asignar__";
/** Valor del filtro de proyecto que muestra el tablero completo. */
const TODOS_PROYECTOS = "__todos__";
/** Valor del selector "Asociado a un evento" cuando no hay evento asociado. */
const SIN_EVENTO = "__sin_evento__";
/**
 * Valor del selector de "Proyecto" cuando el pendiente es libre (sin proyecto).
 * Es un sentinel UI: Radix Select no permite items con `value=""`. Al enviar al
 * backend lo traducimos a "".
 */
const SIN_PROYECTO = "__sin_proyecto__";
/** Valor del filtro por responsable que muestra el tablero completo. */
const TODOS_RESPONSABLES = "__todos__";
/** Valor del filtro por responsable que muestra solo los pendientes sin asignar. */
const RESPONSABLE_SIN_ASIGNAR = "__sin_asignar__";
/** Valor del filtro por tipo (asociadas a evento / libres / todas). */
type FiltroTipo = "todas" | "evento" | "libre";

/**
 * Estados compartidos de un pendiente (los del backend, `estados.ESTADOS_TAREA`).
 * El orden marca el avance del ciclo de vida: pendiente -> en curso -> hecha (#145).
 */
const ORDEN_ESTADOS = ["pendiente", "en_curso", "hecha"] as const;
type EstadoTareaUi = (typeof ORDEN_ESTADOS)[number];

const ESTADO_LABEL: Record<string, string> = {
  pendiente: "Pendiente",
  en_curso: "En curso",
  hecha: "Hecha",
};

type VarianteBadge = "secondary" | "aviso" | "ok" | "error" | "outline";

const ESTADO_VARIANTE: Record<string, VarianteBadge> = {
  pendiente: "aviso",
  en_curso: "secondary",
  hecha: "ok",
};

function etiquetaEstado(estado: string): string {
  return ESTADO_LABEL[estado] ?? estado;
}

/**
 * Siguiente estado del ciclo de vida al avanzar (pendiente -> en curso -> hecha ->
 * pendiente). Un estado desconocido (legado) vuelve al inicio del ciclo.
 */
function estadoSiguiente(estado: string): EstadoTareaUi {
  const i = ORDEN_ESTADOS.indexOf(estado as EstadoTareaUi);
  return ORDEN_ESTADOS[(i + 1) % ORDEN_ESTADOS.length] ?? "pendiente";
}

/** Icono del ciclo de vida según el estado actual. */
function IconoEstado({ estado, className }: { estado: string; className?: string }) {
  if (estado === "hecha")
    return <CheckCircle2 className={cn("text-emerald-600 dark:text-emerald-400", className)} />;
  if (estado === "en_curso")
    return <CircleDot className={cn("text-amber-600 dark:text-amber-400", className)} />;
  return <Circle className={cn("text-muted-foreground", className)} />;
}

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function formatearFecha(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Tablero de pendientes COMPARTIDO del equipo (#145, F5): panel izquierdo para crear
 * un pendiente (con o sin proyecto, opcionalmente atado a un evento de la rota) con
 * responsable y enlace de acción opcionales; panel derecho con la lista de eventos
 * sin cubrir como "pendientes implícitos", los filtros (proyecto / responsable / tipo),
 * la barra de estatus compartida (cuántos pendientes / en curso / hechos) y la lista,
 * editable por todo el equipo. Consume el backend de tareas (`/api/tareas`), que ya
 * es multiusuario.
 */
export default function Tareas() {
  const query = useQuery({
    queryKey: CLAVE_TAREAS,
    queryFn: ({ signal }) => api.tareas(signal),
  });

  const tareas = query.data?.tareas ?? [];
  const proyectos = query.data?.proyectos ?? [];
  const usuarios = query.data?.usuarios ?? [];
  const eventosSinCubrir = query.data?.eventos_sin_cubrir ?? [];

  // Evento que el usuario quiere prepopular en el formulario al hacer clic en
  // un chip de "Eventos sin cubrir". Lo mantenemos en el padre para que la
  // sección de chips y el formulario estén conectados.
  const [eventoPrellenado, setEventoPrellenado] = React.useState<EventoSinCubrir | null>(null);

  return (
    <>
      <PageHeader {...CABECERA} />
      <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <NuevaTarea
          proyectos={proyectos}
          usuarios={usuarios}
          eventos={eventosSinCubrir}
          cargando={query.isPending}
          eventoPrellenado={eventoPrellenado}
          onEventoConsumido={() => setEventoPrellenado(null)}
        />
        <div className="space-y-4">
          {eventosSinCubrir.length > 0 && (
            <EventosSinCubrir
              eventos={eventosSinCubrir}
              onSeleccionar={(evento) => setEventoPrellenado(evento)}
            />
          )}
          <ListaTareas
            tareas={tareas}
            proyectos={proyectos}
            usuarios={usuarios}
            cargando={query.isPending}
            error={query.isError ? mensajeError(query.error) : null}
            onReintentar={() => void query.refetch()}
            reintentando={query.isFetching}
          />
        </div>
      </div>
    </>
  );
}

// --- Alta (panel izquierdo) ------------------------------------------------

function NuevaTarea({
  proyectos,
  usuarios,
  eventos,
  cargando,
  eventoPrellenado,
  onEventoConsumido,
}: {
  proyectos: ProyectoTarea[];
  usuarios: UsuarioTarea[];
  eventos: EventoSinCubrir[];
  cargando: boolean;
  eventoPrellenado: EventoSinCubrir | null;
  onEventoConsumido: () => void;
}) {
  const queryClient = useQueryClient();
  // Proyecto: OPCIONAL (#145, refresh). Por defecto "(sin proyecto)" → "".
  const [proyecto, setProyecto] = React.useState<string>(SIN_PROYECTO);
  const [eventoId, setEventoId] = React.useState<string>(SIN_EVENTO);
  const [titulo, setTitulo] = React.useState("");
  const [detalle, setDetalle] = React.useState("");
  const [responsable, setResponsable] = React.useState(SIN_RESPONSABLE);
  const [enlace, setEnlace] = React.useState("");

  // Si llega un evento desde "Eventos sin cubrir" (clic en chip), prepoblamos
  // el selector y el título (solo si el usuario aún no escribió nada).
  React.useEffect(() => {
    if (!eventoPrellenado) return;
    setEventoId(eventoPrellenado.id);
    setTitulo((actual) =>
      actual.trim().length === 0
        ? `Cubrir: ${eventoPrellenado.titulo} (${eventoPrellenado.fecha} ${eventoPrellenado.hora})`
        : actual,
    );
    onEventoConsumido();
  }, [eventoPrellenado, onEventoConsumido]);

  const crear = useMutation({
    mutationFn: () =>
      api.crearTarea({
        // Mandamos "" si el usuario eligió "(sin proyecto)": el backend lo
        // trata como pendiente libre (#145, refresh).
        proyecto: proyecto === SIN_PROYECTO ? "" : proyecto,
        evento_id: eventoId === SIN_EVENTO ? undefined : eventoId,
        titulo: titulo.trim(),
        detalle: detalle.trim(),
        responsable_id: responsable === SIN_RESPONSABLE ? "" : responsable,
        enlace: enlace.trim(),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success("Pendiente creado.");
      setTitulo("");
      setDetalle("");
      setResponsable(SIN_RESPONSABLE);
      setEnlace("");
      setEventoId(SIN_EVENTO);
      // Proyecto se queda como esté: respetamos la elección del usuario.
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = titulo.trim().length > 0 && !crear.isPending;

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ClipboardList className="h-4 w-4" />
          Nuevo pendiente
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="tarea-proyecto">
            Proyecto <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Select value={proyecto} onValueChange={setProyecto} disabled={cargando}>
            <SelectTrigger id="tarea-proyecto" aria-label="Proyecto">
              <SelectValue placeholder="(sin proyecto)" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SIN_PROYECTO}>(sin proyecto)</SelectItem>
              {proyectos.map((p) => (
                <SelectItem key={p.id} value={p.id} disabled={!p.existe}>
                  {p.nombre}
                  {!p.existe ? " (carpeta no encontrada)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tarea-evento">
            Asociado a un evento{" "}
            <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Select value={eventoId} onValueChange={setEventoId} disabled={cargando}>
            <SelectTrigger id="tarea-evento" aria-label="Asociado a un evento">
              <SelectValue placeholder="(ninguno)" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SIN_EVENTO}>(ninguno)</SelectItem>
              {eventos.map((e) => (
                <SelectItem key={e.id} value={e.id}>
                  {e.fecha} {e.hora} · {e.titulo}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tarea-titulo">Título</Label>
          <Input
            id="tarea-titulo"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ej. Revisar el copy de la nota de las 8"
            maxLength={200}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tarea-detalle">
            Detalle <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Textarea
            id="tarea-detalle"
            value={detalle}
            onChange={(e) => setDetalle(e.target.value)}
            placeholder="Contexto para ti o para el asistente al abrir la tarea."
            rows={4}
            maxLength={8000}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tarea-responsable">
            Responsable{" "}
            <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Select value={responsable} onValueChange={setResponsable} disabled={cargando}>
            <SelectTrigger id="tarea-responsable" aria-label="Responsable">
              <SelectValue placeholder="Sin asignar" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
              {usuarios.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.usuario}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tarea-enlace">
            Enlace de acción{" "}
            <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="tarea-enlace"
            value={enlace}
            onChange={(e) => setEnlace(e.target.value)}
            placeholder="Ej. /asistente o https://…"
            maxLength={2000}
          />
        </div>
        <div className="flex justify-end">
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear pendiente
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// --- Sección "Eventos sin cubrir" -------------------------------------------

/**
 * Lista compacta de eventos próximos cuya cobertura sigue sin pendiente: chips
 * clicables que prepopulan el formulario de "Nuevo pendiente" con el evento
 * asociado. Es la lectura "pendientes implícitos" para equipos como Claro
 * Sports / UnoTV, que organizan su jornada por eventos de la rota más que por
 * tareas libres.
 */
function EventosSinCubrir({
  eventos,
  onSeleccionar,
}: {
  eventos: EventoSinCubrir[];
  onSeleccionar: (evento: EventoSinCubrir) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Calendar className="h-4 w-4" />
          Eventos sin cubrir esta semana y la siguiente
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {eventos.map((e) => (
            <ChipEventoSinCubrir
              key={e.id}
              evento={e}
              onSeleccionar={() => onSeleccionar(e)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/** Estilo del chip según el tipo de cobertura del evento (espeja Rota.tsx). */
const ESTILO_COBERTURA: Record<EventoSinCubrir["tipo_cobertura"], string> = {
  transmision:
    "border-sky-300 bg-sky-50 text-sky-800 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300 dark:hover:bg-sky-900/40",
  imagenes:
    "border-violet-300 bg-violet-50 text-violet-800 hover:bg-violet-100 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300 dark:hover:bg-violet-900/40",
  no_cubrir:
    "border-zinc-300 bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-400 dark:hover:bg-zinc-800/60",
};

function ChipEventoSinCubrir({
  evento,
  onSeleccionar,
}: {
  evento: EventoSinCubrir;
  onSeleccionar: () => void;
}) {
  const Icono = evento.tipo_cobertura === "imagenes" ? Calendar : Radio;
  return (
    <button
      type="button"
      onClick={onSeleccionar}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors",
        ESTILO_COBERTURA[evento.tipo_cobertura] ?? ESTILO_COBERTURA.transmision,
      )}
      aria-label={`Crear pendiente para ${evento.titulo} (${evento.fecha} ${evento.hora})`}
    >
      <Icono className="h-3 w-3 shrink-0" />
      <span className="truncate font-medium">{evento.titulo}</span>
      <span className="opacity-80">
        · {evento.fecha} {evento.hora}
      </span>
    </button>
  );
}

// --- Listado (panel derecho) -----------------------------------------------

function ListaTareas({
  tareas,
  proyectos,
  usuarios,
  cargando,
  error,
  onReintentar,
  reintentando,
}: {
  tareas: Tarea[];
  proyectos: ProyectoTarea[];
  usuarios: UsuarioTarea[];
  cargando: boolean;
  error: string | null;
  onReintentar: () => void;
  reintentando: boolean;
}) {
  // Filtros se aplican en cliente: el tablero llega completo (los #s de la
  // barra de estatus reflejan el filtro activo).
  const [filtroProyecto, setFiltroProyecto] = React.useState(TODOS_PROYECTOS);
  const [filtroResponsable, setFiltroResponsable] =
    React.useState<string>(TODOS_RESPONSABLES);
  const [filtroTipo, setFiltroTipo] = React.useState<FiltroTipo>("todas");

  const tareasFiltradas = React.useMemo(() => {
    return tareas.filter((t) => {
      if (filtroProyecto !== TODOS_PROYECTOS && t.proyecto !== filtroProyecto) return false;
      if (filtroResponsable === RESPONSABLE_SIN_ASIGNAR) {
        if (t.responsable_id) return false;
      } else if (filtroResponsable !== TODOS_RESPONSABLES) {
        if (t.responsable_id !== filtroResponsable) return false;
      }
      if (filtroTipo === "evento" && !t.evento_id) return false;
      if (filtroTipo === "libre" && t.evento_id) return false;
      return true;
    });
  }, [tareas, filtroProyecto, filtroResponsable, filtroTipo]);

  if (cargando) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <BloqueError
        titulo="No se pudieron cargar las tareas"
        mensaje={error}
        onReintentar={onReintentar}
        cargando={reintentando}
      />
    );
  }

  const hayProyectos = proyectos.length > 0;
  const hayFiltrosActivos =
    filtroProyecto !== TODOS_PROYECTOS ||
    filtroResponsable !== TODOS_RESPONSABLES ||
    filtroTipo !== "todas";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {hayProyectos && (
          <div className="flex items-center gap-2">
            <Label htmlFor="filtro-proyecto" className="text-sm text-muted-foreground">
              Proyecto
            </Label>
            <Select value={filtroProyecto} onValueChange={setFiltroProyecto}>
              <SelectTrigger
                id="filtro-proyecto"
                aria-label="Filtrar por proyecto"
                className="w-60"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS_PROYECTOS}>Todos los proyectos</SelectItem>
                {proyectos.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <ChipsFiltroTipo valor={filtroTipo} onCambio={setFiltroTipo} />
      </div>
      <ChipsFiltroResponsable
        usuarios={usuarios}
        valor={filtroResponsable}
        onCambio={setFiltroResponsable}
      />

      {tareasFiltradas.length === 0 ? (
        <EstadoVacio
          icono={ListTodo}
          titulo="Sin pendientes"
          texto={
            tareas.length === 0
              ? "Crea el primer pendiente con el formulario de la izquierda."
              : hayFiltrosActivos
                ? "No hay pendientes con los filtros activos. Cambia los filtros o crea uno."
                : "No hay pendientes que mostrar."
          }
        />
      ) : (
        <>
          <BarraEstatus tareas={tareasFiltradas} />
          <div className="space-y-3">
            {tareasFiltradas.map((t) => (
              <TarjetaTarea key={t.id} tarea={t} proyectos={proyectos} usuarios={usuarios} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/** Chips para filtrar por tipo: todas / asociadas a evento / libres. */
function ChipsFiltroTipo({
  valor,
  onCambio,
}: {
  valor: FiltroTipo;
  onCambio: (v: FiltroTipo) => void;
}) {
  const opciones: { valor: FiltroTipo; etiqueta: string }[] = [
    { valor: "todas", etiqueta: "Todas" },
    { valor: "evento", etiqueta: "Asociadas a evento" },
    { valor: "libre", etiqueta: "Libres" },
  ];
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted-foreground">Tipo</span>
      <div className="flex flex-wrap gap-1.5">
        {opciones.map((op) => (
          <Button
            key={op.valor}
            type="button"
            variant={valor === op.valor ? "default" : "outline"}
            size="sm"
            className="h-7 px-2.5 text-xs"
            onClick={() => onCambio(op.valor)}
            aria-pressed={valor === op.valor}
          >
            {op.etiqueta}
          </Button>
        ))}
      </div>
    </div>
  );
}

/** Chips para filtrar por responsable (uno por usuario + "Sin asignar" + "Todos"). */
function ChipsFiltroResponsable({
  usuarios,
  valor,
  onCambio,
}: {
  usuarios: UsuarioTarea[];
  valor: string;
  onCambio: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-muted-foreground">Responsable</span>
      <div className="flex flex-wrap gap-1.5">
        <Button
          type="button"
          variant={valor === TODOS_RESPONSABLES ? "default" : "outline"}
          size="sm"
          className="h-7 px-2.5 text-xs"
          onClick={() => onCambio(TODOS_RESPONSABLES)}
          aria-pressed={valor === TODOS_RESPONSABLES}
        >
          Todos
        </Button>
        <Button
          type="button"
          variant={valor === RESPONSABLE_SIN_ASIGNAR ? "default" : "outline"}
          size="sm"
          className="h-7 px-2.5 text-xs"
          onClick={() => onCambio(RESPONSABLE_SIN_ASIGNAR)}
          aria-pressed={valor === RESPONSABLE_SIN_ASIGNAR}
        >
          Sin asignar
        </Button>
        {usuarios.map((u) => (
          <Button
            key={u.id}
            type="button"
            variant={valor === u.id ? "default" : "outline"}
            size="sm"
            className="h-7 px-2.5 text-xs"
            onClick={() => onCambio(u.id)}
            aria-pressed={valor === u.id}
          >
            {u.usuario}
          </Button>
        ))}
      </div>
    </div>
  );
}

/** Barra de estatus compartida: recuento por estado del ciclo de vida. */
function BarraEstatus({ tareas }: { tareas: Tarea[] }) {
  const conteo = React.useMemo(() => {
    const base: Record<string, number> = { pendiente: 0, en_curso: 0, hecha: 0 };
    for (const t of tareas) base[t.estado] = (base[t.estado] ?? 0) + 1;
    return base;
  }, [tareas]);

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm"
      role="status"
      aria-label="Resumen de tareas por estado"
    >
      <span className="text-muted-foreground">
        {tareas.length} {tareas.length === 1 ? "pendiente" : "pendientes"}
      </span>
      {ORDEN_ESTADOS.map((estado) => (
        <Badge key={estado} variant={ESTADO_VARIANTE[estado] ?? "secondary"} className="font-normal">
          {conteo[estado] ?? 0} {etiquetaEstado(estado).toLowerCase()}
        </Badge>
      ))}
    </div>
  );
}

function TarjetaTarea({
  tarea,
  proyectos,
  usuarios,
}: {
  tarea: Tarea;
  proyectos: ProyectoTarea[];
  usuarios: UsuarioTarea[];
}) {
  const queryClient = useQueryClient();

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });

  const cambiarEstado = useMutation({
    mutationFn: (estado: EstadoTareaUi) => api.actualizarTarea(tarea.id, { estado }),
    onSuccess: () => invalidar(),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const reasignar = useMutation({
    mutationFn: (responsable_id: string) => api.actualizarTarea(tarea.id, { responsable_id }),
    onSuccess: () => invalidar(),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarTarea(tarea.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? "Pendiente borrado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const abrir = useMutation({
    mutationFn: () => api.abrirTarea(tarea.id),
    onSuccess: (res) => toast.success(res?.mensaje ?? "Abriendo en el asistente…"),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const proyectoAllowlist = proyectos.find((p) => p.id === tarea.proyecto);
  // Si el backend manda `proyecto_existe` lo respetamos; si no, caemos al
  // estado de la allowlist (compatibilidad).
  const proyectoExiste =
    tarea.proyecto_existe !== undefined ? tarea.proyecto_existe : proyectoAllowlist?.existe ?? false;
  const tieneProyecto = tarea.proyecto.trim().length > 0;
  const puedeAbrir = tieneProyecto && proyectoExiste;
  const nombreProyecto =
    tarea.proyecto_nombre || proyectoAllowlist?.nombre || tarea.proyecto;
  const hecha = tarea.estado === "hecha";
  const fecha = formatearFecha(tarea.fecha);
  const siguiente = estadoSiguiente(tarea.estado);
  const tieneEnlace = tarea.enlace.trim().length > 0;
  const tieneEvento = Boolean(tarea.evento_id && tarea.evento_titulo);

  return (
    <Card className={cn(hecha && "opacity-60")}>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("font-medium leading-snug", hecha && "line-through")}>
                {tarea.titulo}
              </span>
              {tieneProyecto && (
                <Badge variant="outline" className="font-normal">
                  {nombreProyecto}
                </Badge>
              )}
              <Badge variant={ESTADO_VARIANTE[tarea.estado] ?? "secondary"} className="font-normal">
                {etiquetaEstado(tarea.estado)}
              </Badge>
            </div>
            {tieneEvento && (
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="outline" className="gap-1 font-normal">
                  <Calendar className="h-3 w-3" />
                  {tarea.evento_fecha} {tarea.evento_hora} · {tarea.evento_titulo}
                </Badge>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {fecha && <span>{fecha}</span>}
              <Autor nombre={tarea.autor_nombre} className="text-xs" />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Tooltip label={`Pasar a "${etiquetaEstado(siguiente)}"`}>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Pasar a ${etiquetaEstado(siguiente)}`}
                onClick={() => cambiarEstado.mutate(siguiente)}
                disabled={cambiarEstado.isPending}
              >
                {cambiarEstado.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <IconoEstado estado={tarea.estado} className="h-4 w-4" />
                )}
              </Button>
            </Tooltip>
            {tieneEnlace && (
              <Tooltip label="Abrir enlace de acción">
                <Button asChild variant="ghost" size="icon" aria-label="Abrir enlace de acción">
                  <a href={tarea.enlace} target="_blank" rel="noreferrer">
                    <Link2 className="h-4 w-4" />
                  </a>
                </Button>
              </Tooltip>
            )}
            {puedeAbrir && (
              <Tooltip label="Abrir en Claude Code">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Abrir en Claude Code"
                  onClick={() => abrir.mutate()}
                  disabled={abrir.isPending}
                >
                  {abrir.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <ExternalLink className="h-4 w-4" />
                  )}
                </Button>
              </Tooltip>
            )}
            <Tooltip label="Borrar">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Borrar tarea"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => borrar.mutate()}
                disabled={borrar.isPending}
              >
                {borrar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </Button>
            </Tooltip>
          </div>
        </div>
        {tarea.detalle && (
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{tarea.detalle}</p>
        )}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Responsable</span>
          <Select
            value={tarea.responsable_id || SIN_RESPONSABLE}
            onValueChange={(v) => reasignar.mutate(v === SIN_RESPONSABLE ? "" : v)}
            disabled={reasignar.isPending}
          >
            <SelectTrigger
              aria-label="Responsable del pendiente"
              className="h-7 w-48 text-xs"
            >
              <SelectValue placeholder="Sin asignar" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
              {usuarios.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.usuario}
                </SelectItem>
              ))}
              {/* Responsable legado que ya no está en la lista de usuarios: lo mostramos
                  para no perder la asignación visible. */}
              {tarea.responsable_id &&
                !usuarios.some((u) => u.id === tarea.responsable_id) && (
                  <SelectItem value={tarea.responsable_id}>
                    {tarea.responsable_nombre || "desconocido"}
                  </SelectItem>
                )}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  );
}
