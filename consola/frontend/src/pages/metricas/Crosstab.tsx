/**
 * Crosstab de rendimiento marca×red×formato (estrategia digital).
 *
 * Una tabla-mapa de calor: cada fila es una combinación marca×red×formato del periodo
 * con su número de piezas, engagement medio y `rendimiento_relativo_medio` (vistas de la
 * celda ÷ mediana de VISTAS de su grupo). El rendimiento relativo se colorea para leer de
 * un vistazo qué formatos alcanzan por encima (>1, verde) o por debajo (<1, rojo) de su grupo.
 *
 * Mismo stack y estados honestos (carga / vacío / error) que el resto de Métricas: si la
 * fuente no expone celdas, lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { Grid3x3 } from "lucide-react";

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
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import {
  nombreFormato,
  nombreMarca,
  nombreRed,
  numeroCompacto,
  porcentaje,
} from "@/lib/formato";
import type { CeldaCrosstab, MarcaDisponible } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";
import { useOrdenTabla } from "./useOrdenTabla";

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
  marcas,
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Catálogo {id, nombre} para resolver el id crudo de marca de cada celda. */
  marcas: MarcaDisponible[];
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
    <SeccionColapsable
      titulo="Rendimiento por formato"
      icono={Grid3x3}
      descripcion={
        <>
          Cruce marca × red × formato. El rendimiento relativo compara las VISTAS de
          cada combinación con la mediana de vistas de su grupo:{" "}
          <span className="text-emerald-700 dark:text-emerald-300">verde</span> alcanza
          por encima, <span className="text-red-700 dark:text-red-300">rojo</span> por debajo.
        </>
      }
    >
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
        <TablaCrosstab celdas={data.celdas} marcas={marcas} />
      )}
    </SeccionColapsable>
  );
}

type ClaveCrosstab = "n_piezas" | "visualizaciones" | "engagement_pct" | "rendimiento";

function TablaCrosstab({
  celdas,
  marcas,
}: {
  celdas: CeldaCrosstab[];
  marcas: MarcaDisponible[];
}) {
  // Orden por defecto: rendimiento relativo descendente (lo que más rinde, arriba).
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<CeldaCrosstab, ClaveCrosstab>(
    celdas,
    {
      n_piezas: (c) => c.n_piezas,
      visualizaciones: (c) => c.visualizaciones,
      engagement_pct: (c) => c.engagement_pct,
      rendimiento: (c) => c.rendimiento_relativo_medio,
    },
    { clave: "rendimiento", direccion: "desc" },
  );

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Marca</TableHead>
            <TableHead>Red</TableHead>
            <TableHead>Formato</TableHead>
            <CabeceraOrdenable
              activa={estado.clave === "n_piezas"}
              direccion={estado.direccion}
              onClick={() => alClicar("n_piezas")}
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
              Vistas
            </CabeceraOrdenable>
            <CabeceraOrdenable
              activa={estado.clave === "engagement_pct"}
              direccion={estado.direccion}
              onClick={() => alClicar("engagement_pct")}
              alinear="right"
            >
              Eng.
            </CabeceraOrdenable>
            <CabeceraOrdenable
              activa={estado.clave === "rendimiento"}
              direccion={estado.direccion}
              onClick={() => alClicar("rendimiento")}
              alinear="right"
            >
              Rendimiento
            </CabeceraOrdenable>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filasOrdenadas.map((c) => (
            <TableRow key={`${c.marca}-${c.red}-${c.formato ?? "sin"}`}>
              <TableCell className="font-medium">{nombreMarca(c.marca, marcas)}</TableCell>
              <TableCell className="text-muted-foreground">{nombreRed(c.red)}</TableCell>
              <TableCell className="text-muted-foreground">{nombreFormato(c.formato)}</TableCell>
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
                title="Vistas de la celda ÷ mediana de vistas de su grupo"
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
