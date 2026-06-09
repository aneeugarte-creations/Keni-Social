/**
 * Evolución por red: barras APILADAS por mes — una capa por red social (color), altura =
 * alcance (visualizaciones). Cuenta la COMPOSICIÓN y la tendencia: cómo crece el alcance
 * total mes a mes y qué red lo empuja (lo que la tabla "Detalle por red", agregada de todo
 * el periodo, no muestra). Estética del Panorama (panel tematizado, colores neón).
 *
 * Reúsa la MISMA query que `PiezasConsolidada`/`PanoramaPiezas` (misma `queryKey`): caché
 * compartida, sin coste de API extra.
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import * as React from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { marcaParam } from "@/components/comunes/selectores";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { nombreRed, numeroCompacto, numeroCompleto, redCanonica } from "@/lib/formato";
import type { PiezaListado } from "@/types";

import { colorDe } from "./coloresRed";
import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";

/** Orden canónico de redes (color y apilado estables). */
const ORDEN_REDES = ["facebook", "instagram", "tiktok", "youtube", "x"];

/** Una fila = un mes; además de `mes` (etiqueta) lleva la suma por red. */
interface FilaMes {
  mes: string;
  [red: string]: number | string;
}

/** "May 2021" capitalizado a partir de año/mes (0-index). */
function etiquetaMes(anio: number, mes0: number): string {
  const d = new Date(anio, mes0, 1);
  const m = d.toLocaleDateString("es-MX", { month: "short" }).replace(".", "");
  return `${m.charAt(0).toUpperCase()}${m.slice(1)} ${anio}`;
}

/** Tooltip (tematizado): desglose por red del mes + total. */
function TooltipEvolucion(props: {
  active?: boolean;
  label?: string | number;
  payload?: Array<{ dataKey?: string | number; value?: number; color?: string }>;
}) {
  if (!props.active || !props.payload?.length) return null;
  const filas = props.payload.filter((p) => (p.value ?? 0) > 0);
  const total = filas.reduce((s, p) => s + (p.value ?? 0), 0);
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="mb-1 font-medium">{props.label}</p>
      <ul className="space-y-0.5">
        {filas.map((p) => (
          <li key={String(p.dataKey)} className="flex items-center gap-1.5 text-muted-foreground">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: colorDe(String(p.dataKey)) }}
            />
            {nombreRed(String(p.dataKey))}
            <span className="ml-auto pl-3 tabular-nums text-foreground">
              {numeroCompleto(p.value ?? 0)}
            </span>
          </li>
        ))}
        <li className="mt-1 flex items-center gap-1.5 border-t border-border pt-1 font-medium">
          Total
          <span className="ml-auto tabular-nums">{numeroCompleto(total)}</span>
        </li>
      </ul>
    </div>
  );
}

export function EvolucionRedes({
  marcaActual = MARCA_TODAS,
  rangoActual,
  desnudo = false,
}: {
  /** Marca global del dashboard (switch de la barra superior): acota la consulta. */
  marcaActual?: string;
  /** Rango global del dashboard: el periodo del gráfico. */
  rangoActual?: string;
  /** `true` => solo el gráfico, sin el `SeccionColapsable` (título/colapso). */
  desnudo?: boolean;
}) {
  const marca_ = marcaParam(marcaActual);

  // MISMA queryKey que PiezasConsolidada/PanoramaPiezas => caché compartida (sin coste extra).
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-listado", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasPiezasListado({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const piezas = React.useMemo<PiezaListado[]>(() => data?.piezas ?? [], [data]);

  const { filas, redesPresentes } = React.useMemo(() => {
    // Agrega visualizaciones por (mes, red). Clave de mes = AAAA-MM.
    const porMes = new Map<string, Record<string, number>>();
    const redes = new Set<string>();
    let minClave: string | null = null;
    let maxClave: string | null = null;

    for (const p of piezas) {
      const [a, m] = (p.publicado || "").split("-").map((n) => parseInt(n, 10));
      if (!a || !m) continue;
      if (!Number.isFinite(p.visualizaciones)) continue;
      const clave = `${a}-${String(m).padStart(2, "0")}`;
      const red = redCanonica(p.plataforma) || "otra";
      redes.add(red);
      const fila = porMes.get(clave) ?? {};
      fila[red] = (fila[red] ?? 0) + p.visualizaciones;
      porMes.set(clave, fila);
      if (minClave === null || clave < minClave) minClave = clave;
      if (maxClave === null || clave > maxClave) maxClave = clave;
    }

    if (minClave === null || maxClave === null) {
      return { filas: [] as FilaMes[], redesPresentes: [] as string[] };
    }

    // Redes presentes ordenadas (canónicas primero) — orden estable del apilado/leyenda.
    const presentes = Array.from(redes).sort(
      (a, b) => (ORDEN_REDES.indexOf(a) + 1 || 99) - (ORDEN_REDES.indexOf(b) + 1 || 99),
    );

    // Recorre TODOS los meses del rango (rellena con 0 los vacíos) para una serie continua.
    const [aMin, mMin] = minClave.split("-").map((n) => parseInt(n, 10));
    const [aMax, mMax] = maxClave.split("-").map((n) => parseInt(n, 10));
    const out: FilaMes[] = [];
    let yy = aMin;
    let mm = mMin - 1; // 0-index
    while (yy < aMax || (yy === aMax && mm <= mMax - 1)) {
      const clave = `${yy}-${String(mm + 1).padStart(2, "0")}`;
      const sumas = porMes.get(clave) ?? {};
      const fila: FilaMes = { mes: etiquetaMes(yy, mm) };
      for (const red of presentes) fila[red] = sumas[red] ?? 0;
      out.push(fila);
      mm++;
      if (mm > 11) {
        mm = 0;
        yy++;
      }
    }

    return { filas: out, redesPresentes: presentes };
  }, [piezas]);

  // Muestra ~8 etiquetas de mes como máximo (interval = nº de categorías a saltar).
  const intervalo = Math.max(0, Math.ceil(filas.length / 8) - 1);

  const contenido = isPending ? (
        <Skeleton className="h-[380px] w-full rounded-xl" />
      ) : isError ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar la evolución por red.
        </p>
      ) : filas.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Sin piezas con fecha en este periodo.
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card p-4 dark:border-white/5 dark:bg-[#0b0b12]">
          {/* Rótulo de la métrica (título + aclaración honesta) + leyenda, dentro del gráfico. */}
          <div className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-1.5">
            <div className="space-y-1">
              <p className="text-base font-medium leading-none tracking-tight text-foreground">
                Visualizaciones por aplicación
              </p>
              <p className="text-xs text-muted-foreground">Alcance de lo publicado cada mes</p>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-0.5">
              {redesPresentes.map((red) => (
                <span
                  key={red}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
                >
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colorDe(red) }} />
                  {nombreRed(red)}
                </span>
              ))}
            </div>
          </div>

          <ResponsiveContainer width="100%" height={360}>
            <AreaChart data={filas} margin={{ top: 12, right: 18, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="mes"
                interval={intervalo}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: "hsl(var(--border))" }}
              />
              <YAxis
                tickFormatter={(v: number) => numeroCompacto(v)}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={48}
              />
              <Tooltip
                cursor={{ stroke: "hsl(var(--muted-foreground))", strokeOpacity: 0.3 }}
                content={<TooltipEvolucion />}
              />
              {redesPresentes.map((red) => (
                <Area
                  key={red}
                  type="monotone"
                  dataKey={red}
                  stackId="redes"
                  stroke={colorDe(red)}
                  strokeWidth={2}
                  fill={colorDe(red)}
                  fillOpacity={0.3}
                  name={nombreRed(red)}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      );

  if (desnudo) return contenido;
  return (
    <SeccionColapsable titulo="Evolución por red" icono={BarChart3} descripcion="Alcance por mes, apilado por red.">
      {contenido}
    </SeccionColapsable>
  );
}
