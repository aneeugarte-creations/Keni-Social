/**
 * Altas y bajas de seguidores del periodo, por red (estrategia digital).
 *
 * Descompone el crecimiento neto en sus dos flujos: las ALTAS (nuevos seguidores) y las
 * BAJAS (desconexiones). Refuerza el relato de audiencia más allá del stock: una marca puede
 * crecer en neto y aun así perder mucha gente (alta rotación). No todas las redes separan
 * los flujos: TikTok e Instagram solo dan el neto, así que `altas`/`bajas` llegan `null` y se
 * muestran como "—"; Facebook y YouTube sí dan altas/bajas brutas. El `neto` siempre viene.
 *
 * `por_red` vacío = la fuente no expone flujo de audiencia (degradación honesta).
 */
import { useQuery } from "@tanstack/react-query";
import { UsersRound } from "lucide-react";
import * as React from "react";

import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { marcaParam } from "@/components/comunes/selectores";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { nombreRed, numeroCompleto, REDES_CANONICAS, redCanonica } from "@/lib/formato";
import type { AudienciaPorRed } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";
import { useVistaConfig } from "./vistaConfig";

/** Neto con signo: es un CONTEO (`+1,234` / `−5,200` / `0`), no un porcentaje. */
function netoConSigno(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "0";
  return `${n > 0 ? "+" : "−"}${numeroCompleto(Math.abs(n))}`;
}

/** Color del neto: verde sube, rojo baja, neutro sin cambio. */
function colorNeto(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "text-muted-foreground";
  return n > 0
    ? "text-emerald-700 dark:text-emerald-300"
    : "text-red-700 dark:text-red-300";
}

export function FlujoAudiencia({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "audiencia", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasAudiencia({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // Filas en orden canónico, solo las redes que el flujo trae (no se pinta una fila "—" para
  // una red sin datos: aquí la ausencia es "sin flujo de audiencia", distinto del stock).
  const filas = React.useMemo(() => {
    const por: Record<string, AudienciaPorRed> = {};
    for (const r of data?.por_red ?? []) por[redCanonica(r.red)] = r;
    return REDES_CANONICAS.filter((r) => por[r]).map((r) => por[r]);
  }, [data]);

  return (
    <Seccion
      id="audiencia"
      titulo="Altas y bajas de seguidores"
      icono={UsersRound}
      descripcion="El crecimiento neto descompuesto en altas (nuevos) y bajas (desconexiones). Facebook y YouTube separan ambos flujos; TikTok e Instagram solo reportan el neto."
    >
      <Card className="overflow-hidden py-2">
        {isPending ? (
          <div className="p-4">
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        ) : isError ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No se pudo cargar el flujo de audiencia.
          </p>
        ) : filas.length === 0 ? (
          <EstadoVacioTexto texto="No hay flujo de audiencia para este periodo." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Red</TableHead>
                <TableHead className="text-right">Altas</TableHead>
                <TableHead className="text-right">Bajas</TableHead>
                <TableHead className="pr-6 text-right last:pr-6">Neto</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filas.map((f) => (
                <TableRow key={f.red}>
                  <TableCell className="pl-6 font-medium">{nombreRed(f.red)}</TableCell>
                  <TableCell className="text-right tabular-nums text-emerald-700 dark:text-emerald-300">
                    {f.altas === null ? (
                      <span className="text-muted-foreground" title="Esta red no separa altas">
                        —
                      </span>
                    ) : (
                      `+${numeroCompleto(f.altas)}`
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-red-700 dark:text-red-300">
                    {f.bajas === null ? (
                      <span className="text-muted-foreground" title="Esta red no separa bajas">
                        —
                      </span>
                    ) : (
                      `−${numeroCompleto(f.bajas)}`
                    )}
                  </TableCell>
                  <TableCell
                    className={`pr-6 text-right font-medium tabular-nums last:pr-6 ${colorNeto(f.neto)}`}
                  >
                    {netoConSigno(f.neto)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </Seccion>
  );
}
