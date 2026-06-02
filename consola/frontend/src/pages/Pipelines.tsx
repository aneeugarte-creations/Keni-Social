import { useQuery } from "@tanstack/react-query";
import { GitBranch, RefreshCw } from "lucide-react";
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
  PipelineEtapa,
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
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                e.estado === "ok" && "bg-emerald-500",
                e.estado === "en_curso" && "bg-sky-500 animate-pulse",
                e.estado === "revisar" && "bg-amber-500",
                e.estado === "pendiente" && "bg-muted-foreground/40",
                e.estado === "fallo" && "bg-destructive",
              )}
            />
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

function FilaPipeline({ run, onAbrir }: { run: Pipeline; onAbrir: (id: string) => void }) {
  return (
    <Card className="transition-colors hover:bg-muted/40">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="shrink-0">{run.marca_nombre || run.marca}</Badge>
            <ChipEstado estado={run.estado_global} />
            <span className="truncate text-xs text-muted-foreground">{tiempoRelativo(run.creado)}</span>
          </div>
          <p className="truncate text-sm font-medium" title={run.titulo}>{run.titulo}</p>
          <TiraEtapas etapas={run.etapas} />
        </div>
        <Button variant="ghost" size="sm" className="shrink-0" onClick={() => onAbrir(run.id)}>
          Ver detalle
        </Button>
      </CardContent>
    </Card>
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
  return (
    <Dialog open={!!id} onOpenChange={(o) => { if (!o) onCerrar(); }}>
      <DialogContent className="max-h-[85vh] w-full overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="pr-6 text-base">{run?.titulo ?? "Pipeline"}</DialogTitle>
          <DialogDescription>
            {run ? `${run.marca_nombre} · ${tiempoRelativo(run.creado)}` : "Cargando…"}
          </DialogDescription>
        </DialogHeader>

        {q.isPending ? (
          <div className="space-y-3 py-4">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : q.isError || !run ? (
          <BloqueError
            titulo="No se pudo cargar el pipeline"
            mensaje={q.error instanceof ApiError ? q.error.message : "Inténtalo de nuevo."}
            onReintentar={() => q.refetch()}
          />
        ) : (
          <div className="space-y-5 py-4">
            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase text-muted-foreground">Etapas</h3>
              {run.etapas.map((e) => (
                <div key={e.clave} className="flex items-start justify-between gap-3 rounded-md border p-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{e.nombre}</p>
                    <p className="text-xs text-muted-foreground">{e.detalle}</p>
                  </div>
                  <ChipEstado estado={e.estado} className="shrink-0" />
                </div>
              ))}
            </section>

            {run.piezas.length > 0 && (
              <section className="space-y-2">
                <h3 className="text-xs font-semibold uppercase text-muted-foreground">Piezas por red</h3>
                {run.piezas.map((p, i) => (
                  <div key={`${p.red}-${i}`} className="flex items-center justify-between rounded-md border p-2 text-sm">
                    <span className="font-medium">{p.red_nombre}</span>
                    <div className="flex items-center gap-2">
                      {p.veredicto && <ChipEstado estado={p.veredicto === "listo" ? "ok" : "revisar"} />}
                      <Badge variant="outline">{p.estado}</Badge>
                    </div>
                  </div>
                ))}
              </section>
            )}

            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase text-muted-foreground">Actividad</h3>
              {datos && datos.actividad.length > 0 ? (
                datos.actividad.map((ev, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 rounded-md border p-2 text-xs">
                    <span className="truncate" title={ev.etiqueta}>{ev.etiqueta}</span>
                    <span className="shrink-0 text-muted-foreground">{tiempoRelativo(ev.fecha)}</span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted-foreground">Sin eventos registrados todavía.</p>
              )}
            </section>
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
        descripcion="Cada pieza del pipeline de contenido, etapa a etapa (Ingesta → Copy → Validación → Aprobación), estilo CI/CD."
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
