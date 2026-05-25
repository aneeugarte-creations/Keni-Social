/**
 * Fila de KPIs: cuatro tarjetas con el total del reporte. Estilo Vercel/Geist:
 * etiqueta gris pequena + numero contenido, sin iconos ni acentos de color.
 */
import { Card, CardContent } from "@/components/ui/card";
import type { TotalMetricas } from "@/types";

import { METRICAS, valorMetrica } from "./metricas-meta";

export function Kpis({ total }: { total: TotalMetricas }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {METRICAS.map((m) => (
        <Card key={m.clave}>
          <CardContent className="space-y-1.5 p-5">
            <p className="text-sm text-muted-foreground">{m.etiqueta}</p>
            <p
              className="truncate text-2xl font-semibold tracking-tight tabular-nums"
              title={m.completo(valorMetrica(total, m.clave))}
            >
              {m.compacto(valorMetrica(total, m.clave))}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
