/**
 * Métrica por LÍNEA de contenido (vertical) y por ORIGEN.
 *
 * Consume `/api/metricas/lineas` y muestra dos tablas: rendimiento del periodo por línea
 * y por origen, con piezas / visualizaciones / interacciones / engagement. Sigue el
 * selector de marca + rango global del dashboard (la marca viaja en forma `id_metricas`,
 * que es justo lo que devuelve `marcaParam` para el catálogo de Métricas).
 *
 * Estados honestos (carga / vacío / error) como el resto de Métricas: si la fuente no
 * expone líneas/orígenes para el periodo, lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";

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
import { api } from "@/lib/api";
import { numeroCompacto, porcentaje } from "@/lib/formato";
import type { FilaMetricaLinea } from "@/types";

import { MARCA_TODAS } from "./Controles";

export function MetricaPorLinea({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "lineas", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasLineas({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Rendimiento por línea y origen</CardTitle>
        </div>
        <p className="text-sm text-muted-foreground">
          Qué líneas de contenido y qué orígenes (interno / petición externa) rinden mejor en
          el periodo: piezas publicadas, visualizaciones, interacciones y engagement.
        </p>
      </CardHeader>
      <CardContent className="space-y-8">
        {isPending ? (
          <Skeleton className="h-72 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No se pudo cargar el rendimiento por línea.
          </p>
        ) : data.lineas.length === 0 && data.origenes.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            La fuente activa no expone rendimiento por línea u origen para este periodo.
          </p>
        ) : (
          <>
            <TablaLineas
              titulo="Por línea de contenido"
              filas={data.lineas}
              total={data.total}
              etiquetaPrimera="Línea"
            />
            <TablaLineas
              titulo="Por origen"
              filas={data.origenes}
              total={data.total}
              etiquetaPrimera="Origen"
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function TablaLineas({
  titulo,
  filas,
  total,
  etiquetaPrimera,
}: {
  titulo: string;
  filas: FilaMetricaLinea[];
  total: FilaMetricaLinea;
  etiquetaPrimera: string;
}) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold tracking-tight">{titulo}</h3>
      {filas.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          Sin datos para este corte en el periodo.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{etiquetaPrimera}</TableHead>
                <TableHead className="text-right">Piezas</TableHead>
                <TableHead className="text-right">Visualizaciones</TableHead>
                <TableHead className="text-right">Interacciones</TableHead>
                <TableHead className="text-right">Engagement</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filas.map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="font-medium">{f.nombre}</TableCell>
                  <TableCell className="text-right tabular-nums">{f.piezas}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompacto(f.visualizaciones)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompacto(f.interacciones)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {porcentaje(f.engagement_pct)}
                  </TableCell>
                </TableRow>
              ))}
              <TableRow className="border-t-2 font-medium">
                <TableCell>Total</TableCell>
                <TableCell className="text-right tabular-nums">{total.piezas}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {numeroCompacto(total.visualizaciones)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {numeroCompacto(total.interacciones)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {porcentaje(total.engagement_pct)}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
