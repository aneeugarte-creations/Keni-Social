/**
 * LogBarridos — tabla del LOG por barrido de un daemon (`GET /api/sistema/daemons/{daemon}/barridos`,
 * nuevo primero): cada iteración del bucle con su hora, resultado (OK/Error), duración y resumen.
 *
 * Reutilizable: lo pinta el detalle de un daemon (AgenteDetalle) y la subpágina de una fase del
 * pipeline cuyos logs son los barridos de un daemon (p. ej. Google Trends → daemon `trends`).
 */
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, FileText, XCircle } from "lucide-react";

import { BloqueError } from "@/components/comunes/BloqueError";
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
import { formatearFechaHora, tiempoRelativo } from "@/lib/fecha";
import { duracion } from "@/lib/formato";
import { INTERVALO_DETALLE_MS } from "@/lib/refresco";

/** Cuántos barridos pedir al log (el back acota a su cota dura por daemon). */
const LIMITE_BARRIDOS = 50;

/** Log por barrido: tabla de `GET …/barridos` (nuevo primero). */
export function LogBarridos({ daemon, limite = LIMITE_BARRIDOS }: { daemon: string; limite?: number }) {
  const query = useQuery({
    queryKey: ["sistema", "daemons", daemon, "barridos", limite],
    queryFn: ({ signal }) => api.sistemaDaemonBarridos(daemon, limite, signal),
    refetchInterval: INTERVALO_DETALLE_MS,
  });

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileText className="h-4 w-4" aria-hidden="true" />
          Log por barrido
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {query.isPending ? (
          <Skeleton className="h-40 w-full rounded-xl" />
        ) : query.isError ? (
          <BloqueError
            titulo="No se pudo leer el log de barridos"
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        ) : query.data.barridos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin barridos</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Hora</TableHead>
                <TableHead>Resultado</TableHead>
                <TableHead>Duración</TableHead>
                <TableHead>Resumen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.barridos.map((b) => (
                <TableRow key={b.id}>
                  <TableCell
                    className="whitespace-nowrap text-muted-foreground"
                    title={formatearFechaHora(b.ts_inicio)}
                  >
                    {tiempoRelativo(b.ts_inicio)}
                  </TableCell>
                  <TableCell>
                    {b.ok ? (
                      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                        OK
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
                        <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                        Error
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums text-muted-foreground">
                    {b.duracion_ms > 0 ? duracion(b.duracion_ms) : "—"}
                  </TableCell>
                  <TableCell className="text-sm">
                    {/* `resumen` puede venir vacío hoy: si falta, el error (cuando lo hay) o un
                        guion. Así una fila nunca queda muda. */}
                    {b.resumen ? (
                      <span>{b.resumen}</span>
                    ) : b.error_txt ? (
                      <span className="text-red-600 dark:text-red-400">{b.error_txt}</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                    {b.resumen && b.error_txt && (
                      <span className="mt-0.5 block text-xs text-red-600 dark:text-red-400">
                        {b.error_txt}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
