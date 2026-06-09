import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronRight, GitBranch, OctagonAlert, RefreshCw, Sparkles } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import type { BadgeProps } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  Pipeline,
  PipelineActividad,
  PipelineCluster,
  PipelineEtapa,
  PipelineGeneracion,
  PipelineHallazgo,
  PipelineQaFuente,
  RespuestaPipelineDetalle,
  RespuestaPipelines,
} from "@/types";

// Verificación por corroboración (Ola D) -> etiqueta corta para los chips de procedencia IA.
const VERIFICACION_TEXTO: Record<string, string> = {
  corroborada: "corroborada",
  unica_fuente: "1 sola fuente",
  dudosa: "dudosa",
};

// Estado de etapa/run -> aspecto del badge + etiqueta corta. Mapeo único para toda la
// página (la tira de etapas y el chip de estado global comparten convención GitLab-like).
const ASPECTO: Record<string, { variant: BadgeProps["variant"]; clase: string; texto: string }> = {
  ok: { variant: "secondary", clase: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30", texto: "OK" },
  en_curso: { variant: "secondary", clase: "bg-sky-500/15 text-sky-600 border-sky-500/30", texto: "En curso" },
  revisar: { variant: "secondary", clase: "bg-amber-500/15 text-amber-600 border-amber-500/30", texto: "Revisar" },
  pendiente: { variant: "outline", clase: "text-muted-foreground", texto: "Pendiente" },
  saltada: { variant: "outline", clase: "text-muted-foreground/60 border-dashed line-through", texto: "Saltada" },
  fallo: { variant: "destructive", clase: "", texto: "Fallo" },
};

// Etapa (clave) -> código de etapa de los eventos de actividad (la traza CI/CD/QA).
const ETAPA_A_EVENTO: Record<string, string> = { jerarquia: "JERARQUIA", ci: "CI", cd: "CD", qa: "QA" };

// Catálogo de etapas para el filtro `?etapa=` (espeja `_ETAPAS` del back, en orden de flujo).
const ETAPAS_FILTRO: { clave: string; nombre: string }[] = [
  { clave: "jerarquia", nombre: "Ranking" },
  { clave: "ci", nombre: "Selección" },
  { clave: "qa", nombre: "Criba" },
  { clave: "cd", nombre: "Copy" },
  { clave: "aprobacion", nombre: "Aprobación" },
];
// Valores del filtro `?estado=` (el `estado_global` de la run).
const ESTADOS_FILTRO: { clave: string; nombre: string }[] = [
  { clave: "pendiente", nombre: "Pendiente" },
  { clave: "en_curso", nombre: "En curso" },
  { clave: "revisar", nombre: "Revisar" },
  { clave: "fallo", nombre: "Fallo" },
  { clave: "ok", nombre: "Completado" },
];
// Tamaño de página del botón «Cargar más» (se pide `limite = páginas * PAGINA`, offset 0).
const PAGINA = 20;

// Fase de progreso de la generación (`claude -p`) -> etiqueta humana para la cabecera del
// stream. Espeja las fases del dominio (stream.FASE_*): razonando → generando → completado.
const FASE_TEXTO: Record<string, string> = {
  razonando: "Razonando…",
  generando: "Escribiendo…",
  completado: "Completado",
};

/** Etiqueta legible del estado/fase de una generación del agente (para la cabecera). */
function faseTexto(gen: PipelineGeneracion): string {
  if (gen.estado === "error") return "Error";
  if (gen.estado === "ejecutando") return FASE_TEXTO[gen.fase] ?? "En curso…";
  return FASE_TEXTO[gen.fase] ?? "Completado";
}

function aspecto(estado: string) {
  return ASPECTO[estado] ?? ASPECTO.pendiente;
}

function ChipEstado({ estado, className }: { estado: string; className?: string }) {
  const a = aspecto(estado);
  return (
    <Badge variant={a.variant} className={cn("border", a.clase, className)}>
      {a.texto}
    </Badge>
  );
}

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
        QA: problema
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

/** Chips de PROCEDENCIA IA: las señales reales del pool (corroboración, fusión, score,
 *  verificación, breaking) que la IA usó para deduplicar y jerarquizar la historia. */
function ProcedenciaIA({ cluster }: { cluster: PipelineCluster }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge variant="outline" className="text-[10px]">{cluster.n_fuentes} fuente(s)</Badge>
      {cluster.n_items > 1 && (
        <Badge variant="outline" className="text-[10px]">{cluster.n_items} notas agrupadas</Badge>
      )}
      <Badge variant="outline" className="text-[10px]">score {cluster.score.toFixed(2)}</Badge>
      {cluster.verificacion && (
        <Badge variant="outline" className="text-[10px]">
          {VERIFICACION_TEXTO[cluster.verificacion] ?? cluster.verificacion}
        </Badge>
      )}
      {cluster.breaking && (
        <Badge variant="secondary" className="gap-1 border border-amber-500/30 bg-amber-500/15 text-[10px] text-amber-600">
          🔥 breaking
        </Badge>
      )}
      {cluster.senal > 0 && (
        <Badge variant="outline" className="text-[10px]">viralidad {cluster.senal.toLocaleString("es-MX")}</Badge>
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
function TiraEtapas({ etapas }: { etapas: PipelineEtapa[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {etapas.map((e, i) => (
        <React.Fragment key={e.clave}>
          <div
            className={cn(
              "flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
              aspecto(e.estado).clase || "text-muted-foreground",
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

function tiempoRelativo(iso: string): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const seg = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (seg < 60) return "hace un momento";
  const min = Math.floor(seg / 60);
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `hace ${h} h`;
  const d = Math.floor(h / 24);
  return `hace ${d} d`;
}

/** Tarjeta de una run: TODA la tarjeta es clicable (abre el detalle). */
function FilaPipeline({ run, onAbrir }: { run: Pipeline; onAbrir: (id: string) => void }) {
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onAbrir(run.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onAbrir(run.id);
        }
      }}
      className="cursor-pointer transition-colors hover:bg-muted/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <CardContent className="flex items-center gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="shrink-0">{run.marca_nombre || run.marca}</Badge>
            <ChipEstado estado={run.estado_global} />
            <BadgeQaFuente qa={run.qa_fuente} />
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
          </div>
          <p className="truncate text-sm font-medium" title={run.titulo}>{run.titulo}</p>
          <TiraEtapas etapas={run.etapas} />
        </div>
        <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      </CardContent>
    </Card>
  );
}

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

/** Stream del agente (`claude -p`) de una etapa: el PROCESO DE PENSAMIENTO (lo que el agente
 *  dijo/hizo), no solo el resultado. Bloque monoespaciado, desplazable y prominente: es la
 *  cabecera del paso. Si la generación sigue en curso, muestra la `salida` parcial tal cual
 *  (sin sondeo en vivo: el detalle se lee una vez al abrir). */
function ProcesoAgente({ gen, titulo = "Proceso del agente (Claude)" }: { gen: PipelineGeneracion; titulo?: string }) {
  const enCurso = gen.estado === "ejecutando";
  const salida = gen.salida.trim();
  const prompt = (gen.prompt ?? "").trim();
  return (
    <div className="space-y-1.5 rounded-md border bg-muted/30 p-2.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-foreground">{titulo}</span>
        <ChipEstado estado={enCurso ? "en_curso" : gen.estado === "error" ? "fallo" : "ok"} />
        <span className="text-xs text-muted-foreground">{faseTexto(gen)}</span>
      </div>
      {/* PROMPT enviado a la IA (plegado por defecto: suele ser largo). */}
      {prompt && (
        <details className="rounded bg-background/60">
          <summary className="cursor-pointer select-none px-2 py-1 text-[11px] font-medium text-muted-foreground hover:text-foreground">
            Ver prompt enviado a la IA
          </summary>
          <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap break-words border-t px-2 py-2 font-mono text-[11px] leading-relaxed text-foreground/80">
            {prompt}
          </pre>
        </details>
      )}
      {/* RAZONAMIENTO + RESULTADO: el stream token a token del agente (lo que pensó y produjo). */}
      <div className="text-[11px] font-medium text-muted-foreground">Razonamiento + resultado</div>
      {salida ? (
        <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded bg-background/60 p-2 font-mono text-[11px] leading-relaxed text-foreground/90">
          {salida}
        </pre>
      ) : (
        <p className="text-xs italic text-muted-foreground">
          {enCurso ? "El agente está arrancando…" : "Sin proceso registrado para esta etapa."}
        </p>
      )}
    </div>
  );
}

/** Contenido COMPLETO específico de cada etapa (lo que ocurrió de verdad). */
function ContenidoEtapa({
  clave,
  run,
  generacion,
}: {
  clave: string;
  run: Pipeline;
  generacion?: PipelineGeneracion;
}) {
  if (clave === "jerarquia") {
    // Paso de IA del POOL de noticias: dedup/fusión (Haiku) + ranking por score. Mostramos las
    // señales reales de la historia y, si existe, el PROCESO Haiku real del pool para esa marca.
    return (
      <div className="space-y-3 text-xs">
        {run.cluster ? (
          <div className="space-y-2">
            <p className="text-muted-foreground">
              La IA del pool de noticias deduplicó (fusión semántica) y jerarquizó esta historia
              antes de crear el tema. Estas son las señales que usó:
            </p>
            <ProcedenciaIA cluster={run.cluster} />
          </div>
        ) : (
          <p className="text-muted-foreground">
            Este tema no nació de una historia rankeada (creado a mano o antes del ranking por IA).
          </p>
        )}
        {generacion && (
          <div className="space-y-1">
            <p className="text-[11px] text-muted-foreground">
              IA del pool (Haiku) para esta marca — a nivel de LOTE de la fusión/encaje, no
              exclusivo de esta pieza:
            </p>
            <ProcesoAgente gen={generacion} titulo="IA del pool (Haiku)" />
          </div>
        )}
      </div>
    );
  }
  if (clave === "ci") {
    return (
      <div className="space-y-1 text-xs text-muted-foreground">
        <p><span className="font-medium text-foreground">Tema:</span> {run.titulo}</p>
        {run.origen && <p><span className="font-medium text-foreground">Origen:</span> {run.origen}</p>}
        {run.descripcion && <p className="line-clamp-3">{run.descripcion}</p>}
      </div>
    );
  }
  if (clave === "cd") {
    return (
      <div className="space-y-3">
        {/* Headline: el proceso de pensamiento del agente que generó el copy. */}
        {generacion && <ProcesoAgente gen={generacion} />}
        {/* Secundario: el resultado (copy + placa) que produjo. */}
        {run.piezas.map((p, i) => (
          <div key={`${p.red}-${i}`} className="rounded-md border p-2">
            <div className="mb-1 flex items-center gap-2">
              <span className="text-xs font-semibold">{p.red_nombre}</span>
              {p.copy_in && <Badge variant="outline" className="text-[10px]">placa: {p.copy_in}</Badge>}
            </div>
            {p.copy ? (
              <p className="whitespace-pre-wrap text-xs text-foreground/90">{p.copy}</p>
            ) : (
              <p className="text-xs italic text-muted-foreground">Sin copy todavía.</p>
            )}
            {p.imagen_url && (
              <img
                src={p.imagen_url}
                alt={`Placa ${p.red_nombre}`}
                loading="lazy"
                className="mt-2 h-24 w-24 rounded border object-cover"
              />
            )}
          </div>
        ))}
      </div>
    );
  }
  if (clave === "qa") {
    // Criba de la FUENTE (pre-copy, por tema): veredicto estructurado + hallazgos, NO por pieza.
    const qa = run.qa_fuente;
    return (
      <div className="space-y-2">
        {/* Headline: el proceso de pensamiento del agente que cribó la nota de origen. */}
        {generacion && <ProcesoAgente gen={generacion} />}
        {qa && (qa.no_verificado || qa.problema) ? (
          <div className="space-y-2 rounded-md border p-2">
            <div className="flex flex-wrap items-center gap-2">
              <BadgeQaFuente qa={qa} />
              {qa.copy_omitido && (
                <span className="text-xs text-muted-foreground">
                  Copy omitido: no se gastó generación en una fuente con problemas.
                </span>
              )}
            </div>
            {qa.resumen && <p className="text-xs text-foreground/90">{qa.resumen}</p>}
            <ListaHallazgos hallazgos={qa.hallazgos} />
            {qa.no_verificado && qa.hallazgos.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Sin hallazgos de peso: la fuente es apta, pero no se verificó a fondo.
              </p>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Criba de la fuente aún sin resolver.</p>
        )}
      </div>
    );
  }
  // aprobacion
  return (
    <div className="space-y-2">
      {run.piezas.map((p, i) => (
        <div key={`${p.red}-${i}`} className="flex items-center justify-between gap-2 rounded-md border p-2 text-xs">
          <span className="font-semibold">{p.red_nombre}</span>
          <div className="flex flex-col items-end gap-0.5 text-muted-foreground">
            <Badge variant="outline">{p.estado}</Badge>
            {p.revisor_nombre && <span>Revisó: {p.revisor_nombre} · {tiempoRelativo(p.revisado_en || "")}</span>}
            {!p.revisor_nombre && p.enviado_a_revision_en && (
              <span>En revisión {tiempoRelativo(p.enviado_a_revision_en)}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Panel INDEPENDIENTE y plegable de una etapa: cabecera siempre visible (nombre + estado)
 *  y, al desplegar, el detalle COMPLETO de lo ocurrido en ese paso. Cada panel se abre/cierra
 *  por su cuenta (estado local propio). */
function PanelEtapa({
  etapa,
  run,
  eventos,
  generacion,
  defaultOpen,
}: {
  etapa: PipelineEtapa;
  run: Pipeline;
  eventos: PipelineActividad[];
  generacion?: PipelineGeneracion;
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
          <ChipEstado estado={etapa.estado} />
        </span>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div className="space-y-3 border-t p-3">
          <p className="text-xs text-muted-foreground">{etapa.detalle}</p>
          <EventosEtapa eventos={eventos} />
          <ContenidoEtapa clave={etapa.clave} run={run} generacion={generacion} />
        </div>
      )}
    </div>
  );
}

function DetalleRun({ id, onCerrar }: { id: string | null; onCerrar: () => void }) {
  const q = useQuery({
    queryKey: ["pipelines", "detalle", id],
    queryFn: ({ signal }) => api.pipelineDetalle(id as string, signal),
    enabled: !!id,
  });
  const datos = q.data as RespuestaPipelineDetalle | undefined;
  const run = datos?.pipeline;
  const eventosDe = (clave: string): PipelineActividad[] => {
    const cod = ETAPA_A_EVENTO[clave];
    return cod && datos ? datos.actividad.filter((e) => e.etapa === cod) : [];
  };
  // Stream del agente (`claude -p`) de la etapa, si la run lo correlacionó (CD/QA).
  const generacionDe = (clave: string): PipelineGeneracion | undefined => {
    const cod = ETAPA_A_EVENTO[clave];
    return cod ? datos?.generaciones_por_etapa?.[cod] : undefined;
  };

  return (
    <Dialog open={!!id} onOpenChange={(o) => { if (!o) onCerrar(); }}>
      <DialogContent className="max-h-[85vh] w-full overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="pr-6 text-base">{run?.titulo ?? "Pipeline"}</DialogTitle>
          <DialogDescription>
            {run ? `${run.marca_nombre} · ${tiempoRelativo(run.creado)}` : "Cargando…"}
          </DialogDescription>
        </DialogHeader>

        {q.isPending ? (
          <div className="space-y-3 py-4">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : q.isError || !run ? (
          <BloqueError
            titulo="No se pudo cargar el pipeline"
            mensaje={q.error instanceof ApiError ? q.error.message : "Inténtalo de nuevo."}
            onReintentar={() => q.refetch()}
          />
        ) : (
          <div className="space-y-2 py-4">
            {run.etapas.map((e, i) => (
              <PanelEtapa
                key={e.clave}
                etapa={e}
                run={run}
                eventos={eventosDe(e.clave)}
                generacion={generacionDe(e.clave)}
                // Abre por defecto la PRIMERA etapa no completada (donde está la acción);
                // si todas están ok, abre la última (Aprobación). El resto, plegadas.
                defaultOpen={
                  i === (run.etapas.findIndex((x) => x.estado !== "ok") + run.etapas.length) % run.etapas.length
                }
              />
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function Pipelines() {
  // Deep-link `?run=<id>`: el feed enlaza aquí para abrir el proceso IA de una pieza. La run
  // abierta vive en la URL (compartible/navegable); al cerrar, se limpia el parámetro.
  const [params, setParams] = useSearchParams();
  const runParam = params.get("run");
  const [abierto, setAbierto] = React.useState<string | null>(runParam);
  React.useEffect(() => {
    if (runParam) setAbierto(runParam);
  }, [runParam]);
  const cerrar = React.useCallback(() => {
    setAbierto(null);
    if (params.has("run")) {
      params.delete("run");
      setParams(params, { replace: true });
    }
  }, [params, setParams]);
  // La vista respeta el switch global de marca de la barra superior (no tiene selector
  // propio). `marcaActiva` es el id canónico (o null = "Todas", solo admin) que el back
  // valida; null → sin filtro de marca.
  const { marcaActiva } = useMarcaActiva();
  // Filtros (etapa donde está parada / estado global) y paginación incremental.
  const [etapa, setEtapa] = React.useState("");
  const [estado, setEstado] = React.useState("");
  const [paginas, setPaginas] = React.useState(1);
  // Al cambiar un filtro (o la marca activa), volvemos a la 1ª página.
  React.useEffect(() => { setPaginas(1); }, [etapa, estado, marcaActiva]);

  const q = useQuery({
    queryKey: ["pipelines", "lista", marcaActiva ?? "todas", etapa, estado, paginas],
    queryFn: ({ signal }) =>
      api.pipelines(
        { marca: marcaActiva ?? undefined, etapa, estado, limite: paginas * PAGINA },
        signal,
      ),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,  // no parpadea al «Cargar más» ni al cambiar de filtro
  });
  const datos = q.data as RespuestaPipelines | undefined;
  const runs = datos?.pipelines ?? [];
  const total = datos?.paginacion?.total ?? runs.length;
  const hayFiltro = !!(etapa || estado);

  return (
    <div className="space-y-5">
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu icono={RefreshCw} onClick={() => q.refetch()} disabled={q.isFetching}>
            Actualizar
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* Filtros: por la etapa donde está parada la run y por su estado global. */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={etapa || "todas"} onValueChange={(v) => setEtapa(v === "todas" ? "" : v)}>
          <SelectTrigger className="h-9 w-[200px]"><SelectValue placeholder="Etapa" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas las etapas</SelectItem>
            {ETAPAS_FILTRO.map((e) => (
              <SelectItem key={e.clave} value={e.clave}>{e.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={estado || "todos"} onValueChange={(v) => setEstado(v === "todos" ? "" : v)}>
          <SelectTrigger className="h-9 w-[170px]"><SelectValue placeholder="Estado" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Cualquier estado</SelectItem>
            {ESTADOS_FILTRO.map((e) => (
              <SelectItem key={e.clave} value={e.clave}>{e.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hayFiltro && (
          <Button variant="ghost" size="sm" onClick={() => { setEtapa(""); setEstado(""); }}>
            Limpiar
          </Button>
        )}
        {!q.isPending && (
          <span className="ml-auto text-xs text-muted-foreground">
            {total} {total === 1 ? "run" : "runs"}{hayFiltro ? " (filtrado)" : ""}
          </span>
        )}
      </div>

      {q.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
      ) : q.isError ? (
        <BloqueError
          titulo="No se pudieron cargar los pipelines"
          mensaje={q.error instanceof ApiError ? q.error.message : "Inténtalo de nuevo."}
          onReintentar={() => q.refetch()}
          cargando={q.isFetching}
        />
      ) : runs.length === 0 ? (
        <EstadoVacio
          icono={GitBranch}
          titulo={hayFiltro ? "Sin runs con ese filtro" : "Aún no hay pipelines"}
          texto={
            hayFiltro
              ? "Ninguna run coincide con la etapa/estado elegidos. Prueba a quitar el filtro."
              : "Cuando el pipeline automático ingiera temas (RSS/tendencias), cada pieza aparecerá aquí con sus etapas. Actívalo con KENI_PIPELINE."
          }
        />
      ) : (
        <>
          <div className="space-y-3">
            {runs.map((run) => (
              <FilaPipeline key={run.id} run={run} onAbrir={setAbierto} />
            ))}
          </div>
          {runs.length < total && (
            <div className="flex justify-center pt-1">
              <Button
                variant="outline"
                onClick={() => setPaginas((p) => p + 1)}
                disabled={q.isFetching}
              >
                {q.isFetching ? "Cargando…" : `Cargar más (${runs.length} de ${total})`}
              </Button>
            </div>
          )}
        </>
      )}

      <DetalleRun id={abierto} onCerrar={cerrar} />
    </div>
  );
}
