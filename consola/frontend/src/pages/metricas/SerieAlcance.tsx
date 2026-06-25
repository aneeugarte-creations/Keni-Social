/**
 * Tendencia de alcance de cuenta del periodo (estrategia digital).
 *
 * El alcance (usuarios ÚNICOS que vieron la cuenta) es un FLUJO diario, no un stock ni un
 * volumen aditivo: por eso se muestra como TENDENCIA (la serie día a día), nunca como una
 * cifra única de periodo —sumar reach diario contaría a la misma persona varias veces—. Solo
 * Instagram expone alcance de cuenta; el resto de redes no lo mide, así que si la fuente no
 * trae serie se dice con honestidad en vez de inventar una línea.
 *
 * Distinto de las IMPRESIONES (volumen, sí aditivo), que son la cifra de cabecera del
 * periodo: aquí se trata el alcance único, complementario.
 */
import { useQuery } from "@tanstack/react-query";
import { LineChart } from "@tremor/react";
import { Radar } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { numeroCompacto } from "@/lib/formato";
import type { PuntoAlcance } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";
import { useVistaConfig } from "./vistaConfig";

/** "12 may" a partir de una fecha ISO (AAAA-MM-DD), en es-MX. */
function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(d);
}

export function SerieAlcance({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "serie-alcance", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasSerieAlcance({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // El alcance de cuenta es un flujo diario; la línea grafica el `total` por día (Instagram
  // es la única red que lo aporta). Un día sin dato es un hueco honesto, no un 0 inventado.
  const datos = (data?.puntos ?? []).map((p: PuntoAlcance) => ({
    fecha: fechaCorta(p.fecha),
    Alcance: p.total,
  }));

  return (
    <Seccion
      id="alcance-serie"
      titulo="Alcance de cuenta"
      icono={Radar}
      descripcion="Usuarios únicos que vieron la cuenta cada día. Es un alcance ÚNICO (solo lo mide Instagram), distinto de las impresiones, que son el volumen total del periodo."
    >
      <Card className="space-y-4 p-4 sm:p-6">
        {isPending ? (
          <Skeleton className="h-56 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No se pudo cargar la serie de alcance.
          </p>
        ) : datos.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No hay alcance de cuenta para este periodo (solo Instagram lo mide).
          </p>
        ) : (
          /* Alternativa textual del chart para lectores de pantalla. */
          <div role="img" aria-label={`Tendencia de alcance de cuenta del periodo (${data.etiqueta_rango})`}>
            <LineChart
              data={datos}
              index="fecha"
              categories={["Alcance"]}
              colors={["sky"]}
              valueFormatter={numeroCompacto}
              showLegend={false}
              showAnimation
              startEndOnly
              curveType="monotone"
              className="h-56"
            />
          </div>
        )}
      </Card>
    </Seccion>
  );
}
