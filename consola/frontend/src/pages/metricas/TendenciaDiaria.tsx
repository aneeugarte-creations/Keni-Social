/**
 * Tendencia diaria del periodo: evolución día a día de visualizaciones o interacciones.
 *
 * Una sola gráfica conmutable (no dos a la vez) para no saturar: las escalas de vistas
 * e interacciones difieren mucho y superponerlas engañaría. Usa Tremor (mismo stack que
 * el resto de Métricas) y se sirve de la cache del backend (`/api/metricas/tendencia`).
 * Si la fuente activa no expone serie diaria, lo dice con honestidad en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { AreaChart } from "@tremor/react";
import { LineChart as LineChartIcon } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { numeroCompacto, numeroCompleto } from "@/lib/formato";
import type { PuntoSerie } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";

type Metrica = "visualizaciones" | "interacciones";

const ETIQUETA: Record<Metrica, string> = {
  visualizaciones: "Visualizaciones",
  interacciones: "Interacciones",
};
const COLOR: Record<Metrica, string> = { visualizaciones: "orange", interacciones: "violet" };

/** "12 may" a partir de una fecha ISO (AAAA-MM-DD), en es-MX. */
function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(d);
}

export function TendenciaDiaria({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const [metrica, setMetrica] = React.useState<Metrica>("visualizaciones");

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "tendencia", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasTendencia({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    // 2 min: el conmutador de métrica/marca no debe re-pegar a la fuente en cada cambio,
    // pero tampoco queremos serie rancia; "Actualizar" invalida igualmente.
    staleTime: 2 * 60_000,
  });

  const etiqueta = ETIQUETA[metrica];
  const datos = (data?.puntos ?? []).map((p: PuntoSerie) => ({
    fecha: fechaCorta(p.fecha),
    [etiqueta]: p[metrica],
  }));

  return (
    <SeccionColapsable
      titulo="Tendencia diaria"
      icono={LineChartIcon}
      acciones={
        <Select value={metrica} onValueChange={(v) => setMetrica(v as Metrica)}>
          <SelectTrigger className="w-[170px]" aria-label="Métrica de la tendencia">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="visualizaciones">Visualizaciones</SelectItem>
            <SelectItem value="interacciones">Interacciones</SelectItem>
          </SelectContent>
        </Select>
      }
    >
      {isPending ? (
          <Skeleton className="h-56 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No se pudo cargar la tendencia.
          </p>
        ) : datos.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            La fuente activa no expone serie diaria para este periodo.
          </p>
        ) : (
          <AreaChart
            data={datos}
            index="fecha"
            categories={[etiqueta]}
            colors={[COLOR[metrica]]}
            valueFormatter={numeroCompacto}
            showLegend={false}
            showAnimation
            startEndOnly
            curveType="monotone"
            className="h-56"
            customTooltip={({ payload, active }) =>
              active && payload?.length ? (
                <div className="rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm">
                  <p className="text-muted-foreground">{payload[0]?.payload?.fecha}</p>
                  <p className="font-medium tabular-nums">
                    {numeroCompleto(Number(payload[0]?.value ?? 0))}
                  </p>
                </div>
              ) : null
            }
          />
        )}
    </SeccionColapsable>
  );
}
