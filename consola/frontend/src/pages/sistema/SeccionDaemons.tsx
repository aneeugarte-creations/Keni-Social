import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
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
import { api, mensajeError } from "@/lib/api";
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
  inactivo: "Inactivo",
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

function FilaDaemon({ latido }: { latido: LatidoDaemon }) {
  const barrido = latido.ultimo_barrido
    ? tiempoRelativo(latido.ultimo_barrido)
    : "nunca";
  return (
    <TableRow>
      <TableCell className="font-medium">{latido.daemon}</TableCell>
      <TableCell>
        <ChipEstado estado={latido.estado} />
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
    </TableRow>
  );
}

/**
 * Sección de daemons de fondo del panel Sistema: estado de cada daemon a partir de sus
 * latidos persistidos (`/api/sistema/daemons`). Lo que requiere atención (atrasado/error)
 * se lista primero. Auto-refresco con la misma cadencia que los recursos.
 */
export function SeccionDaemons() {
  const query = useQuery({
    queryKey: ["sistema", "daemons"],
    queryFn: ({ signal }) => api.sistemaDaemons(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
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
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {error ? (
          <p className="text-sm text-muted-foreground">{error}</p>
        ) : ordenados.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aún no hay latidos registrados (el proceso de daemons no ha arrancado o
            acaba de desplegarse).
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {ordenados.map((l) => (
                <FilaDaemon key={l.daemon} latido={l} />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
