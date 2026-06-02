/**
 * Crecimiento de seguidores del periodo (estrategia digital).
 *
 * Pinta la evolución día a día del total de seguidores (AreaChart de Tremor, mismo
 * stack que el resto de Métricas) con opción de desglosar por red. El neto del periodo
 * (`neto` global + `neto_por_red`) se muestra como KPIs arriba. Si la fuente activa no
 * expone seguidores (`puntos=[]`) lo dice con honestidad en vez de inventar una serie.
 */
import { useQuery } from "@tanstack/react-query";
import { AreaChart } from "@tremor/react";
import { Users } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { numeroCompacto, numeroCompleto, variacion } from "@/lib/formato";
import type { PuntoSeguidores } from "@/types";

import { MARCA_TODAS } from "./Controles";

/** "12 may" a partir de una fecha ISO (AAAA-MM-DD), en es-MX. */
function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(d);
}

// Paleta estable para las series por red (Tremor toma estos nombres de color).
const COLORES_RED = ["blue", "violet", "emerald", "amber", "rose", "cyan", "indigo"];

export function CrecimientoSeguidores({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const [porRed, setPorRed] = React.useState(false);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "seguidores", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasSeguidores({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // Redes presentes en la serie (orden estable por aparición en el neto_por_red).
  const redes = React.useMemo(
    () => (data ? Object.keys(data.neto_por_red) : []),
    [data],
  );

  const datos = (data?.puntos ?? []).map((p: PuntoSeguidores) =>
    porRed
      ? { fecha: fechaCorta(p.fecha), ...p.por_red }
      : { fecha: fechaCorta(p.fecha), Total: p.total },
  );

  const categorias = porRed ? redes : ["Total"];
  const colores = porRed ? COLORES_RED.slice(0, redes.length) : ["blue"];

  return (
    <Card>
      <CardHeader className="gap-1 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <CardTitle className="text-base">Crecimiento de seguidores</CardTitle>
          </div>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <Switch
              checked={porRed}
              onCheckedChange={setPorRed}
              aria-label="Desglosar por red"
              disabled={redes.length === 0}
            />
            Por red
          </label>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPending ? (
          <Skeleton className="h-56 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No se pudo cargar la serie de seguidores.
          </p>
        ) : (data.puntos ?? []).length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            La fuente activa no expone seguidores aún para este periodo.
          </p>
        ) : (
          <>
            <KpisNeto neto={data.neto} netoPorRed={data.neto_por_red} />
            <AreaChart
              data={datos}
              index="fecha"
              categories={categorias}
              colors={colores}
              valueFormatter={numeroCompacto}
              showLegend={porRed}
              showAnimation
              startEndOnly
              curveType="monotone"
              className="h-56"
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Neto del periodo: el global como destacado + un KPI por red. */
function KpisNeto({
  neto,
  netoPorRed,
}: {
  neto: number;
  netoPorRed: Record<string, number>;
}) {
  const redes = Object.keys(netoPorRed);
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      <TarjetaKpi
        etiqueta="Neto del periodo"
        valor={variacion(neto)}
        titulo={`${numeroCompleto(neto)} seguidores`}
      />
      {redes.map((red) => (
        <TarjetaKpi key={red} etiqueta={red} valor={variacion(netoPorRed[red])} />
      ))}
    </div>
  );
}
