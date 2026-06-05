import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarHeart,
  ChevronDown,
  Loader2,
  RefreshCw,
  Repeat,
  Sparkles,
  Sprout,
  TrendingUp,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import { ApiError, api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { FiltrosReciclaje, MotivoReciclaje, SugerenciaReciclaje } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { EtiquetaRed } from "./insignias";
import { tiempoRelativo } from "./meta";

/** Clave de caché de las sugerencias de reciclaje (depende de los filtros). */
export const CLAVE_RECICLAJE = ["reciclaje", "sugerencias"] as const;

/** Capa visual de cada motivo (icono + etiqueta + color del badge). */
const META_MOTIVO: Record<
  MotivoReciclaje,
  { etiqueta: string; icono: typeof Sparkles; clase: string }
> = {
  rendimiento: {
    etiqueta: "Rindió bien",
    icono: TrendingUp,
    clase: "border-amber-500/40 text-amber-700 dark:text-amber-300",
  },
  efemeride: {
    etiqueta: "Efeméride",
    icono: CalendarHeart,
    clase: "border-fuchsia-500/40 text-fuchsia-700 dark:text-fuchsia-300",
  },
  perenne: {
    etiqueta: "Perenne",
    icono: Sprout,
    clase: "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
  },
  recurrente: {
    etiqueta: "Vuelve a circular",
    icono: Repeat,
    clase: "border-sky-500/40 text-sky-700 dark:text-sky-300",
  },
};

/** Una fila de sugerencia: la pieza, su motivo y el botón de reciclar. */
function FilaSugerencia({
  sugerencia,
  onReciclar,
  reciclando,
}: {
  sugerencia: SugerenciaReciclaje;
  onReciclar: (id: string) => void;
  reciclando: boolean;
}) {
  const meta = META_MOTIVO[sugerencia.motivo];
  const Icono = meta?.icono ?? Sparkles;
  // Fila clicable entera = reciclar (la única acción primaria de la fila). La guarda evita
  // que un click sobre el propio botón "Reciclar" la dispare dos veces.
  function alClick(e: React.MouseEvent) {
    if (reciclando) return;
    const t = e.target as HTMLElement;
    if (
      t.closest(
        "button, a, input, select, textarea, label, [role='button'], [role='menuitem'], [data-no-primaria]",
      )
    )
      return;
    onReciclar(sugerencia.id);
  }
  return (
    <div
      onClick={alClick}
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-border/60 bg-background/60 p-3 transition-colors hover:bg-accent/40 sm:flex-row sm:items-start sm:justify-between",
        reciclando ? "cursor-default" : "cursor-pointer",
      )}
    >
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-medium">{sugerencia.titulo || "(sin título)"}</span>
          <Badge variant="outline" className={cn("gap-1 font-normal", meta?.clase)}>
            <Icono className="h-3 w-3" />
            {meta?.etiqueta ?? sugerencia.motivo}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <EtiquetaRed red={sugerencia.red} nombre={sugerencia.red_nombre} />
          <span>· {sugerencia.marca_nombre}</span>
          {sugerencia.fecha_creacion && (
            <span>· publicado {tiempoRelativo(sugerencia.fecha_creacion)}</span>
          )}
          {sugerencia.rendimiento?.encontrado && (
            <span className="font-medium text-amber-700 dark:text-amber-300">
              · {sugerencia.rendimiento.engagement_pct.toFixed(1)}% engagement
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{sugerencia.motivo_detalle}</p>
      </div>
      <Tooltip label="Reciclar (volver a publicar)">
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => onReciclar(sugerencia.id)}
          disabled={reciclando}
          aria-label={`Reciclar ${sugerencia.titulo}`}
        >
          {reciclando ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Reciclar
        </Button>
      </Tooltip>
    </div>
  );
}

/**
 * Panel DISCRETO de reciclaje proactivo (#110).
 *
 * Muestra, plegado por defecto, las piezas de archivo que la heurística del
 * backend (efeméride próxima, perenne madurada o tema recurrente) propone
 * retomar, cada una con su motivo explicable. Al pulsar «Reciclar» dispara el
 * reciclado que YA existe (`api.reciclarPublicacion`), sin lógica nueva: encola
 * la copia si hay franjas o la deja como borrador, e invalida la lista.
 *
 * No estorba cuando no hay candidatas: se oculta por completo.
 */
export function PanelReciclaje({
  filtros,
  onGestionarFranjas,
}: {
  filtros: FiltrosReciclaje;
  onGestionarFranjas: () => void;
}) {
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = React.useState(false);

  const query = useQuery({
    queryKey: [...CLAVE_RECICLAJE, filtros.marca ?? "", filtros.red ?? ""],
    queryFn: ({ signal }) => api.sugerenciasReciclaje(filtros, signal),
  });

  const reciclar = useMutation({
    mutationFn: (id: string) => api.reciclarPublicacion(id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: CLAVE_RECICLAJE });
      toast.success(
        res?.encolado ? "Reciclada y encolada" : "Reciclada como nuevo borrador",
      );
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        toast.error(e.message, {
          action: { label: "Gestionar franjas", onClick: onGestionarFranjas },
        });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const sugerencias = query.data?.sugerencias ?? [];

  // Sin candidatas (o aún cargando la primera vez): el panel no aparece, para no
  // meter ruido en la página de publicaciones.
  if (query.isError) return null;
  if (!query.isPending && sugerencias.length === 0) return null;

  const total = sugerencias.length;

  return (
    <Card className="mb-4 border-primary/20 bg-primary/[0.03]">
      <CardContent className="p-0">
        <button
          type="button"
          onClick={() => setAbierto((v) => !v)}
          aria-expanded={abierto}
          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        >
          <span className="flex items-center gap-2 font-medium">
            <Sparkles className="h-4 w-4 text-primary" />
            Sugerencias para reciclar
            {query.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            ) : (
              <Badge variant="secondary" className="font-normal">
                {total}
              </Badge>
            )}
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              abierto && "rotate-180",
            )}
          />
        </button>

        {abierto && (
          <div className="space-y-2 border-t border-border/60 px-4 py-3">
            <p className="text-sm text-muted-foreground">
              Contenido de archivo que merece retomarse: ya rindió bien en Metricool,
              vuelve a ser relevante por una efeméride próxima, es perenne madurado o su
              tema vuelve a circular.
            </p>
            {sugerencias.map((s) => (
              <FilaSugerencia
                key={s.id}
                sugerencia={s}
                onReciclar={(id) => reciclar.mutate(id)}
                reciclando={reciclar.isPending && reciclar.variables === s.id}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
