/**
 * Métrica por LÍNEA de contenido (vertical) y por ORIGEN.
 *
 * Consume `/api/metricas/lineas` y muestra dos tablas: rendimiento del periodo por línea
 * y por origen, con piezas / vistas / interacciones / engagement (promedio por pieza:
 * media simple de porcentajes, como lo agrega el backend). Sigue el selector de marca +
 * rango global del dashboard (la marca viaja en forma `id_metricas`, que es justo lo que
 * devuelve `marcaParam` para el catálogo de Métricas).
 *
 * Ambas tablas comparten el mismo conjunto de métricas, así que comparten también el editor
 * de campos (`tablaId` "por-linea"): ocultar/reordenar columnas aplica a las dos a la vez.
 * La primera columna (dimensión) cambia de etiqueta por tabla (Línea vs Origen).
 *
 * Estados honestos (carga / vacío / error) como el resto de Métricas: si la fuente no
 * expone líneas/orígenes para el periodo, lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";

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
import { numeroCompleto, porcentaje } from "@/lib/formato";
import type { FilaMetricaLinea } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import type { ColumnaMeta } from "./columnasMeta";
import { MARCA_TODAS } from "./Controles";
import { PieMostrarMas } from "./PieMostrarMas";
import { Seccion } from "./Seccion";
import { useFilasPlegables } from "./useFilasPlegables";
import { useOrdenTabla } from "./useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

/** Id de tabla compartido por las dos tablas (clave en `vistaConfig.columnas`). */
const TABLA_POR_LINEA = "por-linea";

type ClaveMetrica = "piezas" | "visualizaciones" | "interacciones" | "engagement_pct";

/**
 * Catálogo de campos COMPARTIDO por las dos tablas. La primera columna ("dimension") es la
 * vertical de cada fila: se etiqueta "Línea" u "Origen" según la tabla en el render. El resto
 * son las métricas comunes. Su orden aquí es el orden base.
 */
const COLUMNAS: ColumnaMeta[] = [
  { id: "dimension", etiqueta: "Categoría" },
  { id: "piezas", etiqueta: "Piezas" },
  { id: "visualizaciones", etiqueta: "Vistas" },
  { id: "interacciones", etiqueta: "Interacciones" },
  { id: "engagement_pct", etiqueta: "Engagement" },
];

const IDS_BASE = COLUMNAS.map((c) => c.id);

/** Etiqueta legible de cada columna métrica en la cabecera ordenable. */
const ETIQUETA_METRICA: Record<ClaveMetrica, string> = {
  piezas: "Piezas",
  visualizaciones: "Vistas",
  interacciones: "Interacciones",
  engagement_pct: "Engagement",
};

/** Accesores de orden por columna (constante de módulo: referencia estable entre renders). */
const ACCESORES: Record<ClaveMetrica, (f: FilaMetricaLinea) => number | null> = {
  piezas: (f) => f.piezas,
  visualizaciones: (f) => f.visualizaciones,
  interacciones: (f) => f.interacciones,
  engagement_pct: (f) => f.engagement_pct,
};

/** Formatea el valor de una columna métrica de una fila. */
function valorCelda(f: FilaMetricaLinea, clave: ClaveMetrica): string {
  if (clave === "piezas") {
    return String(f.piezas);
  }
  if (clave === "engagement_pct") {
    return porcentaje(f.engagement_pct);
  }
  return numeroCompleto(f[clave]);
}

export function MetricaPorLinea({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);
  const formato = useVistaConfig((s) => s.formato);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "lineas", rangoActual ?? "", marca_ ?? "todas", red ?? "todas", formato ?? "todos"],
    queryFn: ({ signal }) =>
      api.metricasLineas({ rango: rangoActual, marca: marca_, red: red ?? undefined, formato: formato ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  return (
    <Seccion
      id="por-linea"
      titulo="Rendimiento por línea"
      icono={GitBranch}
      tablaId={TABLA_POR_LINEA}
      columnas={COLUMNAS}
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
          Aún no hay rendimiento por línea u origen para este periodo.
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
    </Seccion>
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
  // Config de columnas COMPARTIDA por las dos tablas: ambas leen la misma clave, así que
  // ocultar/reordenar campos en el editor se refleja en las dos a la vez.
  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA_POR_LINEA]);
  const cfg = cfgGuardada ?? { orden: IDS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_BASE, cfg);

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<FilaMetricaLinea, ClaveMetrica>(
    filas,
    ACCESORES,
    { clave: "visualizaciones", direccion: "desc" },
  );

  // Recorte a 5 filas (post-orden); la de "Por origen" (2-3 filas) no se recorta (umbral).
  const { visibles, expandido, alternar, hayMas } = useFilasPlegables(filasOrdenadas, 5);

  const encabezado = (id: string) => {
    if (id === "dimension") {
      return (
        <TableHead key={id} className="pl-6">
          {etiquetaPrimera}
        </TableHead>
      );
    }
    const clave = id as ClaveMetrica;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear="right"
        className="pr-6 last:pr-6"
      >
        {ETIQUETA_METRICA[clave]}
      </CabeceraOrdenable>
    );
  };

  const celda = (f: FilaMetricaLinea, id: string) => {
    if (id === "dimension") {
      return (
        <TableCell key={id} className="pl-6 font-medium">
          {f.nombre}
        </TableCell>
      );
    }
    return (
      <TableCell key={id} className="pr-6 text-right tabular-nums last:pr-6">
        {valorCelda(f, id as ClaveMetrica)}
      </TableCell>
    );
  };

  const celdaTotal = (id: string) => {
    if (id === "dimension") {
      return (
        <TableCell key={id} className="pl-6">
          Total
        </TableCell>
      );
    }
    return (
      <TableCell key={id} className="pr-6 text-right tabular-nums last:pr-6">
        {valorCelda(total, id as ClaveMetrica)}
      </TableCell>
    );
  };

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold tracking-tight">{titulo}</h3>
      {filas.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          Sin datos para este corte en el periodo.
        </p>
      ) : (
        <Card className="overflow-hidden py-2">
          <Table>
            <TableHeader>
              <TableRow>{columnas.map(encabezado)}</TableRow>
            </TableHeader>
            <TableBody>
              {/* Señales del plan (Evergreen/Última hora) y "Sin línea" comparten id vacío:
                  la clave usa el nombre (único por cubo) para no colisionar. */}
              {visibles.map((f) => (
                <TableRow key={f.id || f.nombre}>
                  {columnas.map((id) => celda(f, id))}
                </TableRow>
              ))}
              <TableRow className="border-t-2 font-medium">
                {columnas.map(celdaTotal)}
              </TableRow>
            </TableBody>
            {hayMas && (
              <PieMostrarMas
                expandido={expandido}
                onAlternar={alternar}
                colSpan={columnas.length}
              />
            )}
          </Table>
        </Card>
      )}
    </div>
  );
}
