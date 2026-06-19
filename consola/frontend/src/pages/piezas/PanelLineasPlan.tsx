/**
 * Producción del día por LÍNEA del plan (generados · publicados / objetivo), para la marca
 * activa. Vive en la página de PROGRAMACIÓN (es el pulso del plan que alimenta la parrilla);
 * se oculta solo si la marca no tiene plan o no hay marca activa.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { colorLinea, ETIQUETA_LINEA } from "@/lib/lineas";
import { cn } from "@/lib/utils";

// Re-export por compatibilidad: la tabla canónica vive en `lib/lineas.ts` (la comparten
// Programación, Monitor y la Mesa de redacción de Noticias).
export { ETIQUETA_LINEA };

/** Producción del día por LÍNEA del plan (producido vs objetivo), para la marca activa. */
export function PanelLineasPlan({ marca }: { marca: string }) {
  const produccion = useQuery({
    queryKey: ["produccion", "dia", marca],
    queryFn: ({ signal }) => api.produccionDia(marca, signal),
    refetchInterval: 60_000,
  });
  const lineas = produccion.data?.por_categoria ?? [];
  if (!produccion.data || lineas.length === 0) return null;
  return (
    <section aria-label="Producción del día por línea">
      <h2 className="mb-4 text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
        Producción del día
      </h2>
      {/* Tipografía como protagonista: cada línea es una columna de estadística sin caja. El
          único color es un punto que identifica la línea; número y barra van en neutro para no
          chocar con ese punto. */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-5">
        {lineas.map((l) => {
          const col = colorLinea(l.categoria);
          return (
            <div key={l.categoria}>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span
                  className={cn("h-2 w-2 shrink-0 rounded-full", col.punto)}
                  aria-hidden="true"
                />
                <span className="truncate">
                  {l.etiqueta ||
                    ETIQUETA_LINEA[l.categoria] ||
                    l.categoria.charAt(0).toUpperCase() + l.categoria.slice(1)}
                </span>
              </div>
              <div className="mt-1 text-2xl font-semibold leading-none tabular-nums text-foreground">
                {l.generados}
                <span className="text-sm font-normal text-muted-foreground">
                  {l.objetivo != null ? ` / ${l.objetivo}` : " · fuera de plan"}
                </span>
              </div>
              <div className="mt-1 text-[11px] tabular-nums text-muted-foreground">
                {l.publicados} publicado{l.publicados === 1 ? "" : "s"}
              </div>
              {l.objetivo != null && (
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted">
                  <div className="relative h-full">
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-foreground/20"
                      style={{
                        width: `${Math.min(100, (l.generados / Math.max(1, l.objetivo)) * 100)}%`,
                      }}
                    />
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-foreground"
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
    </section>
  );
}
