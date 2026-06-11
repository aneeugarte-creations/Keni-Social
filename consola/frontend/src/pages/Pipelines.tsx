import { AlertTriangle, ChevronDown, ChevronRight, Clock, Coins, OctagonAlert, Sparkles } from "lucide-react";
import * as React from "react";

import { aspectoEstado, ChipEstado } from "@/components/comunes/ChipEstado";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Markdown } from "@/components/ui/Markdown";
import { tiempoRelativo } from "@/lib/fecha";
import { costeUsd, duracion, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { cn } from "@/lib/utils";
import type {
  Pipeline,
  PipelineActividad,
  PipelineCluster,
  PipelineEtapa,
  PipelineGeneracion,
  PipelineHallazgo,
  PipelineMetricas,
  PipelineQaFuente,
} from "@/types";

// Verificación por corroboración (Ola D) -> etiqueta corta para los chips de procedencia IA.
const VERIFICACION_TEXTO: Record<string, string> = {
  corroborada: "corroborada",
  unica_fuente: "1 sola fuente",
  dudosa: "dudosa",
};

// El aspecto de los estados (badge + etiqueta) vive CONSOLIDADO en el chip único de la
// consola (`components/comunes/ChipEstado`): misma etiqueta y color que Actividad/Monitor.
export { ChipEstado };

// Etapa (clave) -> código de etapa de los eventos de actividad (la traza CI/CD/QA).
export const ETAPA_A_EVENTO: Record<string, string> = {
  fusion: "FUSION", editorial: "EDITORIAL", ci: "CI", qa: "QA", cd: "CD", arte: "ARTE",
};

// Catálogo de etapas para el filtro `?etapa=` (espeja `_ETAPAS` del back, en orden de flujo).
export const ETAPAS_FILTRO: { clave: string; nombre: string }[] = [
  { clave: "fusion", nombre: "Fusión" },
  { clave: "editorial", nombre: "Editorial" },
  { clave: "ci", nombre: "Selección" },
  { clave: "qa", nombre: "Validación" },
  { clave: "cd", nombre: "Copy" },
  { clave: "arte", nombre: "Arte" },
  { clave: "aprobacion", nombre: "Aprobación" },
];
// Valores del filtro `?estado=` (el `estado_global` de la run). Nombres = los del chip
// único (`aspectoEstado`): el filtro y el badge dicen lo mismo.
export const ESTADOS_FILTRO: { clave: string; nombre: string }[] = [
  { clave: "pendiente", nombre: "Pendiente" },
  { clave: "en_curso", nombre: "En curso" },
  { clave: "revisar", nombre: "Revisar" },
  { clave: "fallo", nombre: "Error" },
  { clave: "ok", nombre: "Completado" },
];

/** Chip de la criba de la fuente (rediseño QPC): ⚠️ "No verificado" o ❗ "QA: problema".
 *  Nada si aún no hay veredicto (criba pendiente/en curso: lo cubre la tira de etapas). */
function BadgeQaFuente({ qa, className }: { qa?: PipelineQaFuente; className?: string }) {
  if (!qa) return null;
  if (qa.problema) {
    return (
      <Badge
        variant="secondary"
        className={cn("gap-1 border border-destructive/30 bg-destructive/10 text-destructive", className)}
        title={qa.resumen || "La criba encontró un problema de peso; no se generó copy."}
      >
        <OctagonAlert className="h-3 w-3" aria-hidden="true" />
        Problema
      </Badge>
    );
  }
  if (qa.no_verificado) {
    return (
      <Badge
        variant="secondary"
        className={cn("gap-1 border border-amber-500/30 bg-amber-500/15 text-amber-600", className)}
        title="Fuente apta pero NO verificada a fondo: revisa antes de aprobar."
      >
        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
        No verificado
      </Badge>
    );
  }
  return null;
}

/** Lista de hallazgos de la criba (lo que está mal en la nota de origen). Nada si vacía. */
function ListaHallazgos({ hallazgos }: { hallazgos: PipelineHallazgo[] }) {
  if (!hallazgos || hallazgos.length === 0) return null;
  return (
    <ul className="space-y-1.5">
      {hallazgos.map((h, i) => (
        <li key={i} className="rounded border border-destructive/20 bg-destructive/5 p-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            {h.tipo && <Badge variant="outline" className="text-[10px]">{h.tipo}</Badge>}
            {h.gravedad && (
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px]",
                  h.gravedad === "error" && "border-destructive/40 text-destructive",
                )}
              >
                {h.gravedad}
              </Badge>
            )}
          </div>
          {h.fragmento && <p className="mt-1 italic text-muted-foreground">«{h.fragmento}»</p>}
          {h.explicacion && <p className="mt-1 text-foreground/90">{h.explicacion}</p>}
          {h.sugerencia && <p className="mt-1 text-muted-foreground">Sugerencia: {h.sugerencia}</p>}
        </li>
      ))}
    </ul>
  );
}

/** Chips de las señales del cluster. `modo` decide cuáles: "fusion" (dedup: fuentes/notas) o
 *  "editorial" (score/verificación/viralidad). */
function ProcedenciaIA({ cluster, modo }: { cluster: PipelineCluster; modo: "fusion" | "editorial" }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {modo === "fusion" && (
        <>
          <Badge variant="outline" className="text-[10px]">{cluster.n_fuentes} fuentes</Badge>
          {cluster.n_items > 1 && (
            <Badge variant="outline" className="text-[10px]">{cluster.n_items} notas</Badge>
          )}
        </>
      )}
      {modo === "editorial" && (
        <>
          <Badge variant="outline" className="text-[10px]">Score {cluster.score.toFixed(2)}</Badge>
          {cluster.verificacion && (
            <Badge variant="outline" className="text-[10px]">
              {VERIFICACION_TEXTO[cluster.verificacion] ?? cluster.verificacion}
            </Badge>
          )}
          {cluster.breaking && (
            <Badge variant="secondary" className="border border-amber-500/30 bg-amber-500/15 text-[10px] text-amber-600">
              🔥 breaking
            </Badge>
          )}
          {cluster.senal > 0 && (
            <Badge variant="outline" className="text-[10px]">viralidad {cluster.senal.toLocaleString("es-MX")}</Badge>
          )}
        </>
      )}
    </div>
  );
}

function Punto({ estado }: { estado: string }) {
  return (
    <span
      className={cn(
        "h-2 w-2 shrink-0 rounded-full",
        estado === "ok" && "bg-emerald-500",
        estado === "en_curso" && "bg-sky-500 animate-pulse",
        estado === "revisar" && "bg-amber-500",
        estado === "pendiente" && "bg-muted-foreground/40",
        estado === "saltada" && "bg-muted-foreground/20 ring-1 ring-muted-foreground/30",
        estado === "fallo" && "bg-destructive",
      )}
    />
  );
}

/** Tira horizontal de etapas (CI · CD · QA · Aprobación), estilo pipeline de GitLab. */
export function TiraEtapas({ etapas }: { etapas: PipelineEtapa[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {etapas.map((e, i) => (
        <React.Fragment key={e.clave}>
          <div
            className={cn(
              "flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
              aspectoEstado(e.estado).clase || "text-muted-foreground",
            )}
            title={e.detalle}
          >
            <Punto estado={e.estado} />
            <span className="font-medium">{e.nombre}</span>
          </div>
          {i < etapas.length - 1 && <span className="text-muted-foreground/40">→</span>}
        </React.Fragment>
      ))}
    </div>
  );
}

/** Chips de las MÉTRICAS de un item del feed (tokens · coste · duración). Nada si no hay
 *  ninguna métrica todavía (run sin generaciones / trabajo aún en cola). */
export function MetricasPipeline({ metricas, className }: { metricas?: PipelineMetricas; className?: string }) {
  if (!metricas) return null;
  const { tokens, coste_usd, duration_ms } = metricas;
  if (tokens == null && coste_usd == null && duration_ms == null) return null;
  if (!metricas.items && !tokens && !coste_usd && !duration_ms) return null;
  return (
    <span className={cn("flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground", className)}>
      {tokens != null && (
        <Badge variant="outline" className="gap-1 text-[10px] tabular-nums" title={`${numeroCompleto(tokens)} tokens`}>
          {numeroCompacto(tokens)} tok
        </Badge>
      )}
      {coste_usd != null && (
        <Badge variant="outline" className="gap-1 text-[10px] tabular-nums" title="Coste de las generaciones">
          <Coins className="h-2.5 w-2.5" aria-hidden="true" />
          {costeUsd(coste_usd)}
        </Badge>
      )}
      {duration_ms != null && duration_ms > 0 && (
        <Badge variant="outline" className="gap-1 text-[10px] tabular-nums" title="Tiempo de cómputo IA">
          <Clock className="h-2.5 w-2.5" aria-hidden="true" />
          {duracion(duration_ms)}
        </Badge>
      )}
    </span>
  );
}

/** Etapas a PINTAR de un item del feed: las de la run tal cual; en un item SUELTO, su única
 *  etapa lleva como nombre la etiqueta legible de su tipo de trabajo (copy, imagen, run…). */
export function etapasDeItem(run: Pipeline): PipelineEtapa[] {
  if (run.clase !== "actividad") return run.etapas;
  return run.etapas.map((e) => ({ ...e, nombre: etiquetaTipoGeneracion(run.tipo || e.nombre) }));
}

/** Tarjeta de un item del feed de Producción (run del pipeline o trabajo suelto): TODA la
 *  tarjeta es clicable (abre su detalle) salvo que no haya detalle que abrir (`onAbrir` null). */
function FilaPipeline({ run, onAbrir }: { run: Pipeline; onAbrir: ((run: Pipeline) => void) | null }) {
  const esActividad = run.clase === "actividad";
  return (
    <Card
      role={onAbrir ? "button" : undefined}
      tabIndex={onAbrir ? 0 : undefined}
      onClick={onAbrir ? () => onAbrir(run) : undefined}
      onKeyDown={(e) => {
        if (onAbrir && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onAbrir(run);
        }
      }}
      className={cn(
        "transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        onAbrir && "cursor-pointer hover:bg-muted/40",
      )}
    >
      <CardContent className="flex items-center gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="shrink-0">{run.marca_nombre || run.marca}</Badge>
            {esActividad && (
              <Badge variant="secondary" className="shrink-0 gap-1 text-[10px]" title="Trabajo de IA fuera del pipeline">
                <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
                {etiquetaTipoGeneracion(run.tipo || "")}
              </Badge>
            )}
            <ChipEstado estado={run.estado_global} />
            <BadgeQaFuente qa={run.qa_fuente ?? undefined} />
            {run.cluster && (
              <Badge
                variant="outline"
                className="shrink-0 gap-1 text-[10px]"
                title={`Historia jerarquizada por IA: ${run.cluster.n_fuentes} fuente(s), score ${run.cluster.score.toFixed(2)}`}
              >
                <Sparkles className="h-3 w-3" aria-hidden="true" />
                {run.cluster.n_fuentes} fuente(s)
              </Badge>
            )}
            <span className="truncate text-xs text-muted-foreground">{tiempoRelativo(run.creado)}</span>
            <MetricasPipeline metricas={run.metricas} className="ml-auto" />
          </div>
          <p className="truncate text-sm font-medium" title={run.titulo}>{run.titulo}</p>
          <TiraEtapas etapas={etapasDeItem(run)} />
        </div>
        {onAbrir && <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />}
      </CardContent>
    </Card>
  );
}

export { FilaPipeline };

function EventosEtapa({ eventos }: { eventos: PipelineActividad[] }) {
  if (eventos.length === 0) return null;
  return (
    <ul className="space-y-1">
      {eventos.map((ev, i) => (
        <li key={i} className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <span className="truncate" title={ev.etiqueta}>{ev.etiqueta}</span>
          <span className="shrink-0">{tiempoRelativo(ev.fecha)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Bloque de TRANSPARENCIA de una etapa IA: el PROMPT de entrada (real si corrió; plantilla si
 *  no), el RAZONAMIENTO (proceso de pensamiento, stream del agente) y el RESULTADO. Se enseña
 *  SIEMPRE en etapas IA, aunque aún no se haya ejecutado (entonces el prompt es la plantilla y el
 *  proceso/resultado quedan "pendiente"). `gen` es la generación real (si existe). */
function BloqueIA({ gen, plantilla }: { gen?: PipelineGeneracion; plantilla?: string }) {
  const enCurso = gen?.estado === "ejecutando";
  const salida = (gen?.salida ?? "").trim();
  const prompt = (gen?.prompt || plantilla || "").trim();
  const esPlantilla = !gen?.prompt && !!plantilla;
  const m = gen?.metricas;
  return (
    <div className="space-y-2 rounded-md border border-violet-500/20 bg-violet-500/5 p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="h-3 w-3 text-violet-600" aria-hidden="true" />
        <span className="text-xs font-semibold text-foreground">IA</span>
        {gen
          ? <ChipEstado estado={enCurso ? "en_curso" : gen.estado === "error" ? "fallo" : "ok"} />
          : <span className="text-[11px] text-muted-foreground">aún no ejecutado</span>}
        {/* Métricas REALES de la llamada (tokens/coste/duración), si la generación las dejó. */}
        {m && (
          <MetricasPipeline
            className="ml-auto"
            metricas={{
              items: 1,
              tokens: (m.tokens_in ?? 0) + (m.tokens_out ?? 0) || null,
              coste_usd: m.total_cost_usd ?? null,
              duration_ms: m.duration_ms ?? null,
            }}
          />
        )}
      </div>
      {/* ENTRADA (prompt) ↔ SALIDA (razonamiento + resultado), lado a lado en pantallas anchas
          (la página dedicada) y apilados en estrecho (el feed móvil). */}
      <div className="grid gap-2 lg:grid-cols-2">
        <div className="min-w-0 space-y-1">
          <div className="text-[11px] font-medium text-muted-foreground">
            Entrada · prompt{esPlantilla ? " (plantilla)" : ""}
          </div>
          {prompt ? (
            <div className="max-h-72 overflow-y-auto rounded bg-background/60 p-2">
              <Markdown className="text-xs text-foreground/80">{prompt}</Markdown>
            </div>
          ) : <p className="text-[11px] italic text-muted-foreground">Prompt no disponible.</p>}
        </div>
        <div className="min-w-0 space-y-1">
          <div className="text-[11px] font-medium text-muted-foreground">Salida · razonamiento + resultado</div>
          {salida ? (
            <div className="max-h-72 overflow-y-auto rounded bg-background/60 p-2">
              <Markdown className="text-xs text-foreground/90">{salida}</Markdown>
            </div>
          ) : (
            <p className="text-xs italic text-muted-foreground">
              {enCurso ? "En curso…" : "Pendiente: esta etapa aún no se ha ejecutado."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** Contenido COMPLETO específico de cada etapa. Las etapas IA enseñan SIEMPRE el BloqueIA
 *  (prompt + razonamiento + resultado); las no-IA muestran su dato propio. */
function ContenidoEtapa({
  clave,
  estado,
  run,
  generacion,
  plantilla,
}: {
  clave: string;
  estado: string;
  run: Pipeline;
  generacion?: PipelineGeneracion;
  plantilla?: string;
}) {
  if (clave === "fusion" || clave === "editorial") {
    return (
      <div className="space-y-2 text-xs">
        {run.cluster
          ? <ProcedenciaIA cluster={run.cluster} modo={clave} />
          : <p className="text-muted-foreground">Sin historia.</p>}
        <BloqueIA gen={generacion} plantilla={plantilla} />
      </div>
    );
  }
  if (clave === "ci") {
    // Selección: crea el tema en BD (no es IA). Solo la nota de origen.
    return run.descripcion
      ? <Markdown className="text-xs text-muted-foreground">{run.descripcion}</Markdown>
      : null;
  }
  if (clave === "cd") {
    // Solo el bloque IA (prompt | razonamiento + resultado): el copy final por red ya se ve
    // en la SALIDA del bloque y, sobre todo, en el feed/aprobación (su sitio). Repetir aquí
    // las tarjetas por red (X/Instagram/Facebook con placa) era ruido duplicado.
    return <BloqueIA gen={generacion} plantilla={plantilla} />;
  }
  if (clave === "arte") {
    // Solo si el arte IA CORRIÓ (estado ok): una pieza puede traer la FOTO de la nota de una
    // fuente propia (bajada en la ingesta) sin que esta etapa la generara — esa foto vive en
    // la pieza (feed/aprobación), no aquí. Enseñarla con la etapa apagada mentía ("Arte ok").
    const imagenes = estado === "ok" ? run.piezas.filter((p) => p.imagen_url) : [];
    return (
      <div className="space-y-2">
        <BloqueIA gen={generacion} plantilla={plantilla} />
        {imagenes.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {imagenes.map((p, i) => (
              <img key={`${p.red}-${i}`} src={p.imagen_url} alt={p.red_nombre} loading="lazy"
                className="h-24 w-24 rounded border object-cover" />
            ))}
          </div>
        )}
      </div>
    );
  }
  if (clave === "qa") {
    const qa = run.qa_fuente;
    return (
      <div className="space-y-2">
        <BloqueIA gen={generacion} plantilla={plantilla} />
        {qa && (qa.no_verificado || qa.problema) && (
          <div className="space-y-2 rounded-md border p-2">
            <BadgeQaFuente qa={qa} />
            {qa.resumen && <p className="text-xs text-foreground/90">{qa.resumen}</p>}
            <ListaHallazgos hallazgos={qa.hallazgos} />
          </div>
        )}
      </div>
    );
  }
  if (clave === "trabajo") {
    // Trabajo SUELTO (item `clase="actividad"` del feed): todo el trabajo es UNA etapa IA;
    // su contenido es el bloque entrada/salida de la generación, sin piezas ni criba.
    return <BloqueIA gen={generacion} plantilla={plantilla} />;
  }
  // aprobacion — gate HUMANO (no IA).
  return (
    <div className="space-y-1.5">
      {run.piezas.map((p, i) => (
        <div key={`${p.red}-${i}`} className="flex items-center justify-between gap-2 rounded-md border p-2 text-xs">
          <span className="font-semibold">{p.red_nombre}</span>
          <div className="flex flex-col items-end gap-0.5 text-muted-foreground">
            <Badge variant="outline">{p.estado}</Badge>
            {p.revisor_nombre && <span>{p.revisor_nombre} · {tiempoRelativo(p.revisado_en || "")}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Panel INDEPENDIENTE y plegable de una etapa: cabecera siempre visible (nombre + estado)
 *  y, al desplegar, el detalle COMPLETO de lo ocurrido en ese paso. Cada panel se abre/cierra
 *  por su cuenta (estado local propio). */
export function PanelEtapa({
  etapa,
  run,
  eventos,
  generacion,
  plantilla,
  defaultOpen,
}: {
  etapa: PipelineEtapa;
  run: Pipeline;
  eventos: PipelineActividad[];
  generacion?: PipelineGeneracion;
  plantilla?: string;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="rounded-lg border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-left hover:bg-muted/40"
      >
        <span className="flex items-center gap-2">
          <Punto estado={etapa.estado} />
          <span className="text-sm font-semibold">{etapa.nombre}</span>
          {/* Marca clara IA vs no-IA (Selección = Sistema/BD; Aprobación = Humano). */}
          {etapa.es_ia ? (
            <Badge variant="outline" className="gap-1 border-violet-500/30 text-[10px] text-violet-600">
              <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />IA
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] text-muted-foreground">
              {etapa.clave === "aprobacion" ? "Humano" : "Sistema"}
            </Badge>
          )}
          <ChipEstado estado={etapa.estado} />
        </span>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div className="space-y-3 border-t p-3">
          {etapa.detalle && <p className="text-xs text-muted-foreground">{etapa.detalle}</p>}
          <EventosEtapa eventos={eventos} />
          <ContenidoEtapa clave={etapa.clave} estado={etapa.estado} run={run} generacion={generacion} plantilla={plantilla} />
        </div>
      )}
    </div>
  );
}

// La antigua vista «Pipelines» (y la pestaña «Feed» del hub Actividad IA) viven hoy
// FUSIONADAS en la página Producción (`pages/Produccion.tsx`): una sola línea temporal de
// runs del pipeline + actividad suelta. Este módulo conserva la maquinaria de render
// compartida (tarjeta del feed, tira de etapas, panel por etapa, bloque IA, métricas) que
// usan Producción y los detalles (`PipelineDetalle`, `GeneracionDetalle`).
