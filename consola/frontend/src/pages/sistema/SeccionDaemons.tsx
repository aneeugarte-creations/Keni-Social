import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ExternalLink, Play } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { EstadoDaemon, LatidoDaemon } from "@/types";

import { INTERVALO_RECURSOS_MS } from "./lib";

/** Orden de severidad para listar primero lo que requiere atención. */
const PESO_ESTADO: Record<EstadoDaemon, number> = {
  atrasado: 0,
  error: 1,
  ok: 2,
  inactivo: 3,
};

const ETIQUETA_ESTADO: Record<EstadoDaemon, string> = {
  ok: "OK",
  error: "Error",
  // «Inactivo» se pinta como lo que ES: el gate del daemon está apagado por su ajuste
  // (mismo lenguaje que el 409 de «Barrer ahora»), no un fallo.
  inactivo: "Apagado por ajuste",
  atrasado: "Atrasado",
};

/** Chip de estado con color semántico (verde/rojo/gris/ámbar). */
function ChipEstado({ estado }: { estado: EstadoDaemon }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-transparent",
        estado === "ok" && "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
        estado === "error" && "bg-red-500/15 text-red-600 dark:text-red-400",
        estado === "atrasado" && "bg-amber-500/15 text-amber-600 dark:text-amber-400",
        estado === "inactivo" && "bg-muted text-muted-foreground",
      )}
    >
      {ETIQUETA_ESTADO[estado]}
    </Badge>
  );
}

/** Intervalo legible ("90 s", "15 min", "4 h"). */
function formatoIntervalo(seg: number): string {
  if (!seg) return "—";
  if (seg < 90) return `${Math.round(seg)} s`;
  if (seg < 5400) return `${Math.round(seg / 60)} min`;
  return `${Math.round(seg / 3600)} h`;
}

function FilaDaemon({
  latido,
  onBarrer,
  barriendo,
}: {
  latido: LatidoDaemon;
  onBarrer: (daemon: string) => void;
  /** Daemon cuya solicitud de barrido está en vuelo (deshabilita SOLO su botón). */
  barriendo: string | null;
}) {
  const barrido = latido.ultimo_barrido
    ? tiempoRelativo(latido.ultimo_barrido)
    : "nunca";
  const solicitado = latido.barrido_solicitado !== "";
  return (
    <TableRow>
      <TableCell className="font-medium">{latido.daemon}</TableCell>
      <TableCell>
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <ChipEstado estado={latido.estado} />
          {/* Solicitud de barrido forzado pendiente (campo `barrido_solicitado`): el bucle
              del daemon la consume en su siguiente tick (<= ~1 min). */}
          {solicitado && (
            <Badge
              variant="outline"
              className="border-transparent bg-sky-500/15 text-sky-600 dark:text-sky-400"
              title="El daemon barrerá en su siguiente tick (≤ ~1 min)."
            >
              Barrido solicitado
            </Badge>
          )}
        </span>
      </TableCell>
      <TableCell className="text-muted-foreground">
        {barrido}
        {latido.ultimo_barrido && latido.duracion_ms > 0 && (
          <span className="text-muted-foreground/70"> · {latido.duracion_ms} ms</span>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {formatoIntervalo(latido.intervalo_seg)}
      </TableCell>
      <TableCell className="tabular-nums text-muted-foreground">
        {latido.barridos}
        {latido.errores > 0 && (
          <span className="text-red-500"> ({latido.errores} err)</span>
        )}
      </TableCell>
      <TableCell
        className="max-w-[28ch] truncate text-xs text-muted-foreground"
        title={latido.error_txt || undefined}
      >
        {latido.estado === "error" || latido.errores > 0 ? latido.error_txt : ""}
      </TableCell>
      <TableCell className="text-right">
        {/* Solo a los daemons BARRIBLES (bucle sobre `bucle_gateado`): los legados
            (programador/metricas/…) no miran el flag y el botón sería mentira. */}
        {latido.barrible && (
          <Button
            variant="ghost"
            size="sm"
            disabled={barriendo === latido.daemon || solicitado}
            title={
              solicitado
                ? "Ya hay un barrido solicitado pendiente."
                : "Fuerza un barrido inmediato (sin esperar al intervalo)."
            }
            onClick={() => onBarrer(latido.daemon)}
          >
            <Play className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Barrer ahora
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

/**
 * Sección de daemons de fondo del panel Sistema: estado de cada daemon a partir de sus
 * latidos persistidos (`/api/sistema/daemons`). Lo que requiere atención (atrasado/error)
 * se lista primero. Auto-refresco con la misma cadencia que los recursos. La página entera
 * es de admin (403 si no), así que «Barrer ahora» (POST …/barrer) se ofrece directamente
 * a los daemons `barrible`.
 */
export function SeccionDaemons() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["sistema", "daemons"],
    queryFn: ({ signal }) => api.sistemaDaemons(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });

  const barrer = useMutation({
    mutationFn: (daemon: string) => api.sistemaDaemonBarrer(daemon),
    onSuccess: (r) => {
      toast.success(`Barrido de «${r.daemon}» solicitado: correrá en su siguiente tick.`);
      // Refresca la tabla para que el chip «Barrido solicitado» aparezca al instante.
      void queryClient.invalidateQueries({ queryKey: ["sistema", "daemons"] });
    },
    onError: (e, daemon) => {
      if (e instanceof ApiError && e.status === 409) {
        toast.error(`«${daemon}» está apagado por su ajuste: enciéndelo antes de barrer.`);
      } else if (e instanceof ApiError && e.status === 404) {
        toast.error(`No hay ningún daemon registrado con el nombre «${daemon}».`);
        void queryClient.invalidateQueries({ queryKey: ["sistema", "daemons"] });
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  if (query.isPending) {
    return <Skeleton className="h-48 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer el estado de los daemons"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { daemons, error } = query.data;
  const ordenados = [...daemons].sort(
    (a, b) =>
      PESO_ESTADO[a.estado] - PESO_ESTADO[b.estado] ||
      a.daemon.localeCompare(b.daemon, "es"),
  );

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <Activity className="h-4 w-4" aria-hidden="true" />
          Daemons de fondo
          {/* Aquí se OBSERVA la salud (latidos persistidos) y se puede forzar un barrido;
              el encendido/apagado son ajustes y viven en el Monitor (tira del pipeline +
              panel de ajustes). Un solo sitio para cada cosa. */}
          <Link
            to="/datos/produccion/monitor?tab=ajustes"
            className="ml-auto inline-flex items-center gap-1 text-xs font-normal underline-offset-2 hover:text-foreground hover:underline"
          >
            Ajustes
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </Link>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {error ? (
          <p className="text-sm text-muted-foreground">{error}</p>
        ) : ordenados.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No hay latidos registrados aún (proceso sin iniciar o recién desplegado).
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Daemon</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Último barrido</TableHead>
                <TableHead>Intervalo</TableHead>
                <TableHead>Barridos</TableHead>
                <TableHead>Último error</TableHead>
                <TableHead className="text-right">Acción</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ordenados.map((l) => (
                <FilaDaemon
                  key={l.daemon}
                  latido={l}
                  onBarrer={(d) => barrer.mutate(d)}
                  barriendo={barrer.isPending ? (barrer.variables ?? null) : null}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
