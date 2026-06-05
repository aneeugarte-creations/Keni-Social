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
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { nombreRed, numeroCompacto, numeroCompleto, REDES_CANONICAS } from "@/lib/formato";
import type { PuntoSeguidores } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";

/** Neto de seguidores con signo: es un CONTEO (`+1.2K` / `−5K`), NO un porcentaje. */
function netoSeguidores(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "0";
  return `${n > 0 ? "+" : "−"}${numeroCompacto(Math.abs(n))}`;
}

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

  // Siempre las 5 redes canónicas en orden fijo (facebook, instagram, tiktok, youtube, x),
  // aunque alguna no aporte datos: no se omite ninguna red de la vista.
  const redes = React.useMemo(() => [...REDES_CANONICAS], []);

  // Categorías legibles para la leyenda/serie: cada id de red → su nombre de marca.
  // Re-mapeamos las claves de `por_red` a ese nombre para que el chart use la etiqueta
  // legible como serie (no el id crudo).
  const datos = (data?.puntos ?? []).map((p: PuntoSeguidores) => {
    if (!porRed) return { fecha: fechaCorta(p.fecha), Total: p.total };
    const fila: Record<string, string | number> = { fecha: fechaCorta(p.fecha) };
    for (const red of redes) fila[nombreRed(red)] = p.por_red[red] ?? 0;
    return fila;
  });

  const categorias = porRed ? redes.map(nombreRed) : ["Total"];
  const colores = porRed ? COLORES_RED.slice(0, redes.length) : ["blue"];

  return (
    <SeccionColapsable
      titulo="Crecimiento de seguidores"
      icono={Users}
      acciones={
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch
            checked={porRed}
            onCheckedChange={setPorRed}
            aria-label="Desglosar por red"
            disabled={redes.length === 0}
          />
          Por red
        </label>
      }
      contentClassName="space-y-4"
    >
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
    </SeccionColapsable>
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
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      <TarjetaKpi
        etiqueta="Neto del periodo"
        valor={netoSeguidores(neto)}
        titulo={`${numeroCompleto(neto)} seguidores`}
      />
      {REDES_CANONICAS.map((red) => {
        // Distinguimos "red ausente" (no está en neto_por_red → "—") de un neto real de 0
        // (la red existe pero no ganó/perdió → "0"). Usamos la presencia de la clave.
        const presente = Object.prototype.hasOwnProperty.call(netoPorRed, red);
        const valor = presente ? netoPorRed[red] : null;
        return (
          <TarjetaKpi
            key={red}
            etiqueta={nombreRed(red)}
            valor={valor === null ? "—" : netoSeguidores(valor)}
            titulo={
              valor === null
                ? "Sin datos para este periodo"
                : `${numeroCompleto(valor)} seguidores`
            }
          />
        );
      })}
    </div>
  );
}
