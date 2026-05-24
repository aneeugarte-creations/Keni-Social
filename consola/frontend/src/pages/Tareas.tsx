import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  FolderOpen,
  ListTodo,
  Plus,
  RefreshCw,
  Terminal,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ProyectoTarea, RespuestaTareas, Tarea } from "@/types";

const CLAVE_TAREAS = ["tareas"] as const;

/** Estado "hecha" tal y como lo valida el backend (`db.ESTADOS_TAREA`). */
const ESTADO_HECHA = "hecha";
const ESTADO_PENDIENTE = "pendiente";

/** Devuelve el mensaje legible (es-MX) de un error, con fallback. */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** ¿Está la tarea marcada como hecha? */
function estaHecha(tarea: Tarea): boolean {
  return tarea.estado === ESTADO_HECHA;
}

/** Formatea una fecha ISO en formato corto es-MX; tolera fechas inválidas. */
function formatearFecha(iso: string): string {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(fecha);
}

interface Grupo {
  /** Clave estable para React. */
  clave: string;
  nombre: string;
  /** true => proyecto fuera de la allowlist (tareas huérfanas). */
  huerfano: boolean;
  /** Proyecto resuelto desde la allowlist (para saber si `existe`). */
  proyecto?: ProyectoTarea;
  tareas: Tarea[];
}

/**
 * Agrupa las tareas por proyecto. Las tareas cuyo proyecto ya no está en la
 * allowlist (sin `proyecto_nombre`) caen en un grupo "Sin proyecto" al final.
 */
function agruparTareas(datos: RespuestaTareas): Grupo[] {
  const porId = new Map(datos.proyectos.map((p) => [p.id, p]));
  const mapa = new Map<string, Grupo>();
  const HUERFANO = "__sin_proyecto__";

  for (const tarea of datos.tareas) {
    const proyecto = porId.get(tarea.proyecto);
    const huerfano = proyecto === undefined;
    const clave = huerfano ? HUERFANO : tarea.proyecto;
    let grupo = mapa.get(clave);
    if (!grupo) {
      grupo = {
        clave,
        nombre: huerfano ? "Sin proyecto" : proyecto.nombre || tarea.proyecto_nombre || tarea.proyecto,
        huerfano,
        proyecto,
        tareas: [],
      };
      mapa.set(clave, grupo);
    }
    grupo.tareas.push(tarea);
  }

  const grupos = [...mapa.values()];
  // Orden: proyectos por nombre (es-MX), y el grupo huérfano siempre al final.
  grupos.sort((a, b) => {
    if (a.huerfano !== b.huerfano) return a.huerfano ? 1 : -1;
    return a.nombre.localeCompare(b.nombre, "es-MX");
  });
  return grupos;
}

/** Esqueleto de carga que imita la lista agrupada de tareas. */
function EsqueletoTareas() {
  return (
    <div className="space-y-6">
      {Array.from({ length: 2 }).map((_, g) => (
        <Card key={g}>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent className="divide-y divide-border p-0">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-3.5">
                <Skeleton className="mt-0.5 h-5 w-5 rounded" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-64" />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/**
 * Página de Tareas: gestión de tareas por proyecto. Cada tarea puede abrirse en
 * Claude Code en la carpeta de su proyecto, usando su `detalle` como prompt.
 *
 * Consume `GET /api/tareas` vía React Query y muta con `useMutation` invalidando
 * `["tareas"]` tras cada cambio. UI con modo claro/oscuro y texto es-MX.
 */
export default function Tareas() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_TAREAS,
    queryFn: ({ signal }) => api.tareas(signal),
  });

  const [crearAbierto, setCrearAbierto] = React.useState(false);

  const acciones = (
    <>
      <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
        <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
        Actualizar
      </Button>
      <Button onClick={() => setCrearAbierto(true)} disabled={isPending || isError}>
        <Plus className="h-4 w-4" />
        Crear tarea
      </Button>
    </>
  );

  const tieneTareas = !!data && data.tareas.length > 0;
  const grupos = data ? agruparTareas(data) : [];

  return (
    <>
      <PageHeader
        titulo="Tareas"
        descripcion="Pendientes por proyecto, listas para abrir en Claude Code."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoTareas />
      ) : isError ? (
        <Card className="border-destructive/40">
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">No se pudieron cargar las tareas</p>
              <p className="max-w-md text-sm text-muted-foreground">{mensajeError(error)}</p>
            </div>
            <Button onClick={() => void refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : !tieneTareas ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <ListTodo className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">Aún no hay tareas</p>
              <p className="max-w-md text-sm text-muted-foreground">
                Crea tu primera tarea y ábrela en Claude Code dentro de la carpeta de su proyecto.
              </p>
            </div>
            <Button onClick={() => setCrearAbierto(true)}>
              <Plus className="h-4 w-4" />
              Crear tarea
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {grupos.map((grupo) => (
            <GrupoProyecto key={grupo.clave} grupo={grupo} />
          ))}
        </div>
      )}

      <DialogoCrear
        abierto={crearAbierto}
        onAbierto={setCrearAbierto}
        proyectos={data?.proyectos ?? []}
      />
    </>
  );
}

/** Tarjeta de un proyecto con su lista de tareas. */
function GrupoProyecto({ grupo }: { grupo: Grupo }) {
  const hechas = grupo.tareas.filter(estaHecha).length;
  const carpetaPerdida = !grupo.huerfano && grupo.proyecto?.existe === false;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <FolderOpen className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            {grupo.nombre}
          </CardTitle>
          <Badge variant="secondary">
            {hechas}/{grupo.tareas.length} {grupo.tareas.length === 1 ? "hecha" : "hechas"}
          </Badge>
          {grupo.huerfano && (
            <Badge variant="aviso" className="gap-1">
              <TriangleAlert className="h-3 w-3" />
              Proyecto no configurado
            </Badge>
          )}
          {carpetaPerdida && (
            <Badge variant="aviso" className="gap-1">
              <TriangleAlert className="h-3 w-3" />
              Carpeta no encontrada
            </Badge>
          )}
        </div>
        {grupo.huerfano && (
          <p className="text-sm text-muted-foreground">
            Estas tareas apuntan a un proyecto que ya no está en la lista permitida. No se pueden
            abrir en Claude Code hasta volver a configurarlo.
          </p>
        )}
      </CardHeader>
      <CardContent className="p-0">
        <ul className="divide-y divide-border">
          {grupo.tareas.map((tarea) => (
            <FilaTarea key={tarea.id} tarea={tarea} bloqueada={grupo.huerfano} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

/** Una fila de tarea con checkbox de estado, detalle, fecha y acciones. */
function FilaTarea({ tarea, bloqueada }: { tarea: Tarea; bloqueada: boolean }) {
  const queryClient = useQueryClient();
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  const hecha = estaHecha(tarea);

  const alternar = useMutation({
    mutationFn: () =>
      api.actualizarTarea(tarea.id, { estado: hecha ? ESTADO_PENDIENTE : ESTADO_HECHA }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(hecha ? "Tarea marcada como pendiente." : "Tarea marcada como hecha.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarTarea(tarea.id),
    onSuccess: (res) => {
      setConfirmarBorrado(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(res?.mensaje ?? "Tarea borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const abrir = useMutation({
    mutationFn: () => api.abrirTarea(tarea.id),
    onSuccess: (res) => toast.success(res?.mensaje ?? "Abriendo en Claude Code…"),
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <li className="flex items-start gap-3 px-4 py-3.5">
      <button
        type="button"
        role="checkbox"
        aria-checked={hecha}
        aria-label={hecha ? "Marcar como pendiente" : "Marcar como hecha"}
        onClick={() => alternar.mutate()}
        disabled={alternar.isPending}
        className={cn(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50",
          hecha
            ? "border-emerald-500 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
            : "border-input hover:bg-accent",
        )}
      >
        {hecha && <CheckCircle2 className="h-4 w-4" />}
      </button>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "font-medium",
              hecha && "text-muted-foreground line-through",
            )}
          >
            {tarea.titulo}
          </span>
          <Badge variant={hecha ? "ok" : "secondary"}>{hecha ? "Hecha" : "Pendiente"}</Badge>
        </div>
        {tarea.detalle && (
          <p className="mt-0.5 whitespace-pre-wrap text-sm text-muted-foreground">
            {tarea.detalle}
          </p>
        )}
        <p className="mt-1 text-xs text-muted-foreground">{formatearFecha(tarea.fecha)}</p>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Abrir en Claude Code"
          title={
            bloqueada
              ? "El proyecto de esta tarea ya no está configurado"
              : "Abrir en Claude Code"
          }
          onClick={() => abrir.mutate()}
          disabled={bloqueada || abrir.isPending}
        >
          <Terminal className={cn("h-4 w-4", abrir.isPending && "animate-pulse")} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Borrar tarea"
          title="Borrar tarea"
          onClick={() => setConfirmarBorrado(true)}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      <Dialog open={confirmarBorrado} onOpenChange={setConfirmarBorrado}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Borrar tarea</DialogTitle>
            <DialogDescription>
              ¿Seguro que quieres borrar “{tarea.titulo}”? Esta acción no se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmarBorrado(false)}
              disabled={borrar.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => borrar.mutate()}
              disabled={borrar.isPending}
            >
              {borrar.isPending ? "Borrando…" : "Borrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  );
}

/** Diálogo con el formulario de creación de tareas. */
function DialogoCrear({
  abierto,
  onAbierto,
  proyectos,
}: {
  abierto: boolean;
  onAbierto: (v: boolean) => void;
  proyectos: ProyectoTarea[];
}) {
  const queryClient = useQueryClient();
  const [proyecto, setProyecto] = React.useState("");
  const [titulo, setTitulo] = React.useState("");
  const [detalle, setDetalle] = React.useState("");

  const proyectoSel = proyectos.find((p) => p.id === proyecto);

  const reiniciar = React.useCallback(() => {
    setProyecto("");
    setTitulo("");
    setDetalle("");
  }, []);

  const crear = useMutation({
    mutationFn: () =>
      api.crearTarea({ proyecto, titulo: titulo.trim(), detalle: detalle.trim() }),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(`Tarea creada: ${res.tarea.titulo}`);
      reiniciar();
      onAbierto(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const sinProyectos = proyectos.length === 0;
  const puedeEnviar = !!proyecto && titulo.trim().length > 0 && !crear.isPending;

  function manejarAbierto(v: boolean) {
    if (!v) reiniciar();
    onAbierto(v);
  }

  function manejarEnvio(e: React.FormEvent) {
    e.preventDefault();
    if (puedeEnviar) crear.mutate();
  }

  return (
    <Dialog open={abierto} onOpenChange={manejarAbierto}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Crear tarea</DialogTitle>
          <DialogDescription>
            El detalle es el prompt con el que se abrirá Claude Code en la carpeta del proyecto.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={manejarEnvio} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="tarea-proyecto">Proyecto</Label>
            <Select value={proyecto} onValueChange={setProyecto} disabled={sinProyectos}>
              <SelectTrigger id="tarea-proyecto">
                <SelectValue
                  placeholder={sinProyectos ? "No hay proyectos configurados" : "Elige un proyecto"}
                />
              </SelectTrigger>
              <SelectContent>
                {proyectos.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.nombre}
                    {!p.existe ? " (carpeta no encontrada)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {sinProyectos && (
              <p className="text-xs text-muted-foreground">
                Configura un proyecto en la consola para poder crear tareas.
              </p>
            )}
            {proyectoSel && !proyectoSel.existe && (
              <p className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                <TriangleAlert className="h-3 w-3" />
                La carpeta de este proyecto no existe; no podrás abrir la tarea hasta restaurarla.
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="tarea-titulo">Título</Label>
            <Input
              id="tarea-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Ej. Revisar el copy de la campaña"
              maxLength={200}
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="tarea-detalle">
              Detalle <span className="text-muted-foreground">(opcional)</span>
            </Label>
            <Textarea
              id="tarea-detalle"
              value={detalle}
              onChange={(e) => setDetalle(e.target.value)}
              placeholder="Prompt inicial para Claude Code…"
              rows={4}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => manejarAbierto(false)}
              disabled={crear.isPending}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={!puedeEnviar}>
              {crear.isPending ? "Creando…" : "Crear tarea"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
