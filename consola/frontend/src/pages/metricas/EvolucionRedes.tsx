/**
 * Evolución por red: barras APILADAS por tramo (día, semana o mes, según lo largo del
 * periodo) — una capa por red social (color), altura = vistas. Cuenta la COMPOSICIÓN y la
 * tendencia: cómo crecen las vistas totales tramo a tramo y qué red las empuja (lo que la
 * tabla "Detalle por red", agregada de todo el periodo, no muestra). Estética del Panorama
 * (panel tematizado).
 *
 * Reúsa la MISMA query que `PiezasConsolidada` (misma `queryKey`): caché compartida, sin
 * coste de API extra.
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import * as React from "react";
import {
  Bar,
  BarChart,
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

/**
 * Granularidad del eje temporal, ADAPTATIVA al span real de fechas: con el rango por
 * defecto (~30 días) la agregación mensual producía 1-2 buckets sin lectura posible.
 * Día si ≤ 45 días; semana (lunes ISO) si ≤ 180; mes si más.
 */
type Granularidad = "dia" | "semana" | "mes";

const DIA_MS = 24 * 60 * 60 * 1000;

/** Una fila = un tramo (día/semana/mes); además de `tramo` (etiqueta) lleva la suma por red. */
interface FilaTramo {
  tramo: string;
  [red: string]: number | string;
}

/** Fecha local de `AAAA-MM-DD`, anclada a mediodía (los cambios de hora no mueven el día). */
function fechaDeISO(iso: string): Date | null {
  const [a, m, d] = (iso || "").split("-").map((n) => parseInt(n, 10));
  if (!a || !m || !d) return null;
  return new Date(a, m - 1, d, 12);
}

/** Inicio del tramo que contiene a `d`: el propio día, su lunes (semana ISO) o el día 1 del mes. */
function inicioTramo(d: Date, gran: Granularidad): Date {
  if (gran === "dia") return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12);
  if (gran === "semana")
    return new Date(d.getFullYear(), d.getMonth(), d.getDate() - ((d.getDay() + 6) % 7), 12);
  return new Date(d.getFullYear(), d.getMonth(), 1, 12);
}

/** Inicio del tramo siguiente (para recorrer el rango rellenando huecos con 0). */
function siguienteTramo(d: Date, gran: Granularidad): Date {
  if (gran === "dia") return new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1, 12);
  if (gran === "semana") return new Date(d.getFullYear(), d.getMonth(), d.getDate() + 7, 12);
  return new Date(d.getFullYear(), d.getMonth() + 1, 1, 12);
}

/** "1 jun" es-MX (sin el punto del mes abreviado). */
function diaMes(d: Date): string {
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short" }).replace(".", "");
}

/** "May 2021" capitalizado a partir de año/mes (0-index). */
function etiquetaMes(anio: number, mes0: number): string {
  const d = new Date(anio, mes0, 1);
  const m = d.toLocaleDateString("es-MX", { month: "short" }).replace(".", "");
  return `${m.charAt(0).toUpperCase()}${m.slice(1)} ${anio}`;
}

/** Etiqueta del tramo según granularidad: "1 jun" · "Sem del 1 jun" · "Jun 2026". */
function etiquetaTramo(d: Date, gran: Granularidad): string {
  if (gran === "dia") return diaMes(d);
  if (gran === "semana") return `Sem del ${diaMes(d)}`;
  return etiquetaMes(d.getFullYear(), d.getMonth());
}

/** Tooltip (tematizado): desglose por red del tramo + total. */
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

  // MISMA queryKey que PiezasConsolidada => caché compartida (sin coste extra). El Panorama
  // ya NO comparte esta query: tiene periodo y queryKey propios.
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-listado", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasPiezasListado({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const piezas = React.useMemo<PiezaListado[]>(() => data?.piezas ?? [], [data]);

  const { filas, redesPresentes } = React.useMemo(() => {
    // Piezas con fecha parseable y vistas finitas, ya con su red canónica.
    const validas = piezas
      .map((p) => {
        const fecha = fechaDeISO(p.publicado);
        if (!fecha || !Number.isFinite(p.visualizaciones)) return null;
        return { fecha, red: redCanonica(p.plataforma) || "otra", vistas: p.visualizaciones };
      })
      .filter((v): v is { fecha: Date; red: string; vistas: number } => v !== null);

    if (validas.length === 0) {
      return { filas: [] as FilaTramo[], redesPresentes: [] as string[] };
    }

    // Granularidad adaptativa según el span real entre la primera y la última pieza.
    let min = validas[0].fecha;
    let max = validas[0].fecha;
    for (const v of validas) {
      if (v.fecha < min) min = v.fecha;
      if (v.fecha > max) max = v.fecha;
    }
    const spanDias = Math.round((max.getTime() - min.getTime()) / DIA_MS);
    const gran: Granularidad = spanDias <= 45 ? "dia" : spanDias <= 180 ? "semana" : "mes";

    // Agrega vistas por (tramo, red). Clave = timestamp del inicio del tramo.
    const porTramo = new Map<number, Record<string, number>>();
    const redes = new Set<string>();
    for (const v of validas) {
      const clave = inicioTramo(v.fecha, gran).getTime();
      redes.add(v.red);
      const fila = porTramo.get(clave) ?? {};
      fila[v.red] = (fila[v.red] ?? 0) + v.vistas;
      porTramo.set(clave, fila);
    }

    // Redes presentes ordenadas (canónicas primero) — orden estable del apilado/leyenda.
    const presentes = Array.from(redes).sort(
      (a, b) => (ORDEN_REDES.indexOf(a) + 1 || 99) - (ORDEN_REDES.indexOf(b) + 1 || 99),
    );

    // Recorre TODOS los tramos del rango (rellena con 0 los vacíos) para una serie continua.
    const out: FilaTramo[] = [];
    const fin = inicioTramo(max, gran).getTime();
    for (let d = inicioTramo(min, gran); d.getTime() <= fin; d = siguienteTramo(d, gran)) {
      const sumas = porTramo.get(d.getTime()) ?? {};
      const fila: FilaTramo = { tramo: etiquetaTramo(d, gran) };
      for (const red of presentes) fila[red] = sumas[red] ?? 0;
      out.push(fila);
    }

    return { filas: out, redesPresentes: presentes };
  }, [piezas]);

  // Muestra ~8 etiquetas de tramo como máximo (interval = nº de categorías a saltar).
  const intervalo = Math.max(0, Math.ceil(filas.length / 8) - 1);

  const contenido = isPending ? (
        <Skeleton className="h-[380px] w-full rounded-xl" />
      ) : isError ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar la evolución por red.
        </p>
      ) : filas.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Aún no hay piezas publicadas en este periodo.
        </p>
      ) : (
        <div className="rounded-xl border border-border bg-card p-6">
          {/* Rótulo de la métrica (título + aclaración honesta) + leyenda, dentro del gráfico. */}
          <div className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-1.5">
            <div className="space-y-1">
              <p className="text-base font-medium leading-none tracking-tight text-foreground">
                Vistas por red
              </p>
              <p className="text-xs text-muted-foreground">Vistas de lo publicado en cada tramo</p>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-0.5">
              {redesPresentes.map((red) => (
                <span
                  key={red}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
                >
                  <span
                    className="h-2.5 w-2.5 rounded-full ring-1 ring-foreground/25"
                    style={{ backgroundColor: colorDe(red) }}
                  />
                  {nombreRed(red)}
                </span>
              ))}
            </div>
          </div>

          {/* Barras (no áreas): son SUMAS DISCRETAS por tramo, no un continuo. */}
          <ResponsiveContainer width="100%" height={288}>
            <BarChart data={filas} margin={{ top: 12, right: 18, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="tramo"
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
                cursor={{ fill: "hsl(var(--muted-foreground))", fillOpacity: 0.08 }}
                content={<TooltipEvolucion />}
              />
              {redesPresentes.map((red) => (
                <Bar
                  key={red}
                  dataKey={red}
                  stackId="redes"
                  fill={colorDe(red)}
                  stroke="hsl(var(--foreground))"
                  strokeOpacity={0.25}
                  strokeWidth={1}
                  name={nombreRed(red)}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      );

  if (desnudo) return contenido;
  return (
    <SeccionColapsable
      titulo="Evolución por red"
      icono={BarChart3}
      descripcion="Vistas por tramo (día, semana o mes según el periodo), apiladas por red."
    >
      {contenido}
    </SeccionColapsable>
  );
}
