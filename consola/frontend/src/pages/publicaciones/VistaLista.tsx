import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CalendarClock, Loader2, Pencil, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";
import type { Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { BadgeEstado, EtiquetaRed } from "./insignias";
import { formatearFechaHora, metaEstado, siguienteEstado } from "./meta";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Una tarjeta de publicación con estado, fecha y acciones. */
function TarjetaPublicacion({
  publicacion,
  onEditar,
}: {
  publicacion: Publicacion;
  onEditar: (p: Publicacion) => void;
}) {
  const queryClient = useQueryClient();
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  const proximo = siguienteEstado(publicacion.estado);

  const avanzar = useMutation({
    mutationFn: () => {
      if (!proximo) throw new Error("Estado final");
      return api.actualizarPublicacion(publicacion.id, { estado: proximo });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      if (proximo) toast.success(`Estado cambiado a "${metaEstado(proximo).nombre}"`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarPublicacion(publicacion.id),
    onSuccess: (res) => {
      setConfirmarBorrado(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      toast.success(res?.mensaje ?? "Publicación borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{publicacion.titulo}</span>
            <BadgeEstado estado={publicacion.estado} />
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} />
            <span>· {publicacion.marca_nombre}</span>
            {publicacion.estado === "programado" && publicacion.fecha_programada && (
              <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-300">
                <CalendarClock className="h-3.5 w-3.5" />
                {formatearFechaHora(publicacion.fecha_programada)}
              </span>
            )}
          </div>
          {publicacion.contenido && (
            <p className="line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">
              {publicacion.contenido}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {proximo && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => avanzar.mutate()}
              disabled={avanzar.isPending}
              title={`Avanzar a "${metaEstado(proximo).nombre}"`}
            >
              {avanzar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              {metaEstado(proximo).nombre}
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            aria-label="Editar publicación"
            title="Editar"
            onClick={() => onEditar(publicacion)}
          >
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Borrar publicación"
            title="Borrar"
            className="text-muted-foreground hover:text-destructive"
            onClick={() => setConfirmarBorrado(true)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>

      <Dialog open={confirmarBorrado} onOpenChange={setConfirmarBorrado}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Borrar publicación</DialogTitle>
            <DialogDescription>
              ¿Seguro que quieres borrar “{publicacion.titulo}”? Esta acción no se puede deshacer.
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
            <Button variant="destructive" onClick={() => borrar.mutate()} disabled={borrar.isPending}>
              {borrar.isPending ? "Borrando…" : "Borrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/** Vista de lista: tarjetas de publicación. */
export function VistaLista({
  publicaciones,
  onEditar,
}: {
  publicaciones: Publicacion[];
  onEditar: (p: Publicacion) => void;
}) {
  return (
    <div className="space-y-3">
      {publicaciones.map((p) => (
        <TarjetaPublicacion key={p.id} publicacion={p} onEditar={onEditar} />
      ))}
    </div>
  );
}
