/**
 * Comparativa visual por cuenta/marca con Tremor.
 *
 * - BarChart: visualizaciones vs interacciones por cuenta (escala compacta).
 * - DonutChart: reparto de visualizaciones entre cuentas.
 *
 * Los ejes y tooltips usan los formateadores es-MX para que los números grandes
 * se lean como "221.6 M" en lugar de notación cruda.
 */
import { BarChart, type CustomTooltipProps, DonutChart, Legend } from "@tremor/react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CuentaMetrica } from "@/types";

import { numeroCompacto, numeroCompleto } from "./formato";

export function GraficaMarcas({ cuentas }: { cuentas: CuentaMetrica[] }) {
  // Una entrada por cuenta. Acortamos nombres muy largos para el eje.
  const datosBarras = cuentas.map((c) => ({
    marca: c.marca,
    Visualizaciones: c.visualizaciones,
    Interacciones: c.interacciones,
  }));

  const datosDona = cuentas.map((c) => ({
    marca: c.marca,
    visualizaciones: c.visualizaciones,
  }));

  if (cuentas.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Comparativa por marca</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="py-8 text-center text-sm text-muted-foreground">
            No hay cuentas para mostrar en este rango.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
      <Card className="lg:col-span-3">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Visualizaciones e interacciones por cuenta</CardTitle>
        </CardHeader>
        <CardContent>
          <BarChart
            className="h-72"
            data={datosBarras}
            index="marca"
            categories={["Visualizaciones", "Interacciones"]}
            colors={["blue", "slate"]}
            valueFormatter={numeroCompacto}
            yAxisWidth={56}
            showAnimation
            noDataText="Sin datos para este rango."
            customTooltip={TooltipBarras}
          />
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Reparto de visualizaciones</CardTitle>
        </CardHeader>
        <CardContent>
          <DonutChart
            className="mx-auto h-52"
            data={datosDona}
            category="visualizaciones"
            index="marca"
            colors={["blue", "sky", "cyan", "indigo", "slate", "zinc"]}
            valueFormatter={numeroCompacto}
            showAnimation
            noDataText="Sin datos para este rango."
          />
          <Legend
            className="mt-4 justify-center"
            categories={datosDona.map((d) => d.marca)}
            colors={["blue", "sky", "cyan", "indigo", "slate", "zinc"]}
          />
        </CardContent>
      </Card>
    </div>
  );
}

/** Tooltip de la gráfica de barras con valores completos es-MX. */
function TooltipBarras({ payload, active, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-popover-foreground shadow-md">
      <p className="mb-1 text-sm font-medium">{String(label ?? "")}</p>
      <ul className="space-y-1">
        {payload.map((item, i) => (
          <li key={i} className="flex items-center gap-2 text-xs">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: colorTooltip(String(item.dataKey ?? "")) }}
            />
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

/** Mapa de las categorías de la gráfica a su hex para el punto del tooltip. */
function colorTooltip(dataKey: string): string {
  switch (dataKey) {
    case "Visualizaciones":
      return "#3b82f6";
    case "Interacciones":
      return "#64748b";
    default:
      return "#9ca3af";
  }
}
