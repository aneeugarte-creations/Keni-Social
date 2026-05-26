/**
 * Curva temporal de UNA métrica (interacciones o alcance) de una pieza comercial.
 *
 * Cada métrica va en su propia gráfica porque sus escalas difieren mucho (el alcance
 * suele ser 10-20× las interacciones); compartir eje aplastaría la pequeña. Usa
 * Tremor (misma librería que Métricas) y los formateadores compactos es-MX.
 */
import { AreaChart } from "@tremor/react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SnapshotComercial } from "@/types";

import { numeroCompacto, numeroCompleto } from "../metricas/formato";
import { fechaCorta } from "./formato";

export function GraficaSerie({
  serie,
  metrica,
  titulo,
  color,
}: {
  serie: SnapshotComercial[];
  metrica: "interacciones" | "alcance";
  titulo: string;
  color: string;
}) {
  // Un punto por snapshot; la clave de la serie es el propio título (leyenda limpia).
  const datos = serie.map((s) => ({
    fecha: fechaCorta(s.ts),
    [titulo]: s[metrica],
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{titulo}</CardTitle>
      </CardHeader>
      <CardContent>
        {datos.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">Sin datos todavía.</p>
        ) : (
          <AreaChart
            data={datos}
            index="fecha"
            categories={[titulo]}
            colors={[color]}
            valueFormatter={numeroCompacto}
            showLegend={false}
            showAnimation
            startEndOnly
            curveType="monotone"
            className="h-44"
            // Tooltip con el número completo (separadores de miles).
            customTooltip={({ payload, active }) =>
              active && payload?.length ? (
                <div className="rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm">
                  <p className="text-muted-foreground">{payload[0]?.payload?.fecha}</p>
                  <p className="font-medium tabular-nums">
                    {numeroCompleto(Number(payload[0]?.value ?? 0))}
                  </p>
                </div>
              ) : null
            }
          />
        )}
      </CardContent>
    </Card>
  );
}
