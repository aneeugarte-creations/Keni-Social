/**
 * Sección "Publicidad (Meta Ads)": el INORGÁNICO del periodo a nivel marca.
 *
 * Lista las campañas de pago (impresiones, gasto, clics) con sus totales, claramente
 * separadas de lo orgánico. Sólo aparece si hubo inversión con entrega en el periodo
 * (si no, no ensucia el dashboard). Reusa el stack del resto de Métricas: SeccionColapsable
 * + tabla ordenable, estados honestos (carga / error / vacío).
 */
import { useQuery } from "@tanstack/react-query";
import { Megaphone } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { Badge } from "@/components/ui/badge";
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
import { nombreRed, numeroCompacto, numeroCompleto } from "@/lib/formato";
import type { CampaniaAdsMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";
import { useOrdenTabla } from "./useOrdenTabla";

function dinero(v: number, moneda: string): string {
  return `${v.toLocaleString("es-MX", { maximumFractionDigits: 0 })} ${moneda}`.trim();
}

type ClaveOrden = "impresiones" | "gasto" | "clics";

// Accesores de orden a nivel módulo: identidad estable entre renders.
const ACCESORES: Record<ClaveOrden, (a: CampaniaAdsMetrica) => number> = {
  impresiones: (a) => a.impresiones,
  gasto: (a) => a.gasto,
  clics: (a) => a.clics,
};

export function SeccionAds({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "ads", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasAds({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const ads = data?.ads ?? [];
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<CampaniaAdsMetrica, ClaveOrden>(
    ads,
    ACCESORES,
    { clave: "impresiones", direccion: "desc" },
  );

  // Sin inversión con entrega en el periodo (o sin Ads conectado): no se muestra la sección.
  if (!isPending && !isError && (data?.total.campanias ?? 0) === 0) return null;

  const total = data?.total;
  const col = (clave: ClaveOrden, etiqueta: string, className?: string) => (
    <CabeceraOrdenable
      activa={estado.clave === clave}
      direccion={estado.direccion}
      onClick={() => alClicar(clave)}
      alinear="right"
      className={className}
    >
      {etiqueta}
    </CabeceraOrdenable>
  );

  return (
    <SeccionColapsable
      titulo="Publicidad"
      icono={Megaphone}
      descripcion="Campañas de pago del periodo, separadas del contenido orgánico."
      contentClassName="p-0"
    >
      {isPending ? (
        <div className="p-4">
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : isError ? (
        <p className="p-6 text-sm text-muted-foreground">No se pudieron cargar las campañas de Ads.</p>
      ) : (
        <>
          {total && (
            <div className="flex flex-wrap gap-x-8 gap-y-2 border-b px-6 py-4">
              {/* `total.visualizaciones` es la SUMA de la columna Impresiones (no son
                  vistas orgánicas): el término correcto en Ads es "Impresiones". */}
              <Kpi etiqueta="Impresiones" valor={numeroCompacto(total.visualizaciones)} titulo={numeroCompleto(total.visualizaciones)} />
              <Kpi etiqueta="Gasto" valor={dinero(total.gasto, total.moneda)} />
              <Kpi etiqueta="Campañas" valor={String(total.campanias)} />
              <Kpi etiqueta="Clics" valor={numeroCompacto(total.clics)} />
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Campaña</TableHead>
                <TableHead>Red</TableHead>
                {col("impresiones", "Impresiones")}
                {col("gasto", "Gasto")}
                {col("clics", "Clics", "pr-6")}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filasOrdenadas.map((a, i) => (
                // Clave estable ante reordenaciones: nombre+red+inicio identifica la
                // campaña; el índice solo entra si `inicio` llega vacío.
                <TableRow key={`${a.nombre}-${a.red}-${a.inicio || i}`}>
                  <TableCell className="pl-6">
                    <span className="block max-w-[28rem] truncate font-medium" title={a.nombre}>
                      {a.nombre}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{nombreRed(a.red)}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(a.impresiones)}>
                    {numeroCompacto(a.impresiones)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{dinero(a.gasto, a.moneda)}</TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">{numeroCompacto(a.clics)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </SeccionColapsable>
  );
}

function Kpi({ etiqueta, valor, titulo }: { etiqueta: string; valor: string; titulo?: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs text-muted-foreground">{etiqueta}</p>
      <p className="text-lg font-semibold tabular-nums" title={titulo ?? valor}>
        {valor}
      </p>
    </div>
  );
}
