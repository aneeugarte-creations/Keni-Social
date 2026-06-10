/**
 * Rendimiento del periodo POR SERIE / TIPO (Item C).
 *
 * Metricool no clasifica los posts; este bloque cruza las piezas del periodo con el
 * `contenido` de la BD (enlace por `id_post_metricool`; fallback fuzzy por título) para
 * agrupar el rendimiento por tipo de contenido y por las clases de etiqueta editorial
 * (campaña / vertical / tipo). Un tab por EJE; cada eje pinta el engagement promedio por
 * pieza de cada grupo (media simple de porcentajes, como lo agrega el backend).
 *
 * Honestidad: muestra cuántas piezas se enlazaron por id vs. por título (heurístico) vs.
 * sin enlace (caen en "Sin clasificar"), para que nadie lea la gráfica como autoritativa
 * cuando el enlace con la BD es parcial.
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart, type CustomTooltipProps } from "@tremor/react";
import { Layers } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { numeroCompacto, numeroCompleto, plural, porcentaje } from "@/lib/formato";
import type { SeriePorEtiqueta } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";

export function GraficaPorSerie({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Marca global del dashboard: la gráfica la sigue. */
  marcaActual?: string;
  /** Rango global del dashboard: el periodo analizado. */
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-por-etiqueta", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasPiezasPorEtiqueta({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    // 2 min: al cambiar marca/rango se repinta pronto sin re-pegar en cada toque.
    staleTime: 2 * 60_000,
  });

  // Tab inicial = el primer eje de la respuesta. Si el tab elegido por el usuario ya no
  // existe en los datos (cambio de marca/rango), caemos al inicial SIN efecto: se deriva
  // en render, evitando un estado huérfano que dejaría los tabs sin contenido.
  const ejeInicial = React.useMemo(() => data?.series[0]?.eje ?? "", [data]);
  const [tab, setTab] = React.useState("");
  const tabValido = data?.series.some((s) => s.eje === tab) ? tab : ejeInicial;

  return (
    <SeccionColapsable
      titulo="Rendimiento por serie y tipo"
      descripcion="Engagement promedio por pieza del periodo, agrupado por la clasificación editorial de cada pieza (cruce con el tablero por id de Metricool; título como respaldo)."
      icono={Layers}
    >
      {isPending ? (
          <Skeleton className="mt-2 h-72 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No se pudo cargar la analítica por serie.
          </p>
        ) : data.total === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Sin piezas en este periodo.
          </p>
        ) : (
          <>
            <Tabs value={tabValido} onValueChange={setTab}>
              <TabsList className="flex-wrap">
                {data.series.map((s) => (
                  <TabsTrigger key={s.eje} value={s.eje}>
                    {s.etiqueta}
                  </TabsTrigger>
                ))}
              </TabsList>
              {data.series.map((s) => (
                <TabsContent key={s.eje} value={s.eje}>
                  <SerieChart serie={s} />
                </TabsContent>
              ))}
            </Tabs>
            <Cobertura
              total={data.total}
              enlazadas={data.enlazadas}
              enlazadasTitulo={data.enlazadas_titulo}
              sinEnlace={data.sin_enlace}
            />
          </>
        )}
    </SeccionColapsable>
  );
}

/** Tooltip del grupo: engagement promedio por pieza, nº de piezas y vistas del grupo. */
function TooltipGrupo({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const dato = payload[0]?.payload as
    | { "Engagement %": number; n: number; vistas: number }
    | undefined;
  if (!dato) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="mb-1 font-medium">{String(label ?? "")}</p>
      <ul className="space-y-0.5">
        <li className="flex items-center gap-3 text-muted-foreground">
          Engagement
          <span className="ml-auto tabular-nums text-foreground">
            {porcentaje(dato["Engagement %"])}
          </span>
        </li>
        <li className="flex items-center gap-3 text-muted-foreground">
          Piezas
          <span className="ml-auto tabular-nums text-foreground">
            {plural(dato.n, "pieza")}
          </span>
        </li>
        <li className="flex items-center gap-3 text-muted-foreground">
          Vistas
          <span className="ml-auto tabular-nums text-foreground">
            {numeroCompleto(dato.vistas)}
          </span>
        </li>
      </ul>
    </div>
  );
}

function SerieChart({ serie }: { serie: SeriePorEtiqueta }) {
  if (serie.grupos.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        Sin grupos para este eje.
      </p>
    );
  }
  // La etiqueta del eje incluye el n del grupo para no leer barras de 1 pieza como
  // autoritativas; el tooltip repite n + vistas con el número completo.
  const datos = serie.grupos.map((g) => ({
    grupo: `${g.valor} (${g.n})`,
    "Engagement %": g.engagement_pct,
    n: g.n,
    vistas: g.visualizaciones,
  }));
  return (
    <div className="space-y-2 pt-2">
      <BarChart
        data={datos}
        index="grupo"
        categories={["Engagement %"]}
        colors={["emerald"]}
        valueFormatter={(v) => porcentaje(v)}
        customTooltip={TooltipGrupo}
        showLegend={false}
        showAnimation
        className="h-56"
      />
      <p className="text-xs text-muted-foreground">
        {serie.grupos.map((g, i) => (
          <span key={g.valor}>
            {i > 0 && " · "}
            <span className="font-medium text-foreground">{g.valor}</span>: {g.n}{" "}
            {g.n === 1 ? "pieza" : "piezas"}, {numeroCompacto(g.visualizaciones)} vistas
          </span>
        ))}
      </p>
    </div>
  );
}

function Cobertura({
  total,
  enlazadas,
  enlazadasTitulo,
  sinEnlace,
}: {
  total: number;
  enlazadas: number;
  enlazadasTitulo: number;
  sinEnlace: number;
}) {
  return (
    <p className="text-xs text-muted-foreground">
      {total} piezas · {enlazadas} vinculadas al tablero
      {enlazadasTitulo > 0 && ` · ${enlazadasTitulo} por título (aproximado)`}
      {sinEnlace > 0 && ` · ${sinEnlace} sin clasificar`}
    </p>
  );
}
