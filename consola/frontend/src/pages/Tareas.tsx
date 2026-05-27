import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Circle,
  ClipboardList,
  ExternalLink,
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
import type { ProyectoTarea, Tarea } from "@/types";

const CLAVE_TAREAS = ["tareas"] as const;

const CABECERA = {
  titulo: "Pendientes",
  descripcion:
    "Las tareas por proyecto, con su estado. Crea pendientes, márcalos como hechos y ábrelos en el asistente. Todo local; nada sale a la red.",
};

/**
 * Estados compartidos de una tarea (los del backend, `db.ESTADOS_TAREA`). El
 * orden marca el avance del ciclo de vida (pendiente -> hecha).
 */
const ORDEN_ESTADOS = ["pendiente", "hecha"] as const;
type EstadoTareaUi = (typeof ORDEN_ESTADOS)[number];

const ESTADO_LABEL: Record<string, string> = {
  pendiente: "Pendiente",
  hecha: "Hecha",
};

type VarianteBadge = "secondary" | "aviso" | "ok" | "error" | "outline";

const ESTADO_VARIANTE: Record<string, VarianteBadge> = {
  pendiente: "aviso",
  hecha: "ok",
};

function etiquetaEstado(estado: string): string {
  return ESTADO_LABEL[estado] ?? estado;
}

/** Estado al que avanza al alternar (pendiente <-> hecha). */
function estadoAlternado(estado: string): EstadoTareaUi {
  return estado === "hecha" ? "pendiente" : "hecha";
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
 * Vista editorial de pendientes (#104, F-C-19): panel izquierdo para crear una
 * tarea sobre un proyecto de la allowlist; panel derecho con la barra de estatus
 * compartida (cuántas pendientes / hechas) y la lista, editable. Consume el
 * backend de tareas que ya existe (`/api/tareas`).
 */
export default function Tareas() {
  const query = useQuery({
    queryKey: CLAVE_TAREAS,
    queryFn: ({ signal }) => api.tareas(signal),
  });

  const tareas = query.data?.tareas ?? [];
  const proyectos = query.data?.proyectos ?? [];

  return (
    <>
      <PageHeader {...CABECERA} />
      <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <NuevaTarea proyectos={proyectos} cargando={query.isPending} />
        <ListaTareas
          tareas={tareas}
          proyectos={proyectos}
          cargando={query.isPending}
          error={query.isError ? mensajeError(query.error) : null}
          onReintentar={() => void query.refetch()}
          reintentando={query.isFetching}
        />
      </div>
    </>
  );
}

// --- Alta (panel izquierdo) ------------------------------------------------

function NuevaTarea({ proyectos, cargando }: { proyectos: ProyectoTarea[]; cargando: boolean }) {
  const queryClient = useQueryClient();
  const [proyecto, setProyecto] = React.useState("");
  const [titulo, setTitulo] = React.useState("");
  const [detalle, setDetalle] = React.useState("");

  // Preselecciona el primer proyecto disponible cuando llega la allowlist.
  React.useEffect(() => {
    if (!proyecto && proyectos.length > 0) setProyecto(proyectos[0].id);
  }, [proyecto, proyectos]);

  const crear = useMutation({
    mutationFn: () =>
      api.crearTarea({ proyecto, titulo: titulo.trim(), detalle: detalle.trim() }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success("Tarea creada.");
      setTitulo("");
      setDetalle("");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const sinProyectos = !cargando && proyectos.length === 0;
  const puedeCrear = titulo.trim().length > 0 && proyecto !== "" && !crear.isPending;

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ClipboardList className="h-4 w-4" />
          Nueva tarea
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {sinProyectos ? (
          <p className="text-sm text-muted-foreground">
            No hay proyectos configurados. Da de alta un proyecto en Agentes para poder crear
            tareas.
          </p>
        ) : (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="tarea-proyecto">Proyecto</Label>
              <Select value={proyecto} onValueChange={setProyecto} disabled={cargando}>
                <SelectTrigger id="tarea-proyecto" aria-label="Proyecto">
                  <SelectValue placeholder="Elige un proyecto" />
                </SelectTrigger>
                <SelectContent>
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
            <div className="flex justify-end">
              <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
                {crear.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Crear tarea
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// --- Listado (panel derecho) -----------------------------------------------

function ListaTareas({
  tareas,
  proyectos,
  cargando,
  error,
  onReintentar,
  reintentando,
}: {
  tareas: Tarea[];
  proyectos: ProyectoTarea[];
  cargando: boolean;
  error: string | null;
  onReintentar: () => void;
  reintentando: boolean;
}) {
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

  if (tareas.length === 0) {
    return (
      <EstadoVacio
        icono={ListTodo}
        titulo="Sin pendientes"
        texto="Crea la primera tarea con el formulario de la izquierda."
      />
    );
  }

  return (
    <div className="space-y-4">
      <BarraEstatus tareas={tareas} />
      <div className="space-y-3">
        {tareas.map((t) => (
          <TarjetaTarea key={t.id} tarea={t} proyectos={proyectos} />
        ))}
      </div>
    </div>
  );
}

/** Barra de estatus compartida: recuento por estado del ciclo de vida. */
function BarraEstatus({ tareas }: { tareas: Tarea[] }) {
  const conteo = React.useMemo(() => {
    const base: Record<string, number> = { pendiente: 0, hecha: 0 };
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
        {tareas.length} {tareas.length === 1 ? "tarea" : "tareas"}
      </span>
      {ORDEN_ESTADOS.map((estado) => (
        <Badge key={estado} variant={ESTADO_VARIANTE[estado] ?? "secondary"} className="font-normal">
          {conteo[estado] ?? 0} {etiquetaEstado(estado).toLowerCase()}
        </Badge>
      ))}
    </div>
  );
}

function TarjetaTarea({ tarea, proyectos }: { tarea: Tarea; proyectos: ProyectoTarea[] }) {
  const queryClient = useQueryClient();

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });

  const cambiarEstado = useMutation({
    mutationFn: (estado: EstadoTareaUi) => api.actualizarTarea(tarea.id, { estado }),
    onSuccess: () => invalidar(),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarTarea(tarea.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? "Tarea borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const abrir = useMutation({
    mutationFn: () => api.abrirTarea(tarea.id),
    onSuccess: (res) => toast.success(res?.mensaje ?? "Abriendo en el asistente…"),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const proyecto = proyectos.find((p) => p.id === tarea.proyecto);
  const carpetaFalta = proyecto !== undefined && !proyecto.existe;
  const nombreProyecto = tarea.proyecto_nombre || proyecto?.nombre || tarea.proyecto;
  const hecha = tarea.estado === "hecha";
  const fecha = formatearFecha(tarea.fecha);

  return (
    <Card className={cn(hecha && "opacity-60")}>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("font-medium leading-snug", hecha && "line-through")}>
                {tarea.titulo}
              </span>
              <Badge variant="outline" className="font-normal">
                {nombreProyecto}
              </Badge>
              <Badge variant={ESTADO_VARIANTE[tarea.estado] ?? "secondary"} className="font-normal">
                {etiquetaEstado(tarea.estado)}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {fecha && <span>{fecha}</span>}
              <Autor nombre={tarea.autor_nombre} className="text-xs" />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Tooltip label={hecha ? "Marcar como pendiente" : "Marcar como hecha"}>
              <Button
                variant="ghost"
                size="icon"
                aria-label={hecha ? "Marcar como pendiente" : "Marcar como hecha"}
                onClick={() => cambiarEstado.mutate(estadoAlternado(tarea.estado))}
                disabled={cambiarEstado.isPending}
              >
                {cambiarEstado.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : hecha ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </Tooltip>
            <Tooltip
              label={carpetaFalta ? "La carpeta del proyecto no existe" : "Abrir en Claude Code"}
            >
              <Button
                variant="ghost"
                size="icon"
                aria-label="Abrir en Claude Code"
                onClick={() => abrir.mutate()}
                disabled={abrir.isPending || carpetaFalta}
              >
                {abrir.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ExternalLink className="h-4 w-4" />
                )}
              </Button>
            </Tooltip>
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
      </CardContent>
    </Card>
  );
}
