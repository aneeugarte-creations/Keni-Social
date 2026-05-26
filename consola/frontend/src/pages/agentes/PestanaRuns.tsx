import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Loader2, Play } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import type { BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { costeUsd, duracion, numeroCompleto } from "@/lib/formato";
import type { AgenteDetalle, EstadoRun, MetricasRun, ModoRun, Run } from "@/types";

import { claveAgente, claveRuns, formatearFecha, mensajeError } from "./claves";

/** Etiqueta legible (es-MX) del modo de un run. */
function etiquetaModo(modo: ModoRun): string {
  return modo === "interactivo" ? "Interactivo" : "Headless";
}

/** `true` mientras el run está en curso (sondeo activo). */
function estaEjecutando(estado: EstadoRun): boolean {
  return estado === "ejecutando";
}

/**
 * Etiqueta + variante de badge para el estado de un run. El estado `ejecutando`
 * usa la variante ámbar (`aviso`) y marca que debe llevar spinner.
 */
function presentacionEstado(estado: EstadoRun): {
  texto: string;
  variante: BadgeProps["variant"];
  spinner?: boolean;
} {
  switch (estado) {
    case "completado":
      return { texto: "Completado", variante: "ok" };
    case "error":
      return { texto: "Error", variante: "error" };
    case "ejecutando":
      return { texto: "Ejecutando…", variante: "aviso", spinner: true };
    case "lanzado":
      return { texto: "Lanzado", variante: "secondary" };
    default:
      return { texto: estado, variante: "secondary" };
  }
}

/** Badge de estado de un run; el estado en curso muestra un spinner. */
function BadgeEstado({ estado }: { estado: EstadoRun }) {
  const { texto, variante, spinner } = presentacionEstado(estado);
  return (
    <Badge variant={variante} className={cn(spinner && "gap-1")}>
      {spinner && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
      {texto}
    </Badge>
  );
}

/**
 * Línea compacta de métricas de un run completado: turnos, tokens (in/out),
 * coste USD y duración. Se omite por completo si el run no trae `metricas`
 * (p. ej. el CLI no devolvió JSON o fue interactivo).
 */
function MetricasRunLinea({ metricas }: { metricas: MetricasRun | null | undefined }) {
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

/** Muestra la salida de un run como texto preformateado (auto-scroll al final). */
function SalidaRun({ salida }: { salida: string }) {
  const ref = React.useRef<HTMLPreElement>(null);
  // Seguir el stream: al crecer el texto, bajamos al final.
  React.useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [salida]);
  return (
    <pre
      ref={ref}
      className="max-h-[400px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed"
    >
      {salida}
    </pre>
  );
}

/** Cada cuánto sondeamos el estado de un run en curso. */
const INTERVALO_SONDEO_MS = 1500;

/**
 * Sondea el detalle de un run mientras esté `ejecutando` y detiene el sondeo al
 * terminar (`completado`/`error`). Arranca con `runInicial` (lo que devolvió el
 * `POST`) y, al pasar a un estado final, invalida el detalle del agente y la
 * lista global de runs. Devuelve el run más reciente conocido.
 */
function useSondeoRun(agenteId: string, runInicial: Run): Run {
  const queryClient = useQueryClient();
  // Solo tiene sentido sondear runs headless en curso; los interactivos y los
  // que ya terminaron al volver del POST no necesitan red adicional.
  const sondeable = runInicial.modo === "headless" && estaEjecutando(runInicial.estado);
  const yaFinalizado = React.useRef(false);

  const { data } = useQuery({
    queryKey: claveRuns(agenteId).concat(runInicial.id),
    queryFn: ({ signal }) => api.runAgente(agenteId, runInicial.id, signal),
    initialData: runInicial,
    enabled: sondeable,
    // Mientras el run siga ejecutando, repetimos; al terminar devolvemos `false`
    // para cortar el sondeo.
    refetchInterval: (query) =>
      estaEjecutando(query.state.data?.estado ?? runInicial.estado)
        ? INTERVALO_SONDEO_MS
        : false,
  });

  const run = data ?? runInicial;

  // Al pasar a un estado final, refrescamos el detalle del agente (su lista de
  // runs) y la lista global del Monitor. Una sola vez por run.
  React.useEffect(() => {
    if (!yaFinalizado.current && !estaEjecutando(run.estado)) {
      yaFinalizado.current = true;
      void queryClient.invalidateQueries({ queryKey: claveAgente(agenteId) });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    }
  }, [run.estado, agenteId, queryClient]);

  return run;
}

/** Bloque de resultado del último lanzamiento (en vivo mientras corre). */
function ResultadoRun({ agenteId, runInicial }: { agenteId: string; runInicial: Run }) {
  const run = useSondeoRun(agenteId, runInicial);
  const ejecutando = estaEjecutando(run.estado);

  return (
    <div className="mt-5 space-y-2 border-t border-border pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Resultado</span>
        <BadgeEstado estado={run.estado} />
        <Badge variant="outline">{etiquetaModo(run.modo)}</Badge>
      </div>
      {/* Métricas parciales en vivo mientras corre; finales al terminar. */}
      <MetricasRunLinea metricas={run.metricas} />
      {/* El texto del asistente aparece en vivo (token a token) en cuanto llega. */}
      {run.salida ? (
        <SalidaRun salida={run.salida} />
      ) : ejecutando ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Ejecutando… el texto y las métricas aparecen en vivo.
        </p>
      ) : run.mensaje ? (
        <p className="text-sm text-muted-foreground">{run.mensaje}</p>
      ) : null}
    </div>
  );
}

/** Formulario para lanzar un run + resultado (en vivo) del último lanzamiento. */
function FormularioRun({ agente }: { agente: AgenteDetalle }) {
  const queryClient = useQueryClient();
  const [prompt, setPrompt] = React.useState("");
  const [modo, setModo] = React.useState<ModoRun>("headless");
  const [ultimo, setUltimo] = React.useState<Run | null>(null);

  const ejecutar = useMutation({
    mutationFn: () => api.crearRunAgente(agente.id, { prompt: prompt.trim(), modo }),
    onSuccess: (res) => {
      setUltimo(res.run);
      void queryClient.invalidateQueries({ queryKey: claveAgente(agente.id) });
      if (res.run.estado === "error") {
        toast.error("El run terminó con error.");
      } else if (res.run.modo === "interactivo") {
        toast.success(res.run.mensaje || "Run interactivo lanzado.");
      } else if (estaEjecutando(res.run.estado)) {
        toast.success("Run lanzado. Sigue el progreso aquí abajo.");
      } else {
        toast.success("Run completado.");
      }
      setPrompt("");
    },
    onError: (error) => toast.error(mensajeError(error)),
  });

  const valido = prompt.trim().length > 0 && !ejecutar.isPending;

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (valido) ejecutar.mutate();
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Nueva ejecución</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <form onSubmit={enviar} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="run-prompt">Prompt</Label>
            <Textarea
              id="run-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="¿Qué quieres que haga el agente?"
              rows={4}
              disabled={ejecutar.isPending}
            />
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-2">
              <Label htmlFor="run-modo">Modo</Label>
              <Select
                value={modo}
                onValueChange={(v) => setModo(v as ModoRun)}
                disabled={ejecutar.isPending}
              >
                <SelectTrigger id="run-modo" className="w-full sm:w-[220px]">
                  <SelectValue placeholder="Modo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="headless">Headless (sigue el progreso aquí)</SelectItem>
                  <SelectItem value="interactivo">Interactivo (abre Claude Code)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button type="submit" disabled={!valido}>
              <Play className={cn("h-4 w-4", ejecutar.isPending && "animate-pulse")} />
              {ejecutar.isPending ? "Lanzando…" : "Ejecutar"}
            </Button>
          </div>
        </form>

        {ultimo && <ResultadoRun key={ultimo.id} agenteId={agente.id} runInicial={ultimo} />}
      </CardContent>
    </Card>
  );
}

/** Fila del historial: cabecera con metadatos + salida expandible. */
function FilaRun({ run }: { run: Run }) {
  const [abierto, setAbierto] = React.useState(false);
  const tieneDetalle = Boolean(run.salida || run.mensaje);

  return (
    <li>
      <button
        type="button"
        onClick={() => tieneDetalle && setAbierto((v) => !v)}
        disabled={!tieneDetalle}
        className={cn(
          "flex w-full items-start gap-3 px-4 py-3 text-left transition-colors",
          tieneDetalle ? "hover:bg-accent/50" : "cursor-default",
        )}
        aria-expanded={tieneDetalle ? abierto : undefined}
      >
        <span className="mt-0.5 shrink-0 text-muted-foreground">
          {tieneDetalle ? (
            abierto ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )
          ) : (
            <span className="inline-block h-4 w-4" />
          )}
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <BadgeEstado estado={run.estado} />
            <Badge variant="outline">{etiquetaModo(run.modo)}</Badge>
            <span className="text-xs text-muted-foreground">{formatearFecha(run.fecha_inicio)}</span>
          </div>
          <p className="truncate text-sm" title={run.prompt}>
            {run.prompt || <span className="text-muted-foreground">Sin prompt</span>}
          </p>
          <MetricasRunLinea metricas={run.metricas} />
        </div>
      </button>
      {abierto && tieneDetalle && (
        <div className="px-4 pb-3 pl-11">
          {run.salida ? (
            <SalidaRun salida={run.salida} />
          ) : (
            <p className="text-sm text-muted-foreground">{run.mensaje}</p>
          )}
        </div>
      )}
    </li>
  );
}

/** Historial de runs del agente, más recientes primero. */
function HistorialRuns({ runs }: { runs: Run[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          Historial
          <Badge variant="secondary">{runs.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {runs.length === 0 ? (
          <EstadoVacioTexto texto="Aún no hay ejecuciones. Lanza un run desde el formulario de arriba." />
        ) : (
          <ul className="divide-y divide-border">
            {runs.map((run) => (
              <FilaRun key={run.id} run={run} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** Pestaña «Runs»: formulario de ejecución + historial. */
export function PestanaRuns({ agente }: { agente: AgenteDetalle }) {
  return (
    <div className="space-y-6">
      <FormularioRun agente={agente} />
      <HistorialRuns runs={agente.runs} />
    </div>
  );
}
