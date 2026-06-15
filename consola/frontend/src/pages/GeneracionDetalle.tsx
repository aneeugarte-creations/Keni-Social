/**
 * Página DEDICADA de un trabajo SUELTO de IA (una generación fuera del pipeline: copy
 * manual, imagen, investigación, importación…): el MISMO patrón entrada/salida que una
 * etapa del pipeline (prompt | razonamiento + resultado), con sus métricas (tokens,
 * coste, duración) y estado en vivo (la consulta sondea mientras corre; cancelable).
 * Es el detalle al que lleva la tarjeta de un item `clase="actividad"` de Producción.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, RotateCcw, Square } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { ChipEstado } from "@/components/comunes/ChipEstado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { INTERVALO_DETALLE_MS } from "@/lib/refresco";

import { MetricasPipeline, PanelEtapa } from "./Pipelines";
import type { Pipeline, PipelineEtapa } from "@/types";

/** Estado de generación -> estado de etapa/chip (el mismo mapeo que hace el backend). */
function estadoEtapa(estado: string): string {
  if (estado === "completado") return "ok";
  if (estado === "error") return "fallo";
  if (estado === "ejecutando") return "en_curso";
  return "pendiente";
}

export default function GeneracionDetalle() {
  const { id } = useParams<{ id: string }>();
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const queryClient = useQueryClient();
  const q = useQuery({
    queryKey: ["generaciones", "detalle", id],
    queryFn: ({ signal }) => api.generacion(id as string, signal),
    enabled: !!id,
    refetchInterval: INTERVALO_DETALLE_MS,
    placeholderData: (prev) => prev,
  });
  const gen = q.data?.generacion;
  const cancelar = useMutation({
    mutationFn: () => api.cancelarGeneracion(id as string),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["generaciones", "detalle", id] }),
  });
  // Reintentar (admin): devuelve el job del trabajo FALLIDO a `pendiente` y reabre el
  // registro para que un worker lo vuelva a correr (`POST /api/actividad/cola/reencolar`,
  // acepta `{gen_id}`). 404 legible si la cola ya no conserva el job (registros podados).
  const reencolar = useMutation({
    mutationFn: () => api.colaReencolar(id as string),
    onSuccess: () => {
      toast.success("Trabajo reencolado: un worker lo volverá a ejecutar.");
      void queryClient.invalidateQueries({ queryKey: ["generaciones", "detalle", id] });
      void queryClient.invalidateQueries({ queryKey: ["actividad", "cola"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const estado = estadoEtapa(gen?.estado ?? "");
  // El trabajo entero se presenta como UNA etapa (la misma pieza que usa el detalle del
  // pipeline), con el nombre legible de su tipo: mismo panel, mismo bloque IA in/out.
  const etapa: PipelineEtapa | null = gen
    ? {
        clave: "trabajo",
        nombre: etiquetaTipoGeneracion(gen.tipo),
        estado,
        detalle: gen.error || "",
        ts: gen.fecha_inicio,
        es_ia: true,
      }
    : null;
  // PanelEtapa pide la run por su contenido extra (piezas/cluster); un trabajo suelto no
  // tiene nada de eso: forma mínima compatible.
  const pseudoRun: Pipeline | null = gen
    ? {
        clase: "actividad",
        id: gen.id,
        titulo: gen.etiqueta,
        marca: gen.marca,
        marca_nombre: gen.marca,
        creado: gen.fecha_inicio,
        actualizado: gen.fecha_fin || gen.fecha_inicio,
        estado_global: estado as Pipeline["estado_global"],
        etapa_actual: "",
        etapas: etapa ? [etapa] : [],
        qa_fuente: null,
        cluster: null,
        piezas: [],
      }
    : null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-2">
        <Link
          to="/maquina/actividad"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Actividad
        </Link>
        <div className="flex items-center gap-1">
          {esAdmin && gen?.estado === "error" && (
            <Button
              variant="ghost"
              size="sm"
              className="gap-1"
              onClick={() => reencolar.mutate()}
              disabled={reencolar.isPending}
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              {reencolar.isPending ? "Reencolando…" : "Reintentar"}
            </Button>
          )}
          {gen?.estado === "ejecutando" && (
            <Button
              variant="ghost"
              size="sm"
              className="gap-1 text-destructive"
              onClick={() => cancelar.mutate()}
              disabled={cancelar.isPending}
            >
              <Square className="h-4 w-4" aria-hidden="true" />
              {cancelar.isPending ? "Cancelando…" : "Cancelar"}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="gap-1"
            onClick={() => q.refetch()}
            disabled={q.isFetching}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Actualizar
          </Button>
        </div>
      </div>

      {q.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-2/3" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : q.isError || !gen || !pseudoRun || !etapa ? (
        <BloqueError
          titulo="No se pudo cargar el trabajo"
          mensaje={
            q.error instanceof ApiError && q.error.status === 404
              ? "Esa generación ya no está disponible (los registros viejos se podan)."
              : q.error instanceof ApiError
                ? q.error.message
                : "Inténtalo de nuevo."
          }
          onReintentar={() => q.refetch()}
        />
      ) : (
        <>
          {/* Cabecera: qué trabajo es, de qué marca, cómo va y cuánto costó. */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded border px-2 py-0.5 text-xs">{gen.marca || "—"}</span>
              <Badge variant="secondary" className="text-[10px]">
                {etiquetaTipoGeneracion(gen.tipo)}
              </Badge>
              <ChipEstado estado={estado} />
              <span className="text-xs text-muted-foreground">{tiempoRelativo(gen.fecha_inicio)}</span>
              <MetricasPipeline
                className="ml-auto"
                metricas={
                  gen.metricas
                    ? {
                        items: 1,
                        tokens:
                          (gen.metricas.tokens_in ?? 0) + (gen.metricas.tokens_out ?? 0) || null,
                        coste_usd: gen.metricas.total_cost_usd ?? null,
                        duration_ms: gen.metricas.duration_ms ?? null,
                      }
                    : undefined
                }
              />
            </div>
            <h1 className="text-lg font-semibold leading-snug">
              {gen.etiqueta || etiquetaTipoGeneracion(gen.tipo)}
            </h1>
          </div>

          {/* El trabajo, expandido: entrada (prompt) → salida (razonamiento + resultado). */}
          <PanelEtapa
            etapa={etapa}
            run={pseudoRun}
            eventos={[]}
            generacion={{
              id: gen.id,
              estado: gen.estado,
              fase: gen.fase,
              prompt: gen.prompt || "",
              salida: gen.salida || "",
              metricas: gen.metricas,
            }}
            defaultOpen
          />
        </>
      )}
    </div>
  );
}
