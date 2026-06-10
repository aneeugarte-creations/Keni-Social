/**
 * Página DEDICADA de un pipeline (estilo GitLab/Azure DevOps): cabecera + tira de etapas (vista
 * de flujo) + cada etapa expandida con su ENTRADA (prompt) y SALIDA (razonamiento + resultado).
 * Reemplaza al antiguo pop-up: hay sitio para ver bien las etapas y el in/out. Reusa los
 * componentes de la lista (`Pipelines`), que exporta la maquinaria de render.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { PipelineActividad, PipelineGeneracion, RespuestaPipelineDetalle } from "@/types";

import { ChipEstado, ETAPA_A_EVENTO, MetricasPipeline, PanelEtapa, TiraEtapas } from "./Pipelines";
import { tiempoRelativo } from "@/lib/fecha";
import { INTERVALO_DETALLE_MS } from "@/lib/refresco";

export default function PipelineDetalle() {
  const { id } = useParams<{ id: string }>();
  const q = useQuery({
    queryKey: ["pipelines", "detalle", id],
    queryFn: ({ signal }) => api.pipelineDetalle(id as string, signal),
    enabled: !!id,
    refetchInterval: INTERVALO_DETALLE_MS,
    placeholderData: (prev) => prev,
  });
  const datos = q.data as RespuestaPipelineDetalle | undefined;
  const run = datos?.pipeline;

  const eventosDe = (clave: string): PipelineActividad[] => {
    const cod = ETAPA_A_EVENTO[clave];
    return cod && datos ? datos.actividad.filter((e) => e.etapa === cod) : [];
  };
  const generacionDe = (clave: string): PipelineGeneracion | undefined => {
    const cod = ETAPA_A_EVENTO[clave];
    return cod ? datos?.generaciones_por_etapa?.[cod] : undefined;
  };
  const plantillaDe = (clave: string): string | undefined => {
    const cod = ETAPA_A_EVENTO[clave];
    return cod ? datos?.prompts_por_etapa?.[cod] : undefined;
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-2">
        <Link
          to="/datos/produccion"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Producción
        </Link>
        <Button variant="ghost" size="sm" className="gap-1" onClick={() => q.refetch()} disabled={q.isFetching}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Actualizar
        </Button>
      </div>

      {q.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-2/3" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : q.isError || !run ? (
        <BloqueError
          titulo="No se pudo cargar el pipeline"
          mensaje={q.error instanceof ApiError ? q.error.message : "Inténtalo de nuevo."}
          onReintentar={() => q.refetch()}
        />
      ) : (
        <>
          {/* Cabecera. */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded border px-2 py-0.5 text-xs">{run.marca_nombre || run.marca}</span>
              <ChipEstado estado={run.estado_global} />
              <span className="text-xs text-muted-foreground">{tiempoRelativo(run.creado)}</span>
              {/* Coste real de la run: tokens/coste/duración sumados de sus generaciones. */}
              <MetricasPipeline metricas={run.metricas} className="ml-auto" />
            </div>
            <h1 className="text-lg font-semibold leading-snug">{run.titulo}</h1>
          </div>

          {/* Tira de etapas (vista de flujo, estilo GitLab/Azure). */}
          <div className="overflow-x-auto rounded-lg border bg-muted/20 p-3">
            <TiraEtapas etapas={run.etapas} />
          </div>

          {/* Cada etapa expandida: entrada → salida. */}
          <div className="space-y-2">
            {run.etapas.map((e) => (
              <PanelEtapa
                key={e.clave}
                etapa={e}
                run={run}
                eventos={eventosDe(e.clave)}
                generacion={generacionDe(e.clave)}
                plantilla={plantillaDe(e.clave)}
                defaultOpen
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
