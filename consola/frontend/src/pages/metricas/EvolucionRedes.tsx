/**
 * Evolución por red: barras APILADAS por intervalo de tiempo — una capa por red social (color),
 * altura = vistas. Cuenta la COMPOSICIÓN y la tendencia: cómo crecen las vistas totales
 * intervalo a intervalo y qué red las empuja (lo que la tabla "Detalle por red", agregada de todo
 * el periodo, no muestra). El tamaño del intervalo se adapta al periodo real de los datos:
 * día (≤45 días), semana (≤180) o mes. Estética del Panorama (panel tematizado, neón).
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
import { useVistaConfig } from "./vistaConfig";
import { SeccionColapsable } from "./SeccionColapsable";

/** Orden canónico de redes (color y apilado estables). */
const ORDEN_REDES = ["facebook", "instagram", "tiktok", "youtube", "x"];

/** Una fila = un intervalo (día, semana o mes); además de `intervalo` (etiqueta) lleva la suma por red. */
interface FilaIntervalo {
  intervalo: string;
  [red: string]: number | string;
}

/** Tamaño del intervalo de agregación, adaptativo al span real de los datos. */
export type Granularidad = "dia" | "semana" | "mes";

/**
 * Granularidad adaptativa según el span REAL de los datos: con el rango por defecto
 * (~30 días) la agregación mensual daba 1-2 barras; en día/semana sí hay tendencia.
 */
export function granularidadParaSpan(spanDias: number): Granularidad {
  return spanDias <= 45 ? "dia" : spanDias <= 180 ? "semana" : "mes";
}

/** "May 2021" capitalizado a partir de año/mes (0-index). */
function etiquetaMes(anio: number, mes0: number): string {
  const d = new Date(anio, mes0, 1);
  const m = d.toLocaleDateString("es-MX", { month: "short" }).replace(".", "");
  return `${m.charAt(0).toUpperCase()}${m.slice(1)} ${anio}`;
}

/** "1 jun" en es-MX (sin punto del mes abreviado). */
function etiquetaDia(f: Date): string {
  return f.toLocaleDateString("es-MX", { day: "numeric", month: "short" }).replace(".", "");
}

/** `Date` local anclado a MEDIODÍA a partir de "AAAA-MM-DD" (la aritmética de días no deriva). */
function fechaDeISO(iso: string): Date | null {
  const [a, m, d] = (iso || "").split("-").map((n) => parseInt(n, 10));
  if (!a || !m || !d) return null;
  return new Date(a, m - 1, d, 12);
}

/** Inicio del intervalo que contiene `f`: el propio día, su lunes (ISO) o el día 1 del mes. */
function inicioTramo(f: Date, gran: Granularidad): Date {
  if (gran === "mes") return new Date(f.getFullYear(), f.getMonth(), 1, 12);
  if (gran === "semana") {
    const lunes = new Date(f);
    lunes.setDate(lunes.getDate() - ((lunes.getDay() + 6) % 7));
    return lunes;
  }
  return new Date(f);
}

/** Inicio del intervalo SIGUIENTE (para rellenar con 0 los intervalos intermedios vacíos). */
function siguienteTramo(f: Date, gran: Granularidad): Date {
  const d = new Date(f);
  if (gran === "mes") d.setMonth(d.getMonth() + 1);
  else d.setDate(d.getDate() + (gran === "semana" ? 7 : 1));
  return d;
}

/** Etiqueta del intervalo: día → "1 jun"; semana → "Sem del 1 jun"; mes → "Jun 2026". */
export function etiquetaIntervalo(f: Date, gran: Granularidad): string {
  if (gran === "mes") return etiquetaMes(f.getFullYear(), f.getMonth());
  if (gran === "semana") return `Sem del ${etiquetaDia(f)}`;
  return etiquetaDia(f);
}

/** Tooltip (tematizado): desglose por red del intervalo + total. */
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
  const red = useVistaConfig((s) => s.red);

  // MISMA queryKey que PiezasConsolidada => caché compartida (sin coste extra).
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-listado", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasPiezasListado({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const piezas = React.useMemo<PiezaListado[]>(() => data?.piezas ?? [], [data]);

  const { filas, redesPresentes, gran } = React.useMemo(() => {
    // Piezas válidas: con fecha parseable y vistas finitas.
    const validas: Array<{ f: Date; red: string; vistas: number }> = [];
    const redes = new Set<string>();
    for (const p of piezas) {
      const f = fechaDeISO(p.publicado);
      if (!f || !Number.isFinite(p.visualizaciones)) continue;
      const red = redCanonica(p.plataforma) || "otra";
      redes.add(red);
      validas.push({ f, red, vistas: p.visualizaciones });
    }
    if (!validas.length) {
      return {
        filas: [] as FilaIntervalo[],
        redesPresentes: [] as string[],
        gran: "dia" as Granularidad,
      };
    }

    const tiempos = validas.map((v) => v.f.getTime());
    const minT = Math.min(...tiempos);
    const maxT = Math.max(...tiempos);
    const spanDias = Math.round((maxT - minT) / 86_400_000);
    const gran = granularidadParaSpan(spanDias);

    // Agrega vistas por (intervalo, red). Clave = timestamp del inicio del intervalo.
    const porTramo = new Map<number, Record<string, number>>();
    for (const v of validas) {
      const clave = inicioTramo(v.f, gran).getTime();
      const fila = porTramo.get(clave) ?? {};
      fila[v.red] = (fila[v.red] ?? 0) + v.vistas;
      porTramo.set(clave, fila);
    }

    // Redes presentes ordenadas (canónicas primero) — orden estable del apilado/leyenda.
    const presentes = Array.from(redes).sort(
      (a, b) => (ORDEN_REDES.indexOf(a) + 1 || 99) - (ORDEN_REDES.indexOf(b) + 1 || 99),
    );

    // Recorre TODOS los intervalos del rango (rellena con 0 los vacíos) para una serie continua.
    const out: FilaIntervalo[] = [];
    const fin = inicioTramo(new Date(maxT), gran).getTime();
    for (
      let cur = inicioTramo(new Date(minT), gran);
      cur.getTime() <= fin;
      cur = siguienteTramo(cur, gran)
    ) {
      const sumas = porTramo.get(cur.getTime()) ?? {};
      const fila: FilaIntervalo = { intervalo: etiquetaIntervalo(cur, gran) };
      for (const red of presentes) fila[red] = sumas[red] ?? 0;
      out.push(fila);
    }

    return { filas: out, redesPresentes: presentes, gran };
  }, [piezas]);

  // Muestra ~8 etiquetas de intervalo como máximo en el eje X (interval = categorías a saltar).
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
        /* role=img: alternativa textual del chart (resume intervalos, granularidad y redes). */
        <div
          className="rounded-xl border border-border bg-card p-6"
          role="img"
          aria-label={`Vistas por red en ${filas.length} intervalos por ${
            gran === "dia" ? "día" : gran
          }: redes ${redesPresentes.map(nombreRed).join(", ")}`}
        >
          {/* Rótulo de la métrica (título + aclaración honesta) + leyenda, dentro del gráfico. */}
          <div className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-1.5">
            <div className="space-y-1">
              <p className="text-base font-medium leading-none tracking-tight text-foreground">
                Vistas por red
              </p>
              <p className="text-xs text-muted-foreground">
                Por red y intervalo
              </p>
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

          <ResponsiveContainer width="100%" height={288}>
            {/* Barras apiladas (no áreas): son sumas DISCRETAS por intervalo, no un continuo. */}
            <BarChart data={filas} margin={{ top: 12, right: 18, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeOpacity={0.5} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="intervalo"
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
                cursor={{ fill: "hsl(var(--muted-foreground))", fillOpacity: 0.12 }}
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
      descripcion="Por intervalo, apiladas por red."
    >
      {contenido}
    </SeccionColapsable>
  );
}
