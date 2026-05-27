import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Clock, ExternalLink, History as HistoryIcon, Loader2, Save } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { DetalleHistorial, EntradaHistorial } from "@/types";

import { iconoRed, nombreRed } from "../publicaciones/meta";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

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

/** Enlace de éxito a Publicaciones que se muestra en el toast. */
function EnlacePublicaciones() {
  return (
    <Link to="/publicaciones" className="inline-flex items-center gap-1 underline">
      Ver en Publicaciones
      <ExternalLink className="h-3 w-3" />
    </Link>
  );
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
          <Autor nombre={entrada.autor_nombre} className="text-xs" />
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
 * Cuerpo del diálogo de detalle: resultado completo + recuperación como
 * publicación(es). Si la entrada tiene piezas, las guarda todas; si no, pide
 * elegir una red antes de guardar (`POST /api/skills/historial/{id}/guardar`).
 */
function DetalleHistorialDialogo({ detalle }: { detalle: DetalleHistorial }) {
  const queryClient = useQueryClient();
  const tienePiezas = detalle.piezas.length > 0;
  const [red, setRed] = React.useState("");

  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: !tienePiezas,
  });
  const redes = opcionesQuery.data?.redes ?? [];

  const guardar = useMutation({
    mutationFn: () =>
      api.guardarHistorial(detalle.id, tienePiezas ? {} : { red }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["publicaciones"] });
      const n = data?.publicaciones?.length ?? 0;
      toast.success(
        `Se ${n === 1 ? "guardó" : "guardaron"} ${n} ${n === 1 ? "publicación" : "publicaciones"}`,
        { description: <EnlacePublicaciones /> },
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar = !guardar.isPending && (tienePiezas || red !== "");

  return (
    <>
      {tienePiezas ? (
        <div className="flex flex-wrap items-center gap-2">
          {detalle.piezas.map((p) => {
            const Icono = iconoRed(p.red);
            return (
              <Badge key={p.red} variant="secondary" className="gap-1.5 font-normal">
                <Icono className="h-3.5 w-3.5" />
                {nombreRed(p.red)}
              </Badge>
            );
          })}
        </div>
      ) : null}

      <pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/40 p-4 text-sm leading-relaxed">
        {detalle.resultado}
      </pre>

      <div className="flex flex-wrap items-end gap-2">
        {!tienePiezas && (
          <div className="space-y-1.5">
            <Label htmlFor="historial-red">Red</Label>
            <Select value={red} onValueChange={setRed}>
              <SelectTrigger id="historial-red" className="w-44">
                <SelectValue placeholder="Elige una red" />
              </SelectTrigger>
              <SelectContent>
                {redes.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {tienePiezas ? "Guardar como publicaciones" : "Guardar como publicación"}
        </Button>
        {!tienePiezas && (
          <p className="text-xs text-muted-foreground">
            Esta entrada no tiene piezas por red: elige una para guardarla.
          </p>
        )}
      </div>
    </>
  );
}

/**
 * Lista del historial de generaciones. Cada entrada abre un Dialog con el
 * resultado completo (cargado bajo demanda con `api.detalleHistorial`) y un
 * botón para recuperarlo como publicación(es).
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
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Borrador del historial</DialogTitle>
            <DialogDescription>
              Resultado completo de una generación anterior. Guárdalo como publicación para
              gestionarlo.
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
          ) : detalle.data ? (
            <DetalleHistorialDialogo detalle={detalle.data} />
          ) : null}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
