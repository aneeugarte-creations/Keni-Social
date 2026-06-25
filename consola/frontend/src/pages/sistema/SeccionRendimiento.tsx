import { useQuery } from "@tanstack/react-query";
import { Gauge } from "lucide-react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
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

import { INTERVALO_RECURSOS_MS } from "./lib";

/** Cuántas rutas mostramos (las más usadas; el back ya ordena por nº de peticiones). */
const MAX_FILAS = 15;

/** Color del p95 según el nivel (latencia API: <300 ms bien, >1 s mal). */
function colorLatencia(ms: number): string {
  if (ms >= 1000) return "text-red-500";
  if (ms >= 300) return "text-amber-500";
  return "";
}

/**
 * Sección de rendimiento de la API del panel Sistema: latencias agregadas por ruta
 * (p50/p95/max del primer byte, ventana de las últimas 256 peticiones por ruta).
 * El agregador vive en memoria del back y se reinicia con cada deploy.
 */
export function SeccionRendimiento() {
  const query = useQuery({
    queryKey: ["sistema", "rendimiento"],
    queryFn: ({ signal }) => api.sistemaRendimiento(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });

  if (query.isPending) {
    return <Skeleton className="h-48 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer el rendimiento de la API"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { desde, rutas } = query.data;
  const filas = rutas.slice(0, MAX_FILAS);

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <Gauge className="h-4 w-4" aria-hidden="true" />
          Rendimiento de la API
          <span className="ml-auto text-xs font-normal text-muted-foreground/70">
            desde {tiempoRelativo(desde)}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {filas.length === 0 ? (
          <EstadoVacioTexto texto="Sin peticiones registradas." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ruta</TableHead>
                <TableHead className="text-right">Peticiones</TableHead>
                <TableHead className="text-right">p50</TableHead>
                <TableHead className="text-right">p95</TableHead>
                <TableHead className="text-right">máx</TableHead>
                <TableHead className="text-right">5xx</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filas.map((r) => (
                <TableRow key={r.ruta}>
                  <TableCell className="max-w-[40ch] truncate font-mono text-xs" title={r.ruta}>
                    {r.ruta}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{r.n}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {r.p50_ms} ms
                  </TableCell>
                  <TableCell
                    className={cn("text-right tabular-nums", colorLatencia(r.p95_ms))}
                  >
                    {r.p95_ms} ms
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {r.max_ms} ms
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      r.err_5xx > 0 ? "text-red-500" : "text-muted-foreground",
                    )}
                  >
                    {r.err_5xx}
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
