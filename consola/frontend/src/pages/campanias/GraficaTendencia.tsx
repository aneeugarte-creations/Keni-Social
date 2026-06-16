/**
 * Tendencia diaria de una CAMPAÑA: por día, visualizaciones o interacciones de las
 * piezas publicadas ese día (conmutable). Cada pieza se atribuye a su día de
 * publicación, así la suma de la serie cuadra con el total de los KPIs.
 *
 * Usa Tremor (mismo stack que Métricas) y los formateadores compactos es-MX. Recibe los
 * puntos ya calculados por el backend (`/api/campanias/{id}/analitica`), no
 * vuelve a pegar a la fuente.
 */
import { AreaChart } from "@tremor/react";
import { LineChart as LineChartIcon } from "lucide-react";
import * as React from "react";

import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { numeroCompacto, numeroCompleto } from "@/lib/formato";
import type { PuntoTendenciaCampania } from "@/types";

import { fechaCorta } from "./formato";

type Metrica = "visualizaciones" | "interacciones";

const ETIQUETA: Record<Metrica, string> = {
  visualizaciones: "Vistas",
  interacciones: "Interacciones",
};
const COLOR: Record<Metrica, string> = { visualizaciones: "orange", interacciones: "violet" };

export function GraficaTendencia({ puntos }: { puntos: PuntoTendenciaCampania[] }) {
  const [metrica, setMetrica] = React.useState<Metrica>("visualizaciones");
  const etiqueta = ETIQUETA[metrica];
  const datos = puntos.map((p) => ({ fecha: fechaCorta(p.fecha), [etiqueta]: p[metrica] }));

  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <LineChartIcon className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-medium">Tendencia diaria</h3>
          </div>
          <Select value={metrica} onValueChange={(v) => setMetrica(v as Metrica)}>
            <SelectTrigger className="w-[150px] sm:w-[170px]" aria-label="Métrica de la tendencia">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="visualizaciones">Vistas</SelectItem>
              <SelectItem value="interacciones">Interacciones</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {datos.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No hay piezas con estos hashtags en el periodo.
          </p>
        ) : (
          <AreaChart
            data={datos}
            index="fecha"
            categories={[etiqueta]}
            colors={[COLOR[metrica]]}
            valueFormatter={numeroCompacto}
            showLegend={false}
            showAnimation
            startEndOnly
            curveType="monotone"
            className="h-56"
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
