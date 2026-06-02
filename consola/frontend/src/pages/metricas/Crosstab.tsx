/**
 * Crosstab de rendimiento marca×red×formato (estrategia digital).
 *
 * Una tabla-mapa de calor: cada fila es una combinación marca×red×formato del periodo
 * con su número de piezas, engagement medio y `rendimiento_relativo_medio` (engagement de
 * la celda ÷ mediana de su grupo). El rendimiento relativo se colorea para leer de un
 * vistazo qué formatos rinden por encima (>1, verde) o por debajo (<1, rojo) de su grupo.
 *
 * Mismo stack y estados honestos (carga / vacío / error) que el resto de Métricas: si la
 * fuente no expone celdas, lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { Grid3x3 } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
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
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { numeroCompacto, porcentaje } from "@/lib/formato";
import type { CeldaCrosstab } from "@/types";

import { MARCA_TODAS } from "./Controles";

/** Sin formato declarado: el backend manda `null`. */
function formatoLegible(f: string | null): string {
  return f && f.trim() ? f : "Sin formato";
}

/**
 * Color del rendimiento relativo (>1 rinde por encima de la mediana de su grupo, <1
 * por debajo). `null` = no hay base para compararlo (grupo de una sola pieza, etc.).
 */
function claseRendimiento(v: number | null): string {
  if (v == null) return "text-muted-foreground";
  if (v >= 1.05) return "text-emerald-700 dark:text-emerald-300";
  if (v <= 0.95) return "text-red-700 dark:text-red-300";
  return "text-foreground";
}

function textoRendimiento(v: number | null): string {
  // 1 decimal, consistente con el badge de `rendimiento_relativo` en PiezasAnalitica.
  return v == null ? "—" : `${v.toLocaleString("es-MX", { maximumFractionDigits: 1 })}×`;
}

export function Crosstab({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "crosstab", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasCrosstab({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <Grid3x3 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Rendimiento por formato</CardTitle>
        </div>
        <p className="text-sm text-muted-foreground">
          Cruce marca × red × formato. El rendimiento relativo compara el engagement de
          cada combinación con la mediana de su grupo: <span className="text-emerald-700 dark:text-emerald-300">verde</span> rinde
          por encima, <span className="text-red-700 dark:text-red-300">rojo</span> por debajo.
        </p>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Skeleton className="h-64 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No se pudo cargar el rendimiento por formato.
          </p>
        ) : data.celdas.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            La fuente activa no expone el cruce por formato para este periodo.
          </p>
        ) : (
          <TablaCrosstab celdas={data.celdas} />
        )}
      </CardContent>
    </Card>
  );
}

function TablaCrosstab({ celdas }: { celdas: CeldaCrosstab[] }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Marca</TableHead>
            <TableHead>Red</TableHead>
            <TableHead>Formato</TableHead>
            <TableHead className="text-right">Piezas</TableHead>
            <TableHead className="text-right">Vistas</TableHead>
            <TableHead className="text-right">Eng.</TableHead>
            <TableHead className="text-right">Rendimiento</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {celdas.map((c) => (
            <TableRow key={`${c.marca}-${c.red}-${c.formato ?? "sin"}`}>
              <TableCell className="font-medium">{c.marca}</TableCell>
              <TableCell className="text-muted-foreground">{c.red}</TableCell>
              <TableCell className="text-muted-foreground">{formatoLegible(c.formato)}</TableCell>
              <TableCell className="text-right tabular-nums">{c.n_piezas}</TableCell>
              <TableCell className="text-right tabular-nums">
                {numeroCompacto(c.visualizaciones)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {porcentaje(c.engagement_pct)}
              </TableCell>
              <TableCell
                className={cn(
                  "text-right font-medium tabular-nums",
                  claseRendimiento(c.rendimiento_relativo_medio),
                )}
                title="Engagement de la celda ÷ mediana de su grupo"
              >
                {textoRendimiento(c.rendimiento_relativo_medio)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
