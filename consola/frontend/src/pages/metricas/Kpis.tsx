/**
 * Fila de KPIs: cuatro tarjetas grandes con el total del reporte.
 *
 * Usa la tarjeta de shadcn (consistente con el resto de la consola) y tipografía
 * grande para el valor formateado, con un acento de color por métrica.
 */
import { Eye, Heart, type LucideIcon, Sparkles, Users } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { TotalMetricas } from "@/types";

import { METRICAS, valorMetrica } from "./metricas-meta";

/** Icono y acento de color por métrica (clases estáticas para no purgar). */
const ADORNO: Record<string, { icono: LucideIcon; texto: string; fondo: string }> = {
  visualizaciones: {
    icono: Eye,
    texto: "text-orange-600 dark:text-orange-400",
    fondo: "bg-orange-500/10",
  },
  alcance: {
    icono: Users,
    texto: "text-sky-600 dark:text-sky-400",
    fondo: "bg-sky-500/10",
  },
  interacciones: {
    icono: Heart,
    texto: "text-violet-600 dark:text-violet-400",
    fondo: "bg-violet-500/10",
  },
  engagement_pct: {
    icono: Sparkles,
    texto: "text-emerald-600 dark:text-emerald-400",
    fondo: "bg-emerald-500/10",
  },
};

export function Kpis({ total }: { total: TotalMetricas }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {METRICAS.map((m) => {
        const adorno = ADORNO[m.clave];
        const Icono = adorno.icono;
        return (
          <Card key={m.clave} className="overflow-hidden">
            <CardContent className="flex items-start justify-between gap-3 p-5">
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium text-muted-foreground">{m.etiqueta}</p>
                <p
                  className="truncate text-3xl font-semibold tracking-tight"
                  title={m.completo(valorMetrica(total, m.clave))}
                >
                  {m.compacto(valorMetrica(total, m.clave))}
                </p>
              </div>
              <div
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                  adorno.fondo,
                  adorno.texto,
                )}
              >
                <Icono className="h-5 w-5" />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
