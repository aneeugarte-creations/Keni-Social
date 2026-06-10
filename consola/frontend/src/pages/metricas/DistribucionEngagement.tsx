/**
 * Distribución del engagement de las piezas del periodo (estadísticas del servidor).
 *
 * Consume `GET /api/metricas/piezas` (AnaliticaPiezas): el backend ya calcula sobre
 * TODAS las piezas del periodo el resumen estadístico (n, mediana, p25/p75, mín/máx,
 * desviación) del engagement y de las vistas, además del histograma por tramos. Es el
 * complemento de la tabla consolidada de abajo: aquélla resume el conjunto FILTRADO
 * client-side; esto, el universo completo que el cliente no puede recalcular.
 *
 * Mismo stack (Tremor) y estados honestos (carga / vacío / error) que el resto de
 * Métricas. Los campos `null` de las estadísticas se muestran como "—" (sin base de
 * cálculo; la desviación necesita n>=2): la UI distingue "0" de "sin dato".
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart, type CustomTooltipProps } from "@tremor/react";
import { SigmaSquare } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { numeroCompacto, numeroCompleto, plural, porcentaje } from "@/lib/formato";
import type { AnaliticaPiezas } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";

/** Punto de color del tooltip, coherente con el `emerald` del BarChart (Tremor). */
const PUNTO = "bg-emerald-500";

/** Porcentaje es-MX, o "—" si el campo es `null` (sin base de cálculo). */
function pct(v: number | null): string {
  return v == null ? "—" : porcentaje(v);
}

/** Número compacto es-MX, o "—" si el campo es `null` (sin base de cálculo). */
function compacto(v: number | null): string {
  return v == null ? "—" : numeroCompacto(v);
}

export function DistribucionEngagement({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasPiezas({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    // 2 min: mismo criterio que el resto de secciones de Métricas; el botón
    // "Actualizar" invalida igualmente.
    staleTime: 2 * 60_000,
  });

  return (
    <SeccionColapsable
      titulo="Distribución del engagement"
      icono={SigmaSquare}
      descripcion="Cómo se reparten las piezas del periodo según su tasa de engagement, con los percentiles del conjunto calculados en el servidor sobre TODAS las piezas (la tabla de abajo, en cambio, refleja tus filtros)."
    >
      {isPending ? (
        <Skeleton className="h-72 w-full rounded-lg" />
      ) : isError || !data ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar la distribución de engagement.
        </p>
      ) : data.total === 0 || data.distribucion.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Sin piezas en este periodo.
        </p>
      ) : (
        <Cuerpo data={data} />
      )}
    </SeccionColapsable>
  );
}

/** Contenido del estado con datos: KPIs del servidor + histograma + línea de vistas. */
function Cuerpo({ data }: { data: AnaliticaPiezas }) {
  const e = data.engagement;
  const v = data.visualizaciones;
  const datos = data.distribucion.map((b) => ({ tramo: b.etiqueta, Piezas: b.n }));
  // Alternativa textual del histograma (lectores de pantalla): total + tramo a tramo.
  const resumen = `Distribución del engagement de ${numeroCompleto(data.total)} piezas: ${data.distribucion
    .map((b) => `${b.etiqueta}: ${b.n}`)
    .join(", ")}`;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <TarjetaKpi etiqueta="Piezas" valor={numeroCompleto(e.n)} />
        <TarjetaKpi
          etiqueta="Mediana"
          valor={pct(e.mediana)}
          titulo={`Mediana: ${pct(e.mediana)} · Desviación típica: ${
            e.desviacion == null ? "—" : porcentaje(e.desviacion)
          }`}
        />
        <TarjetaKpi etiqueta="p25 – p75" valor={`${pct(e.p25)} – ${pct(e.p75)}`} />
        <TarjetaKpi etiqueta="Mín – Máx" valor={`${pct(e.minimo)} – ${pct(e.maximo)}`} />
      </div>

      <div role="img" aria-label={resumen}>
        <BarChart
          className="h-56"
          data={datos}
          index="tramo"
          categories={["Piezas"]}
          colors={["emerald"]}
          valueFormatter={numeroCompleto}
          showLegend={false}
          showAnimation
          customTooltip={(props) => <TooltipTramo {...props} />}
        />
      </div>

      <p className="text-sm text-muted-foreground">
        Vistas por pieza: mediana {compacto(v.mediana)} · p25 {compacto(v.p25)} · p75{" "}
        {compacto(v.p75)} · mín {compacto(v.minimo)} · máx {compacto(v.maximo)}
      </p>
    </div>
  );
}

/** Tooltip del histograma: tramo + conteo pluralizado ("12 piezas") es-MX. */
function TooltipTramo({ payload, active, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-popover-foreground shadow-md">
      <p className="mb-1 text-sm font-medium">{String(label ?? "")}</p>
      <ul className="space-y-1">
        {payload.map((item, i) => (
          <li key={i} className="flex items-center gap-2 text-xs">
            <span className={`inline-block h-2 w-2 rounded-full ${PUNTO}`} aria-hidden />
            <span className="font-medium tabular-nums">
              {plural(Number(item.value ?? 0), "pieza")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
