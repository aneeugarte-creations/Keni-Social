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
import type { ProyectoTarea, Tarea, UsuarioTarea } from "@/types";

const CLAVE_TAREAS = ["tareas"] as const;

const CABECERA = {
  titulo: "Pendientes",
  descripcion:
    "Pendientes del equipo: lo que hay que hacer y lo que dejan los relevos. Compartido para todo el equipo: crea, asigna, mueve y márcalo como hecho.",
};

/** Valor del selector de responsable cuando un pendiente queda sin asignar. */
const SIN_RESPONSABLE = "__sin_asignar__";
/** Valor del filtro por responsable que muestra el tablero completo. */
const TODOS_RESPONSABLES = "__todos__";
/** Valor del filtro por responsable que muestra solo los pendientes sin asignar. */
const RESPONSABLE_SIN_ASIGNAR = "__sin_asignar__";

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
 * un pendiente (título, notas y responsable opcional) y panel derecho con un único
 * filtro compacto por responsable, la barra de estatus compartida (cuántos pendientes /
 * en curso / hechos) y la lista, editable por todo el equipo. Consume el backend de
 * tareas (`/api/tareas`), que ya es multiusuario.
 */
export default function Tareas() {
  const query = useQuery({
    queryKey: CLAVE_TAREAS,
    queryFn: ({ signal }) => api.tareas(signal),
  });

  const tareas = query.data?.tareas ?? [];
  const proyectos = query.data?.proyectos ?? [];
  const usuarios = query.data?.usuarios ?? [];

  return (
    // Ocupa toda el área visible (alto del <main>, ~100vh menos topbar + padding)
    // para que el panel "Nuevo pendiente" llegue hasta el fondo de la página.
    <div className="flex flex-col lg:min-h-[calc(100vh-6rem)]">
      <PageHeader {...CABECERA} />
      <div className="grid gap-6 lg:flex-1 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <NuevaTarea usuarios={usuarios} cargando={query.isPending} />
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
  );
}

// --- Alta (panel izquierdo) ------------------------------------------------

function NuevaTarea({
  usuarios,
  cargando,
}: {
  usuarios: UsuarioTarea[];
  cargando: boolean;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [detalle, setDetalle] = React.useState("");
  const [responsable, setResponsable] = React.useState(SIN_RESPONSABLE);

  const crear = useMutation({
    mutationFn: () =>
      api.crearTarea({
        titulo: titulo.trim(),
        detalle: detalle.trim(),
        responsable_id: responsable === SIN_RESPONSABLE ? "" : responsable,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success("Pendiente creado.");
      setTitulo("");
      setDetalle("");
      setResponsable(SIN_RESPONSABLE);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = titulo.trim().length > 0 && !crear.isPending;

  return (
    <Card className="flex h-fit flex-col lg:h-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ClipboardList className="h-4 w-4" />
          Nuevo pendiente
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col space-y-4">
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
        {/* Notas ocupa el alto sobrante para que el panel cubra toda la página. */}
        <div className="flex flex-1 flex-col space-y-1.5">
          <Label htmlFor="tarea-detalle">
            Notas <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Textarea
            id="tarea-detalle"
            value={detalle}
            onChange={(e) => setDetalle(e.target.value)}
            placeholder="Contexto, enlaces o cualquier detalle para el equipo."
            rows={5}
            maxLength={8000}
            className="min-h-32 flex-1 resize-none"
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
  // El único filtro vive en cliente: el tablero llega completo y los #s de la
  // barra de estatus reflejan el responsable filtrado.
  const [filtroResponsable, setFiltroResponsable] =
    React.useState<string>(TODOS_RESPONSABLES);

  const tareasFiltradas = React.useMemo(() => {
    return tareas.filter((t) => {
      if (filtroResponsable === RESPONSABLE_SIN_ASIGNAR) return !t.responsable_id;
      if (filtroResponsable !== TODOS_RESPONSABLES) return t.responsable_id === filtroResponsable;
      return true;
    });
  }, [tareas, filtroResponsable]);

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

  const hayFiltroActivo = filtroResponsable !== TODOS_RESPONSABLES;

  return (
    <div className="space-y-4">
      <FiltroResponsable
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
              : hayFiltroActivo
                ? "No hay pendientes para ese responsable. Cambia el filtro o crea uno."
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

/** Filtro compacto por responsable: Todos / Sin asignar / un usuario. */
function FiltroResponsable({
  usuarios,
  valor,
  onCambio,
}: {
  usuarios: UsuarioTarea[];
  valor: string;
  onCambio: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="filtro-responsable" className="text-sm text-muted-foreground">
        Responsable
      </Label>
      <Select value={valor} onValueChange={onCambio}>
        <SelectTrigger
          id="filtro-responsable"
          aria-label="Filtrar por responsable"
          className="h-8 w-56"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TODOS_RESPONSABLES}>Todos</SelectItem>
          <SelectItem value={RESPONSABLE_SIN_ASIGNAR}>Sin asignar</SelectItem>
          {usuarios.map((u) => (
            <SelectItem key={u.id} value={u.id}>
              {u.usuario}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
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
