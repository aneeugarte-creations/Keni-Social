/**
 * Página DEDICADA de un pipeline (estilo GitLab/Azure DevOps): cabecera + tira de etapas (vista
 * de flujo) + cada etapa expandida con su ENTRADA (prompt) y SALIDA (razonamiento + resultado).
 * Reemplaza al antiguo pop-up: hay sitio para ver bien las etapas y el in/out. Reusa los
 * componentes de la lista (`Pipelines`), que exporta la maquinaria de render.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { TituloPagina } from "@/components/layout/encabezado";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { PipelineActividad, PipelineGeneracion, RespuestaPipelineDetalle } from "@/types";

import { ChipEstado, ETAPA_A_EVENTO, MetricasPipeline, PanelEtapa, TiraEtapas } from "./Pipelines";
import { tiempoRelativo } from "@/lib/fecha";
import { INTERVALO_DETALLE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";

export default function PipelineDetalle() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ["pipelines", "detalle", id],
    queryFn: ({ signal }) => api.pipelineDetalle(id as string, signal),
    enabled: !!id,
    // Mientras una etapa IA está EJECUTANDO, sondeamos rápido para aflorar su `salida` en vivo
    // (el worker la persiste cada ~0.4 s); en reposo, el intervalo normal del detalle.
    refetchInterval: (query) => {
      const d = query.state.data as RespuestaPipelineDetalle | undefined;
      const corriendo = Object.values(d?.generaciones_por_etapa ?? {}).some(
        (g) => g?.estado === "ejecutando",
      );
      return corriendo ? INTERVALO_VIVO_MS : INTERVALO_DETALLE_MS;
    },
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

  // El título de la run y el «←» (volver a Actividad) viven en la BARRA SUPERIOR del shell.
  const titulo = run ? run.titulo : "Pipeline";

  return (
    <div className="space-y-5">
      {/* Cabecera (← Actividad + título) en la barra superior. El detalle se auto-refresca
          (INTERVALO_DETALLE_MS); no hay acción manual de recarga. */}
      <TituloPagina titulo={titulo} onAtras={() => navigate("/maquina/actividad")} />

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
          {/* Cabecera: marca, estado y coste (el título va en la barra superior). */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded border px-2 py-0.5 text-xs">{run.marca_nombre || run.marca}</span>
              <ChipEstado estado={run.estado_global} />
              <span className="text-xs text-muted-foreground">{tiempoRelativo(run.creado)}</span>
              {/* Coste real de la run: tokens/coste/duración sumados de sus generaciones. */}
              <MetricasPipeline metricas={run.metricas} className="ml-auto" />
            </div>
          </div>

          {/* Tira de etapas (vista de flujo, estilo GitLab/Azure). */}
          <div className="overflow-x-auto rounded-lg border bg-muted/20 p-3">
            <TiraEtapas etapas={run.etapas} />
          </div>

          {/* Cada etapa expandida: entrada → salida. Las etapas que NO corrieron («saltada») no
              se listan (ni su in/out vacío): solo se ve lo que de verdad pasó. */}
          <div className="space-y-2">
            {run.etapas.filter((e) => e.estado !== "saltada").map((e) => (
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
