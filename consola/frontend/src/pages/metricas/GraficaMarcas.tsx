/**
 * Comparativa visual por marca con Tremor.
 *
 * - BarChart: UNA métrica a la vez (vistas o interacciones, conmutable) por marca,
 *   con su propia escala — superponer ambas con escalas tan dispares engañaría.
 * - Reparto: lista ordenada con barras de progreso (en lugar de una dona
 *   multicolor), coherente con el sistema de diseño monocromo (estilo Vercel).
 *
 * Los ejes y tooltips usan los formateadores es-MX para que los números grandes
 * se lean como "221.6 M" en lugar de notación cruda.
 */
import { BarChart, type CustomTooltipProps } from "@tremor/react";
import * as React from "react";
import type { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { numeroCompacto, numeroCompleto } from "@/lib/formato";
import type { CuentaMetrica } from "@/types";

import { SeccionColapsable } from "./SeccionColapsable";

type Metrica = "visualizaciones" | "interacciones";

const ETIQUETA: Record<Metrica, string> = {
  visualizaciones: "Vistas",
  interacciones: "Interacciones",
};
/** Colores por métrica (nombres Tremor), los mismos de METRICAS en metricas-meta. */
// OJO: aquí el color codifica la MÉTRICA (no la red); la paleta por red (coloresRed.ts) no aplica.
const COLOR: Record<Metrica, "orange" | "violet"> = {
  visualizaciones: "orange",
  interacciones: "violet",
};
/** Punto de color del tooltip, coherente con `COLOR`. */
const PUNTO: Record<Metrica, string> = {
  visualizaciones: "bg-orange-500",
  interacciones: "bg-violet-500",
};

/**
 * Porcentajes enteros que suman EXACTAMENTE 100 (redondeo por mayor resto):
 * floor de cada exacto y el sobrante repartido de uno en uno a las mayores fracciones.
 */
function porcentajesMayorResto(valores: number[]): number[] {
  const total = valores.reduce((s, v) => s + v, 0);
  if (total <= 0) return valores.map(() => 0);
  const exactos = valores.map((v) => (v * 100) / total);
  const pisos = exactos.map(Math.floor);
  let resto = 100 - pisos.reduce((s, p) => s + p, 0);
  const porFraccion = exactos
    .map((e, i) => ({ fraccion: e - pisos[i], i }))
    .sort((a, b) => b.fraccion - a.fraccion || a.i - b.i);
  for (const { i } of porFraccion) {
    if (resto <= 0) break;
    pisos[i] += 1;
    resto -= 1;
  }
  return pisos;
}

export function GraficaMarcas({
  cuentas,
  desnudo = false,
}: {
  cuentas: CuentaMetrica[];
  /** `true` => solo las gráficas, sin el `SeccionColapsable` (título/colapso). */
  desnudo?: boolean;
}) {
  const [metrica, setMetrica] = React.useState<Metrica>("visualizaciones");
  const etiqueta = ETIQUETA[metrica];

  // Una entrada por marca, con la métrica activa como única categoría.
  const datosBarras = cuentas.map((c) => ({
    marca: c.marca,
    [etiqueta]: c[metrica],
  }));

  // Alternativa textual del chart: hasta 5 marcas con su valor + "y N más" si hay más.
  const top5 = cuentas
    .slice(0, 5)
    .map((c) => `${c.marca} ${numeroCompacto(c[metrica])}`)
    .join(", ");
  const resumen = cuentas.length > 5 ? `${top5} y ${cuentas.length - 5} más` : top5;

  const ordenadas = [...cuentas].sort((a, b) => b.visualizaciones - a.visualizaciones);
  const pcts = porcentajesMayorResto(ordenadas.map((c) => c.visualizaciones));
  const datosReparto = ordenadas.map((c, i) => ({
    marca: c.marca,
    visualizaciones: c.visualizaciones,
    pct: pcts[i],
  }));

  const envolver = (hijo: ReactNode) =>
    desnudo ? (
      hijo
    ) : (
      <SeccionColapsable titulo="Comparativa por marca" sinCaja>
        {hijo}
      </SeccionColapsable>
    );

  if (cuentas.length === 0) {
    return envolver(
      <p className="py-8 text-center text-sm text-muted-foreground">
        No hay marcas para mostrar en este periodo.
      </p>,
    );
  }

  return envolver(
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
      <Card className="lg:col-span-3">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Título dinámico: la gráfica enseña UNA métrica a la vez (la del Select). */}
            <CardTitle className="text-base">Por marca</CardTitle>
            <Select value={metrica} onValueChange={(v) => setMetrica(v as Metrica)}>
              <SelectTrigger className="w-[170px]" aria-label="Métrica de la comparativa">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="visualizaciones">Vistas</SelectItem>
                <SelectItem value="interacciones">Interacciones</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {/* Alternativa textual del chart para lectores de pantalla (resumen con datos). */}
          <div role="img" aria-label={`${etiqueta} por marca: ${resumen}`}>
            <BarChart
              className="h-72"
              data={datosBarras}
              index="marca"
              categories={[etiqueta]}
              colors={[COLOR[metrica]]}
              valueFormatter={numeroCompacto}
              yAxisWidth={56}
              showAnimation
              noDataText="Sin datos para este periodo."
              customTooltip={(props) => <TooltipBarras {...props} punto={PUNTO[metrica]} />}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Reparto de vistas</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-4">
            {datosReparto.map((it) => (
              <li key={it.marca}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-sm text-foreground">{it.marca}</span>
                  <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                    {numeroCompacto(it.visualizaciones)}
                    <span className="ml-1.5 text-xs text-muted-foreground">{it.pct}%</span>
                  </span>
                </div>
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-orange-500 transition-all dark:bg-orange-400"
                    style={{ width: `${it.pct}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      </div>,
  );
}

/** Tooltip de la gráfica de barras con valores completos es-MX. */
function TooltipBarras({
  payload,
  active,
  label,
  punto,
}: CustomTooltipProps & { punto: string }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-popover-foreground shadow-md">
      <p className="mb-1 text-sm font-medium">{String(label ?? "")}</p>
      <ul className="space-y-1">
        {payload.map((item, i) => (
          <li key={i} className="flex items-center gap-2 text-xs">
            <span className={`inline-block h-2 w-2 rounded-full ${punto}`} aria-hidden />
            <span className="text-muted-foreground">{item.name}</span>
            <span className="ml-auto font-medium tabular-nums">
              {numeroCompleto(Number(item.value ?? 0))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
