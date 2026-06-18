import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Coins,
  GitBranch,
  Hammer,
  Loader2,
  MessageSquareWarning,
  Rocket,
  Search,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ChipEstado } from "@/components/comunes/ChipEstado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Markdown } from "@/components/ui/Markdown";
import { Textarea } from "@/components/ui/textarea";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, mensajeError } from "@/lib/api";
import { costeUsd } from "@/lib/formato";
import { cn } from "@/lib/utils";
import type { AccionCheckpoint, Sugerencia } from "@/types";

import {
  CATEGORIA_LABEL,
  CLAVE_SUGERENCIAS,
  COMPLEJIDAD_LABEL,
  COMPLEJIDAD_VARIANTE,
  ESTADO_LABEL,
  ESTADO_VARIANTE,
  etiqueta,
} from "./columnas";

/** Sigue EN VIVO la generación en curso de una pieza (SSE con fallback a sondeo). */
function StreamGeneracion({ genId }: { genId: string }) {
  const seg = useGeneracion();
  const { iniciar, limpiar } = seg;

  React.useEffect(() => {
    let vivo = true;
    if (!genId) {
      limpiar();
      return;
    }
    api
      .generacion(genId)
      .then((r) => {
        if (vivo) iniciar(r.generacion);
      })
      .catch(() => {
        /* El detalle converge igual cuando la fila se refresca. */
      });
    return () => {
      vivo = false;
    };
  }, [genId, iniciar, limpiar]);

  const gen = seg.generacion;
  if (!gen) return null;
  const salida = (gen.salida ?? "").trim();
  const razon = (gen.razonamiento ?? "").trim();

  return (
    <div className="space-y-2 rounded-md border border-violet-500/20 bg-violet-500/5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold">Generación en vivo</span>
        <ChipEstado
          estado={seg.ejecutando ? "en_curso" : gen.estado === "error" ? "fallo" : "ok"}
        />
        {gen.metricas?.total_cost_usd != null && (
          <Badge variant="outline" className="gap-1 text-[10px] tabular-nums">
            <Coins className="h-2.5 w-2.5" aria-hidden="true" />
            {costeUsd(gen.metricas.total_cost_usd)}
          </Badge>
        )}
      </div>
      {razon && (
        <div className="max-h-48 overflow-y-auto rounded bg-background/60 p-2">
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">Razonamiento</div>
          <Markdown className="text-xs text-foreground/70">{razon}</Markdown>
        </div>
      )}
      <div className="max-h-72 overflow-y-auto rounded bg-background/60 p-2">
        {salida ? (
          <Markdown className="text-xs text-foreground/90">{salida}</Markdown>
        ) : (
          <p className="text-xs italic text-muted-foreground">
            {seg.ejecutando ? "En curso…" : "Sin salida."}
          </p>
        )}
      </div>
    </div>
  );
}

/** Sección plegable de markdown (spec / plan). Nada si vacía. */
function BloqueMarkdown({ titulo, texto }: { titulo: string; texto: string }) {
  if (!texto.trim()) return null;
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-semibold text-muted-foreground">{titulo}</div>
      <div className="max-h-80 overflow-y-auto rounded-md border bg-muted/20 p-3">
        <Markdown className="text-sm text-foreground/90">{texto}</Markdown>
      </div>
    </div>
  );
}

export function DetalleSugerencia({
  sugerencia,
  onClose,
}: {
  sugerencia: Sugerencia | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [comentario, setComentario] = React.useState("");

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });

  const id = sugerencia?.id ?? "";

  const discovery = useMutation({
    mutationFn: () => api.discoverySugerencia(id),
    onSuccess: () => {
      invalidar();
      toast.success("Discovery lanzado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const construir = useMutation({
    mutationFn: () => api.construirSugerencia(id),
    onSuccess: () => {
      invalidar();
      toast.success("En cola para construir");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const checkpoint = useMutation({
    mutationFn: (accion: AccionCheckpoint) =>
      api.checkpointSugerencia(id, accion, comentario.trim() || undefined),
    onSuccess: (_res, accion) => {
      invalidar();
      setComentario("");
      toast.success(
        accion === "continuar"
          ? "Checkpoint aprobado"
          : accion === "cambios"
            ? "Cambios solicitados"
            : "Pieza cancelada",
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const promover = useMutation({
    mutationFn: () => api.promoverSugerencia(id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res.detalle || "Promovida a main");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descartar = useMutation({
    mutationFn: () => api.actualizarSugerencia(id, { estado: "descartada" }),
    onSuccess: () => {
      invalidar();
      toast.success("Descartada");
      onClose();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (!sugerencia) return null;

  const ocupado =
    discovery.isPending ||
    construir.isPending ||
    checkpoint.isPending ||
    promover.isPending ||
    descartar.isPending;

  const estado = sugerencia.estado;
  const enRevision = estado === "revision";

  return (
    <Dialog open={!!sugerencia} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="pr-6">{sugerencia.titulo}</DialogTitle>
          <DialogDescription className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="font-normal">
              {etiqueta(CATEGORIA_LABEL, sugerencia.categoria)}
            </Badge>
            <Badge
              variant={ESTADO_VARIANTE[estado] ?? "secondary"}
              className="font-normal"
            >
              {etiqueta(ESTADO_LABEL, estado)}
            </Badge>
            {sugerencia.complejidad && (
              <Badge
                variant={COMPLEJIDAD_VARIANTE[sugerencia.complejidad] ?? "outline"}
                className="font-normal"
              >
                {etiqueta(COMPLEJIDAD_LABEL, sugerencia.complejidad)}
              </Badge>
            )}
            {sugerencia.fase && (
              <Badge variant="outline" className="font-normal">
                fase: {sugerencia.fase}
              </Badge>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {sugerencia.detalle && (
            <Markdown className="text-sm text-muted-foreground">{sugerencia.detalle}</Markdown>
          )}

          {(sugerencia.rama || sugerencia.coste_usd > 0) && (
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              {sugerencia.rama && (
                <span className="flex items-center gap-1">
                  <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
                  {sugerencia.rama}
                </span>
              )}
              {sugerencia.coste_usd > 0 && (
                <span className="flex items-center gap-1 tabular-nums">
                  <Coins className="h-3.5 w-3.5" aria-hidden="true" />
                  {costeUsd(sugerencia.coste_usd)} acumulado
                </span>
              )}
            </div>
          )}

          {sugerencia.gen_id && <StreamGeneracion genId={sugerencia.gen_id} />}

          <BloqueMarkdown titulo="Spec (discovery)" texto={sugerencia.spec} />
          <BloqueMarkdown titulo="Plan" texto={sugerencia.plan} />
          <BloqueMarkdown titulo="Diff" texto={sugerencia.diff_resumen} />

          {enRevision && (
            <Textarea
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
              placeholder="Comentario para «Pedir cambios» (opcional)…"
              rows={3}
              maxLength={4000}
            />
          )}
        </div>

        <div className={cn("flex flex-wrap items-center justify-end gap-2")}>
          {(estado === "nueva" || estado === "fallida") && (
            <Button
              variant="outline"
              onClick={() => discovery.mutate()}
              disabled={ocupado}
            >
              {discovery.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Lanzar discovery
            </Button>
          )}
          {(estado === "nueva" || estado === "discovery" || estado === "fallida") && (
            <Button onClick={() => construir.mutate()} disabled={ocupado}>
              {construir.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Hammer className="h-4 w-4" />
              )}
              Construir
            </Button>
          )}
          {enRevision && (
            <>
              <Button
                variant="outline"
                onClick={() => checkpoint.mutate("cambios")}
                disabled={ocupado}
              >
                <MessageSquareWarning className="h-4 w-4" />
                Pedir cambios
              </Button>
              <Button onClick={() => checkpoint.mutate("continuar")} disabled={ocupado}>
                <CheckCircle2 className="h-4 w-4" />
                Aprobar checkpoint
              </Button>
            </>
          )}
          {(estado === "revision" || estado === "hecha") && (
            <Button onClick={() => promover.mutate()} disabled={ocupado}>
              {promover.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Rocket className="h-4 w-4" />
              )}
              Promover a main
            </Button>
          )}
          {estado !== "descartada" && (
            <Button
              variant="ghost"
              className="text-destructive hover:text-destructive"
              onClick={() => descartar.mutate()}
              disabled={ocupado}
            >
              <Trash2 className="h-4 w-4" />
              Descartar
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
