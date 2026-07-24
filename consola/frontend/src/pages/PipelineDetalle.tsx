/**
 * Página DEDICADA de un pipeline (estilo GitLab/Azure DevOps): cabecera + tira de etapas (vista
 * de flujo) + LÍNEA DE TIEMPO unificada del post (toda la actividad real, incl. el Decisor, con
 * los reintentos colapsados) + cada etapa expandida con su ENTRADA (prompt) y SALIDA (razonamiento
 * + resultado). Reusa los componentes de la lista (`Pipelines`), que exporta la maquinaria de render.
 */
import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { ChipEstado } from "@/components/comunes/ChipEstado";
import { TituloPagina } from "@/components/layout/encabezado";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { costeUsd, numeroCompacto, numeroCompleto } from "@/lib/formato";
import type {
  LineaTiempoEtapa,
  LineaTiempoGen,
  PipelineActividad,
  PipelineGeneracion,
  RespuestaPipelineDetalle,
} from "@/types";

import { ETAPA_A_EVENTO, MetricasPipeline, PanelEtapa, TiraEtapas } from "./Pipelines";
import { formatearHora, tiempoRelativo } from "@/lib/fecha";
import { INTERVALO_DETALLE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";

/** Ruta del SPA al stream (proceso de pensamiento) de una generación concreta. */
function urlStream(genId: string): string {
  return `/maquina/actividad/generacion/${encodeURIComponent(genId)}`;
}

/** Tokens (en miles) y coste de una generación; nada si ambos son nulos. */
function MetricasGen({ gen }: { gen: LineaTiempoGen }) {
  if (gen.tokens == null && gen.coste_usd == null) return null;
  return (
    <span className="flex items-center gap-2 text-[10px] tabular-nums text-muted-foreground">
      {gen.tokens != null && (
        <span title={`${numeroCompleto(gen.tokens)} tokens`}>{numeroCompacto(gen.tokens)} tok</span>
      )}
      {gen.coste_usd != null && <span>{costeUsd(gen.coste_usd)}</span>}
    </span>
  );
}

/** Una fila de la línea de tiempo: una ETAPA con su estado y, si tuvo reintentos, el desglose
 *  intento a intento (cada uno enlaza a su stream, y enseña su motivo si falló). Con un único
 *  intento, enlace directo. Una etapa terminada en error muestra el motivo del último intento en la
 *  propia fila: es la respuesta a «por qué se paró aquí», y no debe exigir abrir el stream. */
function FilaTimeline({ entrada }: { entrada: LineaTiempoEtapa }) {
  const [abierto, setAbierto] = useState(false);
  const varios = entrada.intentos > 1;
  const unica = entrada.generaciones.length === 1 ? entrada.generaciones[0] : undefined;
  // Motivo del fallo TERMINAL de la etapa (el del último intento): se lee en la propia fila, sin
  // tener que abrir el stream de cada intento para saber por qué se paró el post.
  const ultima = entrada.generaciones[entrada.generaciones.length - 1];
  const fallo = entrada.estado_final === "error" ? (ultima?.error ?? "").trim() : "";
  return (
    <div className="rounded-xl border bg-card">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        {varios ? (
          <button
            type="button"
            onClick={() => setAbierto((v) => !v)}
            aria-expanded={abierto}
            aria-label={`${abierto ? "Colapsar" : "Expandir"} intentos de ${entrada.etapa}`}
            className="-ml-1 rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            {abierto ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        ) : (
          <span className="w-3" aria-hidden="true" />
        )}
        <span className="text-sm font-medium text-foreground">{entrada.etapa}</span>
        <ChipEstado estado={entrada.estado_final} />
        {varios && (
          <span className="text-xs text-muted-foreground">· {entrada.intentos} intentos</span>
        )}
        <div className="ml-auto flex items-center gap-3">
          {unica && <MetricasGen gen={unica} />}
          <span className="text-xs tabular-nums text-muted-foreground">
            {formatearHora(entrada.ultima_fecha)}
          </span>
          {!varios && (
            <Link to={urlStream(entrada.ultima_gen_id)} className="text-xs text-primary hover:underline">
              Ver stream
            </Link>
          )}
        </div>
      </div>
      {fallo && <p className="border-t px-3 py-2 text-xs text-destructive">{fallo}</p>}
      {varios && abierto && (
        <ol className="divide-y border-t">
          {entrada.generaciones.map((g, i) => (
            <li key={g.gen_id} className="px-3 py-1.5 pl-9">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] tabular-nums text-muted-foreground">#{i + 1}</span>
                <ChipEstado estado={g.estado} />
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {formatearHora(g.fecha)}
                </span>
                <div className="ml-auto flex items-center gap-3">
                  <MetricasGen gen={g} />
                  <Link to={urlStream(g.gen_id)} className="text-[11px] text-primary hover:underline">
                    Stream →
                  </Link>
                </div>
              </div>
              {g.error.trim() && (
                <p className="mt-1 text-[11px] text-destructive">{g.error.trim()}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** Rótulo separador de un grupo de la línea de tiempo (p. ej. «Antes del tablero»). */
function RotuloGrupo({ texto }: { texto: string }) {
  return (
    <div className="flex items-center gap-2 pt-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
      <span>{texto}</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

/** Línea de tiempo unificada del post: una fila por etapa en el orden recibido (NO se reordena),
 *  con la fase previa al tablero separada bajo «Antes del tablero». */
function LineaTiempo({ entradas }: { entradas: LineaTiempoEtapa[] }) {
  if (entradas.length === 0) return null;
  const hayPrevia = entradas.some((e) => e.fase_previa);
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-foreground">Línea de tiempo</h2>
      <div className="space-y-1.5">
        {entradas.map((entrada, i) => {
          const anterior = entradas[i - 1];
          // El array ya viene en orden de flujo (pool → tablero); marcamos el cambio de grupo
          // sin reordenar: rótulo antes de la primera fase previa y al entrar al tablero.
          const abrePrevia = entrada.fase_previa && !anterior?.fase_previa;
          const abreTablero = !entrada.fase_previa && hayPrevia && anterior?.fase_previa;
          return (
            <Fragment key={`${entrada.etapa}-${entrada.ultima_gen_id}-${i}`}>
              {abrePrevia && <RotuloGrupo texto="Antes del tablero" />}
              {abreTablero && <RotuloGrupo texto="En el tablero" />}
              <FilaTimeline entrada={entrada} />
            </Fragment>
          );
        })}
      </div>
    </section>
  );
}

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
  const lineaTiempo = datos?.linea_tiempo ?? [];

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
          <div className="overflow-x-auto rounded-xl border bg-card p-3">
            <TiraEtapas etapas={run.etapas} />
          </div>

          {/* Línea de tiempo unificada: TODA la actividad real del post (incl. el Decisor) por etapa,
              con los reintentos colapsados. Es la vista PRINCIPAL del detalle. */}
          <LineaTiempo entradas={lineaTiempo} />

          {/* Entrada → salida por etapa: el prompt y el stream (razonamiento + resultado) de cada
              etapa derivada, inline. Las etapas que NO corrieron («saltada») no se listan. */}
          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-foreground">Entrada y salida por etapa</h2>
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
          </section>
        </>
      )}
    </div>
  );
}
