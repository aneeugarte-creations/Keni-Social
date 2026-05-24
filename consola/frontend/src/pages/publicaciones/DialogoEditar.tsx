import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { CuerpoActualizarPublicacion, EstadoOpcion, EstadoPublicacion, Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { EtiquetaRed } from "./insignias";
import { datetimeLocalAIso, isoADatetimeLocal, metaRed } from "./meta";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Diálogo de edición de una publicación: título, contenido, estado y fecha. */
export function DialogoEditar({
  publicacion,
  estados,
  onCerrar,
}: {
  publicacion: Publicacion | null;
  estados: EstadoOpcion[];
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  const [estado, setEstado] = React.useState<EstadoPublicacion>("borrador");
  const [fechaLocal, setFechaLocal] = React.useState("");

  // Cargamos los valores cada vez que se abre con una publicación nueva.
  React.useEffect(() => {
    if (!publicacion) return;
    setTitulo(publicacion.titulo);
    setContenido(publicacion.contenido);
    setEstado(publicacion.estado);
    setFechaLocal(isoADatetimeLocal(publicacion.fecha_programada));
  }, [publicacion]);

  const limite = publicacion ? metaRed(publicacion.red).limite : null;
  const excede = limite !== null && contenido.length > limite;
  const programado = estado === "programado";

  const guardar = useMutation({
    mutationFn: () => {
      if (!publicacion) throw new Error("Sin publicación");
      const cuerpo: CuerpoActualizarPublicacion = {
        titulo: titulo.trim(),
        contenido,
        estado,
        // Solo mandamos fecha si está programado; al salir de programado, la limpiamos.
        fecha_programada: programado ? datetimeLocalAIso(fechaLocal) : null,
      };
      return api.actualizarPublicacion(publicacion.id, cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      toast.success("Publicación actualizada");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const faltaFecha = programado && !fechaLocal;
  const puedeGuardar =
    !!publicacion && titulo.trim().length > 0 && contenido.trim().length > 0 && !faltaFecha && !guardar.isPending;

  return (
    <Dialog open={publicacion !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Editar publicación</DialogTitle>
          <DialogDescription className="flex items-center gap-2">
            {publicacion && (
              <>
                <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} />
                <span className="text-muted-foreground">· {publicacion.marca_nombre}</span>
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="editar-titulo">Título</Label>
            <Input
              id="editar-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              maxLength={200}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="editar-contenido">Contenido</Label>
              <span
                className={cn(
                  "text-xs tabular-nums",
                  excede ? "font-medium text-red-600 dark:text-red-400" : "text-muted-foreground",
                )}
              >
                {contenido.length.toLocaleString("es-MX")}
                {limite !== null && ` / ${limite.toLocaleString("es-MX")}`}
              </span>
            </div>
            <Textarea
              id="editar-contenido"
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              className="min-h-[10rem] font-mono text-sm"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="editar-estado">Estado</Label>
              <Select value={estado} onValueChange={(v) => setEstado(v as EstadoPublicacion)}>
                <SelectTrigger id="editar-estado">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {estados.map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {programado && (
              <div className="space-y-1.5">
                <Label htmlFor="editar-fecha">Fecha y hora programada</Label>
                <Input
                  id="editar-fecha"
                  type="datetime-local"
                  value={fechaLocal}
                  onChange={(e) => setFechaLocal(e.target.value)}
                />
                {faltaFecha && (
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    Elige una fecha para programar la publicación.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={guardar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar cambios
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
