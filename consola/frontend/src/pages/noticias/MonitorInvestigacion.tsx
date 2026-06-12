/**
 * Monitor EN VIVO del loop de INVESTIGACIÓN (ADR 0011), en su propia página (Noticias).
 *
 * Investigación y Producción comparten la MISMA cola y pool; este panel NO inventa una cola
 * aparte: lee el MISMO snapshot/serie (`/api/actividad/cola*`) que el Monitor de Producción y
 * recorta la vista al loop de investigación —su parte del pool (criba/QA en curso/en cola), el
 * embudo de verificación (lo único que este loop acota aparte) y su throughput/gasto del día—.
 * El Monitor de Producción (avatar → Producción → Monitor) es el que OPERA la cola (purgar,
 * cancelar, kill switch); aquí solo se OBSERVA el lado investigación.
 */
import { useQuery } from "@tanstack/react-query";
import { Microscope } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { INTERVALO_SERIE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";
import {
  DesgloseEconomiaProceso,
  resultadoDelDia,
  SerieProceso,
  TarjetaProceso,
} from "@/pages/monitor/comun";

export function MonitorInvestigacion() {
  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });
  const serie = useQuery({
    queryKey: ["actividad", "cola", "series"],
    queryFn: ({ signal }) => api.colaSeries(14, signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });

  // Back anterior (sin desglose por proceso): no pintamos el panel para no mentir con ceros.
  if (cola.data && !cola.data.por_proceso) return null;

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Microscope className="h-4 w-4 text-sky-600" />
          Monitor de investigación
          <span className="text-xs font-normal text-muted-foreground">
            criba y verificación de la fuente · cola compartida con producción
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-2">
        {cola.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : cola.isError ? (
          <p className="text-sm text-muted-foreground">No se pudo leer la cola.</p>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <TarjetaProceso cola={cola.data} proceso="investigacion" />
              <div className="flex flex-col justify-center gap-2 rounded-lg border p-4">
                <span className="text-xs text-muted-foreground">Gasto de hoy (investigación)</span>
                <DesgloseEconomiaProceso
                  res={resultadoDelDia(serie.data, cola.data.presupuesto?.dia ?? "")}
                  soloProceso="investigacion"
                />
              </div>
            </div>
            {/* Throughput de verificación por día (solo investigación; sin marcadores de etapa). */}
            {serie.isPending ? (
              <Skeleton className="h-32 w-full" />
            ) : serie.isError ? null : (
              <SerieProceso serie={serie.data} soloProceso="investigacion" />
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
