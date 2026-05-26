/**
 * Detalle de una publicación comercial: valor actual, objetivo, curvas temporales,
 * edición rápida (estado/objetivo) y acciones (refrescar, reporte, eliminar).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Download, ExternalLink, Loader2, RefreshCw, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { api, ApiError } from "@/lib/api";
import type {
  CuerpoActualizarComercial,
  EstadoComercial,
  MetricaComercial,
  OpcionesComercial,
  PublicacionComercial,
} from "@/types";

import { numeroCompacto, numeroCompleto, porcentaje } from "../metricas/formato";
import { CLAVE_COMERCIAL } from "./claves";
import { etiquetaMetrica, fechaDia, fechaHora, presentacionEstado } from "./formato";
import { GraficaSerie } from "./GraficaSerie";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function TarjetaKpi({ etiqueta, valor, titulo }: { etiqueta: string; valor: string; titulo?: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-sm text-muted-foreground">{etiqueta}</p>
      <p className="truncate text-xl font-semibold tabular-nums" title={titulo ?? valor}>
        {valor}
      </p>
    </div>
  );
}

export function Detalle({
  publicacionId,
  opciones,
  onCerrar,
}: {
  publicacionId: string | null;
  opciones: OpcionesComercial;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: [...CLAVE_COMERCIAL, "detalle", publicacionId],
    queryFn: ({ signal }) => api.comercial(publicacionId as string, signal),
    enabled: publicacionId !== null,
  });
  const pub = query.data?.publicacion ?? null;

  return (
    <Dialog open={publicacionId !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[92vh] max-w-3xl overflow-y-auto">
        {query.isPending ? (
          <EsqueletoDetalle />
        ) : query.isError || pub === null ? (
          <BloqueError
            titulo="No se pudo cargar la publicación"
            mensaje={query.error instanceof Error ? query.error.message : undefined}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        ) : (
          <Contenido
            pub={pub}
            opciones={opciones}
            onCambio={() => {
              void queryClient.invalidateQueries({ queryKey: CLAVE_COMERCIAL });
            }}
            onEliminado={onCerrar}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function EsqueletoDetalle() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-7 w-2/3" />
      <div className="grid grid-cols-3 gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-44 w-full rounded-lg" />
    </div>
  );
}

function Contenido({
  pub,
  opciones,
  onCambio,
  onEliminado,
}: {
  pub: PublicacionComercial;
  opciones: OpcionesComercial;
  onCambio: () => void;
  onEliminado: () => void;
}) {
  const queryClient = useQueryClient();
  const [estado, setEstado] = React.useState<EstadoComercial>(pub.estado);
  const [metrica, setMetrica] = React.useState<MetricaComercial>(pub.metrica_objetivo);
  const [objetivo, setObjetivo] = React.useState(String(pub.objetivo || ""));

  // Sincronizamos el formulario cuando llega otra pieza o se refresca.
  React.useEffect(() => {
    setEstado(pub.estado);
    setMetrica(pub.metrica_objetivo);
    setObjetivo(String(pub.objetivo || ""));
  }, [pub.id, pub.estado, pub.metrica_objetivo, pub.objetivo]);

  const invalidarTodo = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_COMERCIAL });
    onCambio();
  };

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoActualizarComercial = {
        estado,
        metrica_objetivo: metrica,
        objetivo: objetivo ? Number(objetivo) : 0,
      };
      return api.actualizarComercial(pub.id, cuerpo);
    },
    onSuccess: () => {
      invalidarTodo();
      toast.success("Cambios guardados");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const refrescar = useMutation({
    mutationFn: () => api.refrescarComercial(pub.id),
    onSuccess: () => {
      invalidarTodo();
      toast.success("Datos actualizados");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const eliminar = useMutation({
    mutationFn: () => api.eliminarComercial(pub.id),
    onSuccess: () => {
      invalidarTodo();
      toast.success("Publicación retirada del seguimiento");
      onEliminado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const estadoBadge = presentacionEstado(pub.estado);
  const progreso = Math.min(pub.progreso_pct, 100);
  const titulo = pub.titulo || "Publicación comercial";

  return (
    <>
      <DialogHeader>
        <DialogTitle className="pr-6">{titulo}</DialogTitle>
        <DialogDescription className="flex flex-wrap items-center gap-2">
          <Badge variant={estadoBadge.variante}>{estadoBadge.texto}</Badge>
          {pub.red_nombre && <Badge variant="outline">{pub.red_nombre}</Badge>}
          {pub.marca_nombre && <span className="text-muted-foreground">· {pub.marca_nombre}</span>}
          {pub.cliente && <span className="text-muted-foreground">· {pub.cliente}</span>}
          {pub.campania && <span className="text-muted-foreground">· {pub.campania}</span>}
        </DialogDescription>
        <a
          href={pub.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex w-fit items-center gap-1 text-sm text-primary hover:underline"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Ver publicación
        </a>
      </DialogHeader>

      <div className="space-y-5">
        {/* Valor actual */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <TarjetaKpi
            etiqueta="Alcance"
            valor={numeroCompacto(pub.actual.alcance)}
            titulo={numeroCompleto(pub.actual.alcance)}
          />
          <TarjetaKpi
            etiqueta="Interacciones"
            valor={numeroCompacto(pub.actual.interacciones)}
            titulo={numeroCompleto(pub.actual.interacciones)}
          />
          <TarjetaKpi etiqueta="Engagement" valor={porcentaje(pub.actual.engagement_pct)} />
        </div>
        <p className="text-xs text-muted-foreground">
          Publicado el {fechaDia(pub.publicado)} · última lectura {fechaHora(pub.actual.ts)}
        </p>

        {/* Objetivo */}
        {pub.objetivo > 0 ? (
          <div className="space-y-2 rounded-lg border border-border p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                Objetivo · {etiquetaMetrica(pub.metrica_objetivo)}
              </span>
              <span className="font-medium tabular-nums">
                {numeroCompleto(pub.objetivo)} ({pub.progreso_pct} %)
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded bg-muted">
              <div
                className={pub.alcanzado ? "h-2 rounded bg-emerald-500" : "h-2 rounded bg-primary"}
                style={{ width: `${progreso}%` }}
              />
            </div>
            {pub.alcanzado && (
              <p className="flex items-center gap-1.5 text-sm text-emerald-700 dark:text-emerald-300">
                <Bell className="h-4 w-4" />
                Objetivo alcanzado{pub.aviso_en ? ` el ${fechaHora(pub.aviso_en)}` : ""}.
              </p>
            )}
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground">
            Sin objetivo definido. Fija un KPI abajo para que te avise al alcanzarlo.
          </p>
        )}

        {/* Curvas */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <GraficaSerie serie={pub.serie ?? []} metrica="alcance" titulo="Alcance" color="blue" />
          <GraficaSerie
            serie={pub.serie ?? []}
            metrica="interacciones"
            titulo="Interacciones"
            color="emerald"
          />
        </div>

        {/* Edición rápida */}
        <div className="grid grid-cols-1 gap-4 rounded-lg border border-border p-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="det-estado">Estado</Label>
            <Select value={estado} onValueChange={(v) => setEstado(v as EstadoComercial)}>
              <SelectTrigger id="det-estado">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {opciones.estados.map((e) => (
                  <SelectItem key={e.id} value={e.id}>
                    {e.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="det-metrica">Métrica</Label>
            <Select value={metrica} onValueChange={(v) => setMetrica(v as MetricaComercial)}>
              <SelectTrigger id="det-metrica">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {opciones.metricas.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="det-objetivo">Objetivo</Label>
            <Input
              id="det-objetivo"
              type="number"
              min={0}
              value={objetivo}
              onChange={(e) => setObjetivo(e.target.value)}
            />
          </div>
          <div className="sm:col-span-3">
            <Button size="sm" onClick={() => guardar.mutate()} disabled={guardar.isPending}>
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar cambios
            </Button>
          </div>
        </div>

        {/* Acciones */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refrescar.mutate()}
              disabled={refrescar.isPending}
            >
              <RefreshCw className={refrescar.isPending ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              Refrescar ahora
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => api.descargarReporteComercial({ publicacion: pub.id })}
            >
              <Download className="h-4 w-4" />
              Descargar reporte
            </Button>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="text-red-600 hover:text-red-700 dark:text-red-400"
            onClick={() => eliminar.mutate()}
            disabled={eliminar.isPending}
          >
            {eliminar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Quitar del seguimiento
          </Button>
        </div>
      </div>
    </>
  );
}
