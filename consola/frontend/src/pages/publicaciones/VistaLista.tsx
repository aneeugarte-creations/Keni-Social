import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BarChart3,
  CalendarClock,
  CalendarPlus,
  Copy,
  ImageIcon,
  Loader2,
  Pencil,
  RefreshCw,
  Send,
  Sprout,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { marcaMetricasDesdeCanonica } from "@/components/comunes/selectores";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, ApiError, urlMedia } from "@/lib/api";
import { cn } from "@/lib/utils";
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
  onDuplicar,
  onGestionarFranjas,
}: {
  publicacion: Publicacion;
  onEditar: (p: Publicacion) => void;
  onDuplicar: (p: Publicacion) => void;
  onGestionarFranjas: () => void;
}) {
  const queryClient = useQueryClient();
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  const proximo = siguienteEstado(publicacion.estado);
  const imagen = urlMedia(publicacion.imagen_url || publicacion.imagen);

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

  const encolar = useMutation({
    mutationFn: () => api.encolarPublicacion(publicacion.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const fecha = res?.publicacion?.fecha_programada;
      toast.success(
        fecha
          ? `Encolada para ${formatearFechaHora(fecha)}`
          : "Publicación añadida a la cola",
      );
    },
    onError: (e) => {
      // 400 = sin franjas: avisamos y ofrecemos abrir la gestión de franjas.
      if (e instanceof ApiError && e.status === 400) {
        toast.error(e.message, {
          action: { label: "Gestionar franjas", onClick: onGestionarFranjas },
        });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const reciclar = useMutation({
    mutationFn: () => api.reciclarPublicacion(publicacion.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const fecha = res?.publicacion?.fecha_programada;
      toast.success(
        res?.encolado
          ? `Reciclada y encolada${fecha ? ` para ${formatearFechaHora(fecha)}` : ""}`
          : "Reciclada como nuevo borrador",
      );
    },
    onError: (e) => {
      // 400 = sin franjas para encolar: avisamos y ofrecemos abrir las franjas.
      if (e instanceof ApiError && e.status === 400) {
        toast.error(e.message, {
          action: { label: "Gestionar franjas", onClick: onGestionarFranjas },
        });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const alternarEvergreen = useMutation({
    mutationFn: () =>
      api.actualizarPublicacion(publicacion.id, { evergreen: !publicacion.evergreen }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      toast.success(
        publicacion.evergreen ? "Ya no es perenne" : "Marcada como perenne",
      );
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
        <div className="flex min-w-0 flex-1 gap-3">
          {imagen && (
            <img
              src={imagen}
              alt=""
              className="h-16 w-16 shrink-0 rounded-md border border-border object-cover"
            />
          )}
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{publicacion.titulo}</span>
              <BadgeEstado estado={publicacion.estado} />
              {publicacion.id_post_metricool && (
                <Badge
                  variant="outline"
                  className="gap-1 border-sky-500/40 font-normal text-sky-700 dark:text-sky-300"
                  title={`Programada en Metricool · id ${publicacion.id_post_metricool}`}
                >
                  <Send className="h-3 w-3" />
                  Metricool
                </Badge>
              )}
              {publicacion.evergreen && (
                <Badge
                  variant="outline"
                  className="gap-1 border-emerald-500/40 font-normal text-emerald-700 dark:text-emerald-300"
                >
                  <Sprout className="h-3 w-3" />
                  Perenne
                </Badge>
              )}
              {imagen && (
                <ImageIcon
                  className="h-3.5 w-3.5 text-muted-foreground"
                  aria-label="Con imagen"
                />
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} />
              <span>· {publicacion.marca_nombre}</span>
              <Autor nombre={publicacion.autor_nombre} />
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
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-1">
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
          <Tooltip label="Añadir a la cola">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Añadir a la cola"
              onClick={() => encolar.mutate()}
              disabled={encolar.isPending}
            >
              {encolar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CalendarPlus className="h-4 w-4" />
              )}
            </Button>
          </Tooltip>
          {publicacion.estado === "publicado" && (
            <Tooltip label="Ver métricas de esta marca">
              <Button asChild variant="ghost" size="icon" aria-label="Ver métricas">
                <Link
                  to="/analiticas/metricas"
                  state={{ marca: marcaMetricasDesdeCanonica(publicacion.marca) }}
                >
                  <BarChart3 className="h-4 w-4" />
                </Link>
              </Button>
            </Tooltip>
          )}
          {(publicacion.estado === "publicado" || publicacion.evergreen) && (
            <Tooltip label="Reciclar (volver a publicar)">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Reciclar publicación"
                onClick={() => reciclar.mutate()}
                disabled={reciclar.isPending}
              >
                {reciclar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
              </Button>
            </Tooltip>
          )}
          <Tooltip label={publicacion.evergreen ? "Quitar de perennes" : "Marcar como perenne"}>
            <Button
              variant="ghost"
              size="icon"
              aria-label={publicacion.evergreen ? "Quitar perenne" : "Marcar perenne"}
              className={cn(
                publicacion.evergreen
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-muted-foreground",
              )}
              onClick={() => alternarEvergreen.mutate()}
              disabled={alternarEvergreen.isPending}
            >
              {alternarEvergreen.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sprout className="h-4 w-4" />
              )}
            </Button>
          </Tooltip>
          <Tooltip label="Duplicar">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Duplicar publicación"
              onClick={() => onDuplicar(publicacion)}
            >
              <Copy className="h-4 w-4" />
            </Button>
          </Tooltip>
          <Tooltip label="Editar">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Editar publicación"
              onClick={() => onEditar(publicacion)}
            >
              <Pencil className="h-4 w-4" />
            </Button>
          </Tooltip>
          <Tooltip label="Borrar">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Borrar publicación"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => setConfirmarBorrado(true)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </Tooltip>
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
  onDuplicar,
  onGestionarFranjas,
}: {
  publicaciones: Publicacion[];
  onEditar: (p: Publicacion) => void;
  onDuplicar: (p: Publicacion) => void;
  onGestionarFranjas: () => void;
}) {
  return (
    <div className="space-y-3">
      {publicaciones.map((p) => (
        <TarjetaPublicacion
          key={p.id}
          publicacion={p}
          onEditar={onEditar}
          onDuplicar={onDuplicar}
          onGestionarFranjas={onGestionarFranjas}
        />
      ))}
    </div>
  );
}
