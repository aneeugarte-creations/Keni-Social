import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, GitBranch, RefreshCw } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import type { BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  Pipeline,
  PipelineActividad,
  PipelineEtapa,
  PipelineGeneracion,
  RespuestaPipelineDetalle,
  RespuestaPipelines,
} from "@/types";

// Estado de etapa/run -> aspecto del badge + etiqueta corta. Mapeo único para toda la
// página (la tira de etapas y el chip de estado global comparten convención GitLab-like).
const ASPECTO: Record<string, { variant: BadgeProps["variant"]; clase: string; texto: string }> = {
  ok: { variant: "secondary", clase: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30", texto: "OK" },
  en_curso: { variant: "secondary", clase: "bg-sky-500/15 text-sky-600 border-sky-500/30", texto: "En curso" },
  revisar: { variant: "secondary", clase: "bg-amber-500/15 text-amber-600 border-amber-500/30", texto: "Revisar" },
  pendiente: { variant: "outline", clase: "text-muted-foreground", texto: "Pendiente" },
  fallo: { variant: "destructive", clase: "", texto: "Fallo" },
};

// Etapa (clave) -> código de etapa de los eventos de actividad (la traza CI/CD/QA).
const ETAPA_A_EVENTO: Record<string, string> = { ci: "CI", cd: "CD", qa: "QA" };

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

function Punto({ estado }: { estado: string }) {
  return (
    <span
      className={cn(
        "h-2 w-2 shrink-0 rounded-full",
        estado === "ok" && "bg-emerald-500",
        estado === "en_curso" && "bg-sky-500 animate-pulse",
        estado === "revisar" && "bg-amber-500",
        estado === "pendiente" && "bg-muted-foreground/40",
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
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="shrink-0">{run.marca_nombre || run.marca}</Badge>
            <ChipEstado estado={run.estado_global} />
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
function ProcesoAgente({ gen }: { gen: PipelineGeneracion }) {
  const enCurso = gen.estado === "ejecutando";
  const salida = gen.salida.trim();
  return (
    <div className="space-y-1.5 rounded-md border bg-muted/30 p-2.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-foreground">Proceso del agente (Claude)</span>
        <ChipEstado estado={enCurso ? "en_curso" : gen.estado === "error" ? "fallo" : "ok"} />
        <span className="text-xs text-muted-foreground">{faseTexto(gen)}</span>
      </div>
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
    return (
      <div className="space-y-2">
        {/* Headline: el proceso de pensamiento del agente que revisó el copy (QA editorial). */}
        {generacion && <ProcesoAgente gen={generacion} />}
        {/* Secundario: el veredicto + observaciones por pieza. */}
        {run.piezas.map((p, i) => (
          <div key={`${p.red}-${i}`} className="rounded-md border p-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold">{p.red_nombre}</span>
              {p.veredicto ? (
                <ChipEstado estado={p.veredicto === "listo" ? "ok" : "revisar"} />
              ) : (
                <ChipEstado estado="pendiente" />
              )}
            </div>
            {p.observaciones && p.observaciones.length > 0 ? (
              <ul className="mt-1 list-disc pl-4 text-xs text-amber-600">
                {p.observaciones.map((o, j) => <li key={j}>{o}</li>)}
              </ul>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">Sin observaciones.</p>
            )}
          </div>
        ))}
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
  const [abierto, setAbierto] = React.useState<string | null>(null);
  const q = useQuery({
    queryKey: ["pipelines", "lista"],
    queryFn: ({ signal }) => api.pipelines({ limite: 50 }, signal),
    refetchInterval: 30_000,
  });
  const datos = q.data as RespuestaPipelines | undefined;
  const runs = datos?.pipelines ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        titulo="Pipelines"
        descripcion="Cada pieza del pipeline de contenido, etapa a etapa (Ingesta → Copy → Validación → Aprobación), estilo CI/CD. Haz clic en una tarjeta para ver el detalle de cada paso."
        acciones={
          <Button variant="outline" size="sm" onClick={() => q.refetch()} disabled={q.isFetching}>
            <RefreshCw className={cn("mr-2 h-4 w-4", q.isFetching && "animate-spin")} />
            Actualizar
          </Button>
        }
      />

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
          titulo="Aún no hay pipelines"
          texto="Cuando el pipeline automático ingiera temas (RSS/tendencias), cada pieza aparecerá aquí con sus etapas. Actívalo con KENI_PIPELINE."
        />
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <FilaPipeline key={run.id} run={run} onAbrir={setAbierto} />
          ))}
        </div>
      )}

      <DetalleRun id={abierto} onCerrar={() => setAbierto(null)} />
    </div>
  );
}
