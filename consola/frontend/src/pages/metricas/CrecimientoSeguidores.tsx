/**
 * Crecimiento de seguidores del periodo (estrategia digital).
 *
 * Pinta la evolución día a día del total de seguidores (LineChart de Tremor con
 * `autoMinValue`: es una serie de NIVEL, así que el eje truncado es legítimo y evita la
 * línea "plana") con opción de desglosar por red. El neto del periodo (`neto` global +
 * `neto_por_red`) se muestra como KPIs arriba. Si la fuente activa no expone seguidores
 * (`puntos=[]`) lo dice con honestidad en vez de inventar una serie; una red sin datos
 * en el periodo no se pinta como serie (su ausencia queda explicada con "—" en los KPIs).
 */
import { useQuery } from "@tanstack/react-query";
import { LineChart } from "@tremor/react";
import { Users } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { nombreRed, numeroCompacto, numeroCompleto, REDES_CANONICAS } from "@/lib/formato";
import type { PuntoSeguidores } from "@/types";

import { colorDe } from "./coloresRed";
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

  // Redes canónicas CON al menos un punto en el periodo (orden canónico fijo). Las
  // ausentes no se pintan como serie: su ausencia ya queda explicada con "—" en los KPIs.
  const redesConDatos = React.useMemo(() => {
    const puntos = data?.puntos ?? [];
    return REDES_CANONICAS.filter((red) => puntos.some((p) => p.por_red[red] != null));
  }, [data]);

  // Categorías legibles para la leyenda/serie: cada id de red → su nombre de marca.
  // Re-mapeamos las claves de `por_red` a ese nombre para que el chart use la etiqueta
  // legible como serie (no el id crudo). Un día sin dato para una red es `null` (hueco
  // honesto en la línea), NUNCA un 0 inventado (sería un stock de cero seguidores).
  const datos = (data?.puntos ?? []).map((p: PuntoSeguidores) => {
    if (!porRed) return { fecha: fechaCorta(p.fecha), Total: p.total };
    const fila: Record<string, string | number | null> = { fecha: fechaCorta(p.fecha) };
    for (const red of redesConDatos) fila[nombreRed(red)] = p.por_red[red] ?? null;
    return fila;
  });

  const categorias = porRed ? redesConDatos.map(nombreRed) : ["Total"];
  // Color por red SIEMPRE desde la fuente única (coloresRed.ts); los hex están en la
  // safelist de tailwind.config.js para que el JIT no los purgue.
  const colores = porRed ? redesConDatos.map(colorDe) : ["blue"];

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
            disabled={redesConDatos.length === 0}
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
            Aún no hay datos de seguidores para este periodo (la fuente de métricas no los
            entrega).
          </p>
        ) : (
          <>
            <KpisNeto neto={data.neto} netoPorRed={data.neto_por_red} />
            {/* Alternativa textual del chart para lectores de pantalla. */}
            <div
              role="img"
              aria-label={`Seguidores del periodo: neto ${netoSeguidores(data.neto)}`}
            >
              <LineChart
                data={datos}
                index="fecha"
                categories={categorias}
                colors={colores}
                valueFormatter={numeroCompacto}
                showLegend={porRed}
                showAnimation
                startEndOnly
                curveType="monotone"
                autoMinValue
                className="h-56"
              />
            </div>
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
