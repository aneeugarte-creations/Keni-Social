/**
 * DetalleHistoria — el panel de una historia: todo lo que la tarjeta resume.
 *
 * Clic en el título de la tarjeta → este diálogo: resumen completo, «¿Por qué rankea
 * así?» (las señales del motor en frases editoriales) y la LÍNEA DE TIEMPO de fuentes —
 * quién la ABRIÓ, quién se fue sumando y cuándo — más los enlaces a los artículos
 * originales. Las acciones del pie reutilizan las mismas mutaciones del pool.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Loader2, Newspaper, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { etiquetaLinea } from "@/lib/lineas";
import { fraseCorroboracion, nivelPrioridad } from "@/lib/noticias/ranking-editorial";
import type { FuenteHistoria, Historia } from "@/types";

import { CalculoScore } from "./CalculoScore";

function horaLocal(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

/** La línea de tiempo de outlets: el primero ABRIÓ la historia. */
export function TimelineFuentes({ fuentes }: { fuentes: FuenteHistoria[] }) {
  if (fuentes.length === 0) {
    return <p className="text-xs text-muted-foreground">Sin línea de tiempo de fuentes todavía.</p>;
  }
  return (
    <ol className="space-y-1.5" data-testid="timeline-fuentes">
      {fuentes.map((f, i) => (
        <li key={`${f.fuente_id}-${i}`} className="flex items-baseline gap-2 text-xs">
          <span className="w-12 shrink-0 tabular-nums text-muted-foreground" title={f.primer_visto}>
            {horaLocal(f.primer_visto)}
          </span>
          <span className="h-2 w-2 shrink-0 self-center rounded-full bg-sky-500" />
          <span className="font-medium">{f.fuente || f.fuente_id}</span>
          {i === 0 && (
            <Badge variant="outline" className="text-[10px] font-normal">
              la abrió
            </Badge>
          )}
          {f.n_items > 1 && (
            <span className="text-muted-foreground">· {f.n_items} notas</span>
          )}
          {f.primer_visto && (
            <span className="ml-auto text-muted-foreground">{tiempoRelativo(f.primer_visto)}</span>
          )}
        </li>
      ))}
    </ol>
  );
}

export function DetalleHistoria({
  historia,
  abierto,
  onCerrar,
  clavesAInvalidar,
}: {
  historia: Historia;
  abierto: boolean;
  onCerrar: () => void;
  clavesAInvalidar: readonly (readonly unknown[])[];
}) {
  const queryClient = useQueryClient();
  const invalidar = () => {
    for (const clave of clavesAInvalidar) {
      void queryClient.invalidateQueries({ queryKey: clave });
    }
  };

  const usarMut = useMutation({
    mutationFn: () => api.noticias.usarHistoria(historia.id, { generar: true }),
    onSuccess: () => {
      invalidar();
      toast.success("Copy en marcha — aparecerá en el Feed para imagen y aprobación.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const descartarMut = useMutation({
    mutationFn: () => api.noticias.descartarHistoria(historia.id),
    onSuccess: () => {
      invalidar();
      toast.success("Historia descartada.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enPool = (historia.pieza_estado ?? "en_pool") === "en_pool" && historia.estado === "nuevo";
  const prioridad = nivelPrioridad(historia.score);

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-y-auto" data-testid="detalle-historia">
        <DialogHeader>
          <DialogTitle className="leading-snug">
            {historia.breaking === 1 && (
              <Badge className="mr-1.5 gap-1 align-middle text-[10px] bg-red-600 hover:bg-red-600 text-white border-0">
                <Zap className="h-3 w-3" />
                ÚLTIMA HORA
              </Badge>
            )}
            {historia.titulo || "(sin título)"}
          </DialogTitle>
          <DialogDescription>
            {etiquetaLinea(historia.breaking === 1 ? "breaking" : historia.categoria)} ·{" "}
            {fraseCorroboracion(historia)} · prioridad {prioridad}
          </DialogDescription>
        </DialogHeader>

        {historia.resumen && <p className="text-sm leading-relaxed">{historia.resumen}</p>}
        {historia.traducido && historia.titulo_original && (
          <p className="text-xs text-muted-foreground">
            Original ({(historia.idioma || "").toUpperCase()}): {historia.titulo_original}
          </p>
        )}

        {/* El porqué + el CÁLCULO, sin caja negra (componente compartido con el pop-up
            del score de la tarjeta). */}
        <CalculoScore historia={historia} />

        <div className="space-y-1.5">
          <h4 className="text-sm font-semibold">Línea de tiempo de fuentes</h4>
          <TimelineFuentes fuentes={historia.fuentes ?? []} />
        </div>

        {historia.enlaces.length > 0 && (
          <div className="space-y-1.5">
            <h4 className="text-sm font-semibold">Artículos</h4>
            <ul className="space-y-1">
              {historia.enlaces.map((e, i) => (
                <li key={i} className="text-xs flex items-start gap-1">
                  <a
                    href={e.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline flex items-center gap-0.5 break-words flex-1 min-w-0"
                  >
                    {e.titulo || e.url}
                    <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                  </a>
                  {e.fuente && <span className="shrink-0 text-muted-foreground">— {e.fuente}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {enPool && (
          <div className="flex justify-end gap-2 pt-1">
            <Button
              variant="outline"
              size="sm"
              className="gap-1 text-destructive hover:text-destructive"
              onClick={() => descartarMut.mutate()}
              disabled={usarMut.isPending || descartarMut.isPending}
            >
              {descartarMut.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Trash2 className="h-3 w-3" />
              )}
              Descartar
            </Button>
            <Button
              size="sm"
              className="gap-1"
              onClick={() => usarMut.mutate()}
              disabled={usarMut.isPending || descartarMut.isPending}
            >
              {usarMut.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Newspaper className="h-3 w-3" />
              )}
              Pasar al feed
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
