/**
 * Tendencia diaria del periodo: evolución día a día de vistas o interacciones.
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
import { useVistaConfig } from "./vistaConfig";
import { SeccionColapsable } from "./SeccionColapsable";

type Metrica = "visualizaciones" | "interacciones";

const ETIQUETA: Record<Metrica, string> = {
  visualizaciones: "Vistas",
  interacciones: "Interacciones",
};
const COLOR: Record<Metrica, string> = { visualizaciones: "orange", interacciones: "violet" };
/** Punto de color del tooltip, coherente con `COLOR` (Tremor) y con METRICAS. */
const PUNTO: Record<Metrica, string> = {
  visualizaciones: "bg-orange-500",
  interacciones: "bg-violet-500",
};

/** "12 may" a partir de una fecha ISO (AAAA-MM-DD), en es-MX. */
function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(d);
}

/**
 * Rellena los huecos del calendario entre la primera y la última fecha de la serie.
 *
 * Es un flujo diario: un día ausente es un día sin actividad (un 0 real), no un dato
 * perdido, así que emitimos 0 para que la gráfica no "cosa" días no contiguos.
 */
function rellenarHuecos(puntos: PuntoSerie[]): PuntoSerie[] {
  if (puntos.length < 2) return puntos;
  const ordenados = [...puntos].sort((a, b) => a.fecha.localeCompare(b.fecha));
  const porFecha = new Map(ordenados.map((p) => [p.fecha, p]));
  const cursor = new Date(`${ordenados[0].fecha}T00:00:00Z`);
  const fin = new Date(`${ordenados[ordenados.length - 1].fecha}T00:00:00Z`);
  if (Number.isNaN(cursor.getTime()) || Number.isNaN(fin.getTime())) return ordenados;
  const completos: PuntoSerie[] = [];
  while (cursor.getTime() <= fin.getTime()) {
    const iso = cursor.toISOString().slice(0, 10);
    completos.push(porFecha.get(iso) ?? { fecha: iso, visualizaciones: 0, interacciones: 0 });
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return completos;
}

export function TendenciaDiaria({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);
  const [metrica, setMetrica] = React.useState<Metrica>("visualizaciones");

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "tendencia", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) => api.metricasTendencia({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    // 2 min: el conmutador de métrica/marca no debe re-pegar a la fuente en cada cambio,
    // pero tampoco queremos serie rancia; "Actualizar" invalida igualmente.
    staleTime: 2 * 60_000,
  });

  const etiqueta = ETIQUETA[metrica];
  const puntos = React.useMemo(() => rellenarHuecos(data?.puntos ?? []), [data?.puntos]);
  const datos = puntos.map((p) => ({
    fecha: fechaCorta(p.fecha),
    [etiqueta]: p[metrica],
  }));
  const suma = puntos.reduce((s, p) => s + p[metrica], 0);

  return (
    <SeccionColapsable
      id="tendencia"
      titulo="Tendencia diaria"
      icono={LineChartIcon}
      acciones={
        <Select value={metrica} onValueChange={(v) => setMetrica(v as Metrica)}>
          <SelectTrigger className="w-[150px] sm:w-[170px]" aria-label="Métrica de la tendencia">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="visualizaciones">Vistas</SelectItem>
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
            Aún no hay datos día a día para este periodo
          </p>
        ) : (
          <div
            role="img"
            aria-label={`Tendencia diaria de ${etiqueta}: ${datos.length} días, total ${numeroCompleto(suma)}`}
          >
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
                  <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
                    <p className="text-muted-foreground">{payload[0]?.payload?.fecha}</p>
                    <p className="flex items-center gap-2 font-medium tabular-nums">
                      <span
                        className={`inline-block h-2 w-2 shrink-0 rounded-full ${PUNTO[metrica]}`}
                        aria-hidden
                      />
                      {etiqueta}: {numeroCompleto(Number(payload[0]?.value ?? 0))}
                    </p>
                  </div>
                ) : null
              }
            />
          </div>
        )}
    </SeccionColapsable>
  );
}
