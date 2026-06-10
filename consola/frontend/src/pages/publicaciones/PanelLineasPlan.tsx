/**
 * Producción del día por LÍNEA del plan (generados · publicados / objetivo), para la marca
 * activa. Vive en la página de PROGRAMACIÓN (es el pulso del plan que alimenta la parrilla);
 * se oculta solo si la marca no tiene plan o no hay marca activa.
 */
import { useQuery } from "@tanstack/react-query";
import { Target } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// Etiquetas legibles de las líneas del plan editorial (fallback: la categoría capitalizada).
const ETIQUETA_LINEA: Record<string, string> = {
  mx: "Nacional",
  internacional: "Internacional",
  breaking: "Breaking",
  entretenimiento: "Entretenimiento",
  evergreen: "Evergreen",
};

/** Producción del día por LÍNEA del plan (producido vs objetivo), para la marca activa. */
export function PanelLineasPlan({ marca, nombre }: { marca: string; nombre: string }) {
  const produccion = useQuery({
    queryKey: ["produccion", "dia", marca],
    queryFn: ({ signal }) => api.produccionDia(marca, signal),
    refetchInterval: 60_000,
  });
  const lineas = produccion.data?.por_categoria ?? [];
  if (!produccion.data || lineas.length === 0) return null;
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Target className="h-4 w-4 text-emerald-600" />
          Producción del día por línea
          <Badge variant="outline" className="text-[10px]">
            {nombre}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-2">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {lineas.map((l) => {
            const completo = l.objetivo != null && l.generados >= l.objetivo;
            const exceso = l.objetivo != null && l.generados > l.objetivo;
            return (
              <div key={l.categoria} className="rounded-lg border border-border/60 p-3">
                <div className="text-xs text-muted-foreground">
                  {ETIQUETA_LINEA[l.categoria] ??
                    l.categoria.charAt(0).toUpperCase() + l.categoria.slice(1)}
                </div>
                {/* Los TRES números de la línea: generados · publicados / objetivo. */}
                <div
                  className={cn(
                    "mt-1 text-lg font-semibold tabular-nums",
                    exceso ? "text-amber-600" : completo ? "text-emerald-600" : undefined,
                  )}
                >
                  {l.generados}
                  <span className="text-sm font-normal text-muted-foreground">
                    {l.objetivo != null ? ` / ${l.objetivo}` : " (fuera de plan)"}
                  </span>
                </div>
                <div className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">
                  {l.publicados} publicado{l.publicados === 1 ? "" : "s"}
                </div>
                {l.objetivo != null && (
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                    {/* Barra doble: generados (claro) y, encima, publicados (sólido). */}
                    <div className="relative h-full">
                      <div
                        className={cn(
                          "absolute inset-y-0 left-0 rounded-full",
                          exceso ? "bg-amber-500/40" : completo ? "bg-emerald-500/40" : "bg-sky-500/40",
                        )}
                        style={{
                          width: `${Math.min(100, (l.generados / Math.max(1, l.objetivo)) * 100)}%`,
                        }}
                      />
                      <div
                        className={cn(
                          "absolute inset-y-0 left-0 rounded-full",
                          exceso ? "bg-amber-500" : completo ? "bg-emerald-500" : "bg-sky-500",
                        )}
                        style={{
                          width: `${Math.min(100, (l.publicados / Math.max(1, l.objetivo)) * 100)}%`,
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Generados · publicados / objetivo, en ventana móvil de 24 h (el mismo conteo que la
          admisión del plan). «Evergreen» se llena solo (cada día, uno aleatorio del banco green aprobado, a las 8:00); «Breaking» también cuenta lo
          empujado desde el panel.
        </p>
      </CardContent>
    </Card>
  );
}

