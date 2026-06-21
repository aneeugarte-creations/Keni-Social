import { Loader2, X } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { costeUsd, duracion, numeroCompleto } from "@/lib/formato";
import type { Generacion, MetricasRun } from "@/types";

/**
 * Línea compacta de métricas en vivo de una generación: turnos, tokens (in/out),
 * coste y duración. Se omite si aún no hay métricas (p. ej. recién lanzada).
 */
function LineaMetricas({ metricas }: { metricas: MetricasRun | null }) {
  if (!metricas) return null;
  const items: { etiqueta: string; valor: string; titulo?: string }[] = [
    { etiqueta: "Turnos", valor: numeroCompleto(metricas.num_turns) },
    {
      etiqueta: "Tokens",
      valor: `${numeroCompleto(metricas.tokens_in)} / ${numeroCompleto(metricas.tokens_out)}`,
      titulo: "Tokens de entrada / salida",
    },
    { etiqueta: "Coste", valor: costeUsd(metricas.total_cost_usd) },
    { etiqueta: "Duración", valor: duracion(metricas.duration_ms) },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {items.map((it) => (
        <span key={it.etiqueta} className="inline-flex items-center gap-1" title={it.titulo}>
          <span>{it.etiqueta}:</span>
          <span className="font-medium tabular-nums text-foreground">{it.valor}</span>
        </span>
      ))}
      {metricas.modelo && (
        <Badge variant="secondary" className="font-mono text-[10px]">
          {metricas.modelo}
        </Badge>
      )}
    </div>
  );
}

/**
 * Etiqueta humana de la ETAPA de progreso (en qué etapa va, no cuánto falta), según la
 * `fase` que deriva el backend del stream. La fase vacía cae a "Visualizando…".
 */
function etiquetaFase(fase: string): string {
  switch (fase) {
    case "razonando":
      return "Razonando…";
    case "generando":
      return "Escribiendo…";
    case "completado":
      return "Terminando…";
    default:
      return "Visualizando…";
  }
}

/**
 * Consola de progreso EN VIVO de una generación de IA: el texto del asistente que
 * va llegando token a token (auto-scroll al final), con un cursor parpadeante
 * mientras corre. Si aún no hay texto, muestra "Pensando…".
 */
function StreamTexto({ texto, ejecutando }: { texto: string; ejecutando: boolean }) {
  const ref = React.useRef<HTMLPreElement>(null);

  // Auto-scroll al final cuando crece el texto (seguir el stream).
  React.useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [texto]);

  if (!texto) {
    return (
      <p className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Pensando…
      </p>
    );
  }
  return (
    <pre
      ref={ref}
      className="max-h-[360px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed"
    >
      {texto}
      {ejecutando && (
        <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-foreground/70 align-middle" />
      )}
    </pre>
  );
}

/** Razonamiento (thinking) EN VIVO mientras el modelo aún no escribe la respuesta.
 * Muestra la cola de pensamiento token a token para dar feedback inmediato (si no, la UI
 * se quedaría en "Pensando…" en seco durante minutos en tareas que razonan mucho). */
function RazonamientoVivo({ texto, ejecutando }: { texto: string; ejecutando: boolean }) {
  const ref = React.useRef<HTMLPreElement>(null);
  React.useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [texto]);
  return (
    <div className="space-y-1">
      <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        Razonando…
      </p>
      <pre
        ref={ref}
        className="max-h-[260px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-dashed border-border bg-muted/30 p-3 text-xs italic leading-relaxed text-muted-foreground"
      >
        {texto}
        {ejecutando && (
          <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-foreground/40 align-middle" />
        )}
      </pre>
    </div>
  );
}

/**
 * Tarjeta reutilizable de progreso de una generación en segundo plano. Mientras
 * corre muestra el texto en vivo + métricas parciales (y, si se pasa `onCancelar`, un
 * botón "Cancelar" que mata el trabajo en el servidor); al terminar con error,
 * muestra el mensaje y (si se pasa) un botón para reintentar. El resultado
 * COMPLETADO lo renderiza cada página a su manera (copy, hashtags, imagen…).
 */
export function ProgresoGeneracion({
  generacion,
  onReintentar,
  onCancelar,
  cancelando = false,
  className,
}: {
  generacion: Generacion;
  /** Si se pasa, se muestra "Reintentar" en el estado de error. */
  onReintentar?: () => void;
  /** Si se pasa, se muestra "Cancelar" mientras corre (mata el trabajo). */
  onCancelar?: () => void;
  /** `true` mientras la cancelación está en curso (deshabilita el botón). */
  cancelando?: boolean;
  className?: string;
}) {
  const ejecutando = generacion.estado === "ejecutando";
  const error = generacion.estado === "error";

  return (
    <Card className={className}>
      <CardHeader className="space-y-2 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">{generacion.etiqueta || ""}</CardTitle>
          {ejecutando ? (
            <Badge variant="aviso" className="gap-1">
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              {etiquetaFase(generacion.fase)}
            </Badge>
          ) : error ? (
            <Badge variant="error">Error</Badge>
          ) : (
            <Badge variant="ok">Completado</Badge>
          )}
          {ejecutando && onCancelar && (
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              onClick={onCancelar}
              disabled={cancelando}
            >
              {cancelando ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              ) : (
                <X className="h-3.5 w-3.5" aria-hidden />
              )}
              Cancelar
            </Button>
          )}
        </div>
        <LineaMetricas metricas={generacion.metricas} />
      </CardHeader>
      <CardContent className={cn("pt-0", error && "space-y-3")}>
        {error ? (
          <>
            <p className="text-sm text-destructive">
              {generacion.error || "Error"}
            </p>
            {onReintentar && (
              <Button variant="outline" size="sm" onClick={onReintentar}>
                Reintentar
              </Button>
            )}
          </>
        ) : !generacion.salida && generacion.razonamiento ? (
          // Aún no hay respuesta pero el modelo ya razona: mostramos el thinking en vivo.
          <RazonamientoVivo texto={generacion.razonamiento} ejecutando={ejecutando} />
        ) : (
          <StreamTexto texto={generacion.salida} ejecutando={ejecutando} />
        )}
      </CardContent>
    </Card>
  );
}
