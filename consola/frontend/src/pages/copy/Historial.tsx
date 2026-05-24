import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Clock, History as HistoryIcon } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { EntradaHistorial } from "@/types";

/** Formatea una fecha ISO a algo legible en es-MX; tolera valores no-ISO. */
function formatearFecha(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-MX", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Esqueleto de carga para la lista de historial. */
function EsqueletoHistorial() {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="space-y-2 rounded-md p-3">
          <Skeleton className="h-4 w-44" />
          <Skeleton className="h-3 w-full" />
        </div>
      ))}
    </div>
  );
}

/** Una fila clicable del historial. */
function FilaHistorial({
  entrada,
  onAbrir,
}: {
  entrada: EntradaHistorial;
  onAbrir: (id: string) => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onAbrir(entrada.id)}
        className="w-full rounded-md px-4 py-3 text-left transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{entrada.skill_nombre}</span>
          <Badge variant="secondary">{entrada.marca_nombre}</Badge>
          <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {formatearFecha(entrada.fecha)}
          </span>
        </div>
        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{entrada.preview}</p>
      </button>
    </li>
  );
}

/**
 * Lista del historial de generaciones. Cada entrada abre un Dialog con el
 * resultado completo (cargado bajo demanda con `api.detalleHistorial`).
 */
export function Historial() {
  const [abiertoId, setAbiertoId] = React.useState<string | null>(null);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["skills", "historial"],
    queryFn: ({ signal }) => api.historial(signal),
  });

  const detalle = useQuery({
    queryKey: ["skills", "historial", abiertoId],
    queryFn: ({ signal }) => api.detalleHistorial(abiertoId as string, signal),
    enabled: abiertoId !== null,
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <HistoryIcon className="h-4 w-4 text-muted-foreground" />
          Historial
        </CardTitle>
      </CardHeader>
      <CardContent className="p-2">
        {isPending ? (
          <EsqueletoHistorial />
        ) : isError ? (
          <div className="flex items-start gap-2 px-3 py-4 text-sm text-muted-foreground">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <span>
              {error instanceof Error ? error.message : "No se pudo cargar el historial."}
            </span>
          </div>
        ) : data.historial.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">
            Aún no has generado nada. Tus borradores aparecerán aquí.
          </p>
        ) : (
          <ul className="space-y-1">
            {data.historial.map((entrada) => (
              <FilaHistorial key={entrada.id} entrada={entrada} onAbrir={setAbiertoId} />
            ))}
          </ul>
        )}
      </CardContent>

      <Dialog open={abiertoId !== null} onOpenChange={(open) => !open && setAbiertoId(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Borrador del historial</DialogTitle>
            <DialogDescription>
              Resultado completo de una generación anterior. Es un borrador, no se publica.
            </DialogDescription>
          </DialogHeader>
          {detalle.isPending ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-4/6" />
            </div>
          ) : detalle.isError ? (
            <p className="flex items-start gap-2 text-sm text-muted-foreground">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              {detalle.error instanceof Error
                ? detalle.error.message
                : "No se pudo cargar el detalle."}
            </p>
          ) : (
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/40 p-4 text-sm leading-relaxed">
              {detalle.data?.resultado}
            </pre>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
