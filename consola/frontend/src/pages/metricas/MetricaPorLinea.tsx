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

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { PieMostrarMas } from "./PieMostrarMas";
import { SeccionColapsable } from "./SeccionColapsable";
import { useFilasPlegables } from "./useFilasPlegables";
import { useOrdenTabla } from "./useOrdenTabla";

type ClaveOrden = "piezas" | "visualizaciones" | "interacciones" | "engagement_pct";

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
    <SeccionColapsable
      titulo="Rendimiento por línea y origen"
      descripcion="Qué líneas de contenido y qué orígenes (interno / petición externa) rinden mejor en el periodo: piezas publicadas, visualizaciones, interacciones y engagement."
      icono={GitBranch}
      contentClassName="space-y-8"
    >
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
    </SeccionColapsable>
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
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<FilaMetricaLinea, ClaveOrden>(
    filas,
    {
      piezas: (f) => f.piezas,
      visualizaciones: (f) => f.visualizaciones,
      interacciones: (f) => f.interacciones,
      engagement_pct: (f) => f.engagement_pct,
    },
    { clave: "visualizaciones", direccion: "desc" },
  );

  // Recorte a 5 filas (post-orden); la de "Por origen" (2-3 filas) no se recorta (umbral).
  const { visibles, expandido, alternar, hayMas } = useFilasPlegables(filasOrdenadas, 5);

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
                <CabeceraOrdenable
                  activa={estado.clave === "piezas"}
                  direccion={estado.direccion}
                  onClick={() => alClicar("piezas")}
                  alinear="right"
                >
                  Piezas
                </CabeceraOrdenable>
                <CabeceraOrdenable
                  activa={estado.clave === "visualizaciones"}
                  direccion={estado.direccion}
                  onClick={() => alClicar("visualizaciones")}
                  alinear="right"
                >
                  Visualizaciones
                </CabeceraOrdenable>
                <CabeceraOrdenable
                  activa={estado.clave === "interacciones"}
                  direccion={estado.direccion}
                  onClick={() => alClicar("interacciones")}
                  alinear="right"
                >
                  Interacciones
                </CabeceraOrdenable>
                <CabeceraOrdenable
                  activa={estado.clave === "engagement_pct"}
                  direccion={estado.direccion}
                  onClick={() => alClicar("engagement_pct")}
                  alinear="right"
                >
                  Engagement
                </CabeceraOrdenable>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibles.map((f) => (
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
            {hayMas && (
              <PieMostrarMas expandido={expandido} onAlternar={alternar} colSpan={5} />
            )}
          </Table>
        </div>
      )}
    </div>
  );
}
