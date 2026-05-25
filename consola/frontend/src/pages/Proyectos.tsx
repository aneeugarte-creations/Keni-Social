import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ExternalLink,
  FileText,
  FolderGit2,
  Plus,
  RefreshCw,
  Save,
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
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Proyecto } from "@/types";

const CLAVE_PROYECTOS = ["proyectos"];

/**
 * Limpia emojis de estado (❌ ✅ ⚠️ …) y espacios sobrantes del texto que llega
 * del backend, para mostrarlo de forma sobria en la interfaz.
 */
function limpiarTexto(texto: string): string {
  return texto
    .replace(/[✅❌⚠️✔✖✗✘]/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return limpiarTexto(error.message);
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Esqueleto de carga que imita la lista de proyectos. */
function EsqueletoProyectos() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3 w-72" />
          </CardHeader>
          <CardContent className="flex gap-2 pt-0">
            <Skeleton className="h-8 w-32" />
            <Skeleton className="h-8 w-40" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/** Diálogo para editar el CLAUDE.md de un proyecto. */
function DialogoClaudeMd({
  proyecto,
  abierto,
  onAbiertoChange,
}: {
  proyecto: Proyecto;
  abierto: boolean;
  onAbiertoChange: (abierto: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [contenido, setContenido] = React.useState(proyecto.claude_md ?? "");

  // Al reabrir el diálogo, repoblamos con el valor más reciente del proyecto.
  React.useEffect(() => {
    if (abierto) setContenido(proyecto.claude_md ?? "");
  }, [abierto, proyecto.claude_md]);

  const guardar = useMutation({
    mutationFn: () => api.guardarClaudeMd(proyecto.id, { contenido }),
    onSuccess: (res) => {
      toast.success(limpiarTexto(res.mensaje) || "CLAUDE.md guardado.");
      void queryClient.invalidateQueries({ queryKey: CLAVE_PROYECTOS });
      onAbiertoChange(false);
    },
    onError: (error) => toast.error(mensajeError(error)),
  });

  return (
    <Dialog open={abierto} onOpenChange={onAbiertoChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Editar CLAUDE.md</DialogTitle>
          <DialogDescription>
            Instrucciones de contexto para «{proyecto.nombre}». Se guardan en el archivo
            CLAUDE.md del proyecto.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={contenido}
          onChange={(e) => setContenido(e.target.value)}
          placeholder="# Contexto del proyecto&#10;&#10;Escribe aquí las instrucciones para Claude Code…"
          className="min-h-[280px] font-mono text-xs"
          disabled={guardar.isPending}
        />
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onAbiertoChange(false)}
            disabled={guardar.isPending}
          >
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={guardar.isPending}>
            <Save className={cn("h-4 w-4", guardar.isPending && "animate-pulse")} />
            {guardar.isPending ? "Guardando…" : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Tarjeta de un proyecto: nombre, ruta, badges de estado y acciones. */
function TarjetaProyecto({ proyecto }: { proyecto: Proyecto }) {
  const [editando, setEditando] = React.useState(false);

  const abrir = useMutation({
    mutationFn: () => api.abrirProyecto(proyecto.id),
    onSuccess: (res) =>
      toast.success(limpiarTexto(res.mensaje) || "Proyecto abierto en Claude Code."),
    onError: (error) => toast.error(mensajeError(error)),
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <FolderGit2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="truncate">{proyecto.nombre}</span>
            </CardTitle>
            <p className="truncate font-mono text-xs text-muted-foreground" title={proyecto.ruta}>
              {proyecto.ruta}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
            <Badge variant="secondary" className="gap-1.5">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  proyecto.existe ? "bg-emerald-500" : "bg-red-500",
                )}
                aria-hidden="true"
              />
              {proyecto.existe ? "Existe" : "No existe"}
            </Badge>
            {proyecto.tiene_claude_md ? (
              <Badge variant="secondary">Con CLAUDE.md</Badge>
            ) : (
              <Badge variant="secondary" className="gap-1.5">
                <span className="h-2 w-2 rounded-full bg-amber-500" aria-hidden="true" />
                Sin CLAUDE.md
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2 pt-0">
        <Button variant="outline" size="sm" onClick={() => setEditando(true)}>
          <FileText className="h-4 w-4" />
          Editar CLAUDE.md
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => abrir.mutate()}
          disabled={abrir.isPending || !proyecto.existe}
        >
          <ExternalLink className={cn("h-4 w-4", abrir.isPending && "animate-pulse")} />
          {abrir.isPending ? "Abriendo…" : "Abrir en Claude Code"}
        </Button>
      </CardContent>

      <DialogoClaudeMd proyecto={proyecto} abierto={editando} onAbiertoChange={setEditando} />
    </Card>
  );
}

/** Diálogo para añadir un proyecto nuevo (nombre + ruta). */
function DialogoNuevoProyecto({
  abierto,
  onAbiertoChange,
}: {
  abierto: boolean;
  onAbiertoChange: (abierto: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [nombre, setNombre] = React.useState("");
  const [ruta, setRuta] = React.useState("");

  React.useEffect(() => {
    if (abierto) {
      setNombre("");
      setRuta("");
    }
  }, [abierto]);

  const crear = useMutation({
    mutationFn: () => api.crearProyecto({ nombre: nombre.trim(), ruta: ruta.trim() }),
    onSuccess: (res) => {
      toast.success(limpiarTexto(res.mensaje) || "Proyecto añadido.");
      void queryClient.invalidateQueries({ queryKey: CLAVE_PROYECTOS });
      onAbiertoChange(false);
    },
    onError: (error) => toast.error(mensajeError(error)),
  });

  const valido = nombre.trim() !== "" && ruta.trim() !== "";

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (valido) crear.mutate();
  }

  return (
    <Dialog open={abierto} onOpenChange={onAbiertoChange}>
      <DialogContent>
        <form onSubmit={enviar}>
          <DialogHeader>
            <DialogTitle>Añadir proyecto</DialogTitle>
            <DialogDescription>
              Conecta una carpeta existente de tu equipo para verla aquí y abrirla en Claude
              Code.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="nuevo-proyecto-nombre">Nombre</Label>
              <Input
                id="nuevo-proyecto-nombre"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Mi proyecto"
                disabled={crear.isPending}
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nuevo-proyecto-ruta">Ruta</Label>
              <Input
                id="nuevo-proyecto-ruta"
                value={ruta}
                onChange={(e) => setRuta(e.target.value)}
                placeholder="/Users/tu-usuario/proyectos/mi-proyecto"
                className="font-mono text-xs"
                disabled={crear.isPending}
              />
              <p className="text-xs text-muted-foreground">
                Ruta absoluta de la carpeta en este equipo.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onAbiertoChange(false)}
              disabled={crear.isPending}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={!valido || crear.isPending}>
              <Plus className={cn("h-4 w-4", crear.isPending && "animate-pulse")} />
              {crear.isPending ? "Añadiendo…" : "Añadir"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Página de proyectos: lista las carpetas conectadas, permite editar su
 * CLAUDE.md, abrirlas en Claude Code y añadir nuevas.
 */
export default function Proyectos() {
  const [creando, setCreando] = React.useState(false);
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_PROYECTOS,
    queryFn: ({ signal }) => api.proyectos(signal),
  });

  const acciones = (
    <>
      <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
        <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
        Actualizar
      </Button>
      <Button onClick={() => setCreando(true)}>
        <Plus className="h-4 w-4" />
        Añadir proyecto
      </Button>
    </>
  );

  return (
    <>
      <PageHeader
        titulo="Proyectos"
        descripcion="Carpetas conectadas a la consola. Edita su CLAUDE.md o ábrelas en Claude Code."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoProyectos />
      ) : isError ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <AlertCircle className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
            <div className="space-y-1">
              <p className="text-sm font-medium">No se pudieron cargar los proyectos</p>
              <p className="max-w-md text-sm text-muted-foreground">{mensajeError(error)}</p>
            </div>
            <Button onClick={() => void refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : data.proyectos.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <FolderGit2 className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
            <div className="space-y-1">
              <p className="text-sm font-medium">Aún no hay proyectos</p>
              <p className="max-w-md text-sm text-muted-foreground">
                Añade una carpeta para conectarla con la consola y empezar a trabajar con Claude
                Code.
              </p>
            </div>
            <Button onClick={() => setCreando(true)}>
              <Plus className="h-4 w-4" />
              Añadir proyecto
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {data.proyectos.map((p) => (
            <TarjetaProyecto key={p.id} proyecto={p} />
          ))}
        </div>
      )}

      <DialogoNuevoProyecto abierto={creando} onAbiertoChange={setCreando} />
    </>
  );
}
