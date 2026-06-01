import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BarChart3,
  CalendarClock,
  CalendarPlus,
  Copy,
  ImageIcon,
  Pencil,
  RefreshCw,
  Send,
  Sprout,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { marcaMetricasDesdeCanonica } from "@/components/comunes/selectores";
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
import { api, ApiError, urlMedia } from "@/lib/api";
import type { Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { BadgeEstado, EtiquetaRed } from "./insignias";
import { formatearFechaHora, metaEstado, siguienteEstado } from "./meta";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/**
 * Una tarjeta de publicación. Click izquierdo sobre la tarjeta = editar (acción
 * primaria); el resto de operaciones viven en el menú contextual (click derecho) y en
 * el kebab "⋮", sin hilera de botones-icono.
 */
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
  const navigate = useNavigate();
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

  const programarMetricool = useMutation({
    mutationFn: () => api.programarEnMetricool(publicacion.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const r = res.resultado;
      const redes = (r.redes ?? []).join(", ") || "—";
      if (r.dry_run) {
        toast.success(
          `Vista previa lista: se enviaría a Metricool (${redes}). No se publicó (modo dry-run).`,
        );
      } else {
        toast.success(`Publicado en Metricool (${redes})${r.id_post ? ` · id ${r.id_post}` : ""}`);
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
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

  // Acción primaria = editar. Las demás operaciones, condicionadas por estado, en el menú.
  const acciones: EntradaMenuContextual[] = [
    { etiqueta: "Editar", icono: Pencil, onClick: () => onEditar(publicacion) },
    ...(proximo
      ? [
          {
            etiqueta: `Avanzar a "${metaEstado(proximo).nombre}"`,
            icono: ArrowRight,
            onClick: () => avanzar.mutate(),
            deshabilitado: avanzar.isPending,
          },
        ]
      : []),
    { separador: true },
    {
      etiqueta: "Añadir a la cola",
      icono: CalendarPlus,
      onClick: () => encolar.mutate(),
      deshabilitado: encolar.isPending,
    },
    ...(publicacion.estado === "aprobado" || publicacion.estado === "programado"
      ? [
          {
            etiqueta: "Programar en Metricool",
            icono: Send,
            onClick: () => programarMetricool.mutate(),
            deshabilitado: programarMetricool.isPending,
          },
        ]
      : []),
    ...(publicacion.estado === "publicado" || publicacion.evergreen
      ? [
          {
            etiqueta: "Reciclar (volver a publicar)",
            icono: RefreshCw,
            onClick: () => reciclar.mutate(),
            deshabilitado: reciclar.isPending,
          },
        ]
      : []),
    ...(publicacion.estado === "publicado"
      ? [
          {
            etiqueta: "Ver métricas de la marca",
            icono: BarChart3,
            onClick: () =>
              navigate("/analiticas/metricas", {
                state: { marca: marcaMetricasDesdeCanonica(publicacion.marca) },
              }),
          },
        ]
      : []),
    {
      etiqueta: publicacion.evergreen ? "Quitar de perennes" : "Marcar como perenne",
      icono: Sprout,
      onClick: () => alternarEvergreen.mutate(),
      activo: publicacion.evergreen,
      deshabilitado: alternarEvergreen.isPending,
    },
    { etiqueta: "Duplicar", icono: Copy, onClick: () => onDuplicar(publicacion) },
    { separador: true },
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: () => setConfirmarBorrado(true),
      destructivo: true,
    },
  ];

  return (
    <>
      <FilaConAcciones
        como="div"
        onPrimaria={() => onEditar(publicacion)}
        acciones={acciones}
        etiquetaAcciones={`Acciones de "${publicacion.titulo}"`}
        kebab="hover"
        className="rounded-lg border border-border bg-card text-card-foreground shadow-sm transition-colors hover:border-foreground/20"
      >
        <div className="flex min-w-0 flex-1 gap-3 py-4 pl-4 pr-10">
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
      </FilaConAcciones>

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
    </>
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
