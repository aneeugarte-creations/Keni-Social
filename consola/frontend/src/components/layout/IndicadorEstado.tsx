/**
 * Indicador de salud del sistema en la topbar (issue #88).
 *
 * Un punto de color (verde/ámbar/rojo) que resume de un vistazo si la consola
 * está lista para trabajar; al pulsarlo abre un popover con el detalle de los
 * chequeos, el resumen y el siguiente paso accionable. Reemplaza a la antigua
 * página/sección "Estado" (que estaba desalineada y solapaba con Configuración).
 *
 * El backend (`/api/estado`) ya filtra los chequeos al dominio de la consola:
 * las herramientas de transcripción local (whisper/ffmpeg) NO llegan aquí, así
 * que el color del punto refleja solo lo que la consola gobierna.
 *
 * El popover es autocontenido (sin dependencia nueva): se cierra al pulsar fuera
 * o con Escape.
 */
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { NivelEstado, ResultadoEstado } from "@/types";

/** Color del punto de estado por nivel (el color basta; el detalle va en el popover). */
const PUNTO_NIVEL: Record<NivelEstado, string> = {
  ok: "bg-emerald-500",
  aviso: "bg-amber-500",
  error: "bg-red-500",
};

/** Etiqueta accesible del indicador según el nivel global. */
const ETIQUETA_NIVEL: Record<NivelEstado, string> = {
  ok: "Sistema listo",
  aviso: "Sistema con avisos",
  error: "Sistema con problemas",
};

function puntoNivel(nivel: NivelEstado): string {
  return PUNTO_NIVEL[nivel] ?? PUNTO_NIVEL.aviso;
}

/**
 * Nivel global = el peor de los chequeos (error > aviso > ok). Sin chequeos o en
 * error de carga, se trata como "aviso": no afirma que todo va bien.
 */
function nivelGlobal(resultados: ResultadoEstado[]): NivelEstado {
  if (resultados.some((r) => r.estado === "error")) return "error";
  if (resultados.some((r) => r.estado === "aviso")) return "aviso";
  if (resultados.length > 0) return "ok";
  return "aviso";
}

/** Una fila de chequeo: punto de color por nivel, nombre y detalle. */
function FilaChequeo({ resultado }: { resultado: ResultadoEstado }) {
  return (
    <li className="flex items-start gap-3 px-4 py-2.5">
      <span
        className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", puntoNivel(resultado.estado))}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{resultado.nombre}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{resultado.detalle}</p>
      </div>
    </li>
  );
}

/**
 * Indicador de salud para la topbar: botón con punto de color + popover de
 * detalle. La query se mantiene fresca al volver a la pestaña; el color se
 * deriva del peor chequeo.
 */
export function IndicadorEstado() {
  const [abierto, setAbierto] = React.useState(false);
  const contenedorRef = React.useRef<HTMLDivElement>(null);

  const { data, isPending, isError, refetch, isFetching } = useQuery({
    queryKey: ["estado"],
    queryFn: ({ signal }) => api.estado(signal),
    // Refresco suave al volver a la pestaña; no es crítico que esté siempre fresco.
    staleTime: 30_000,
  });

  const resultados = data?.resultados ?? [];
  // En carga o error de la API mostramos ámbar (no afirmamos "todo bien").
  const nivel: NivelEstado = isError ? "error" : isPending ? "aviso" : nivelGlobal(resultados);

  // Cierra el popover al pulsar fuera o con Escape.
  React.useEffect(() => {
    if (!abierto) return;
    function alPulsarFuera(e: MouseEvent) {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false);
      }
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [abierto]);

  return (
    <div ref={contenedorRef} className="relative">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex items-center gap-2 rounded-md px-2 py-1 text-sm transition-colors hover:bg-accent"
        aria-haspopup="dialog"
        aria-expanded={abierto}
        aria-label={ETIQUETA_NIVEL[nivel]}
        title={ETIQUETA_NIVEL[nivel]}
      >
        <span
          className={cn(
            "h-2.5 w-2.5 rounded-full",
            puntoNivel(nivel),
            isFetching && "animate-pulse",
          )}
          aria-hidden="true"
        />
        <span className="hidden text-muted-foreground sm:inline">Estado</span>
      </button>

      {abierto && (
        <div
          role="dialog"
          aria-label="Estado del sistema"
          className="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-md"
        >
          <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0 space-y-0.5">
              <p className="text-sm font-semibold">Estado del sistema</p>
              <p className="text-xs text-muted-foreground">
                {isError
                  ? "No se pudo ejecutar el autodiagnóstico."
                  : data?.resumen || "Revisamos si tu equipo está listo para trabajar."}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0"
              onClick={() => void refetch()}
              disabled={isFetching}
              aria-label="Volver a comprobar"
              title="Volver a comprobar"
            >
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            </Button>
          </div>

          <div className="max-h-[60vh] overflow-y-auto">
            {isPending ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">Comprobando…</p>
            ) : isError ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                Vuelve a intentarlo en un momento.
              </p>
            ) : resultados.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                No hay comprobaciones disponibles.
              </p>
            ) : (
              <>
                <ul className="divide-y divide-border">
                  {resultados.map((r, i) => (
                    <FilaChequeo key={`${r.nombre}-${i}`} resultado={r} />
                  ))}
                </ul>

                {data?.siguiente_paso && (
                  <div className="border-t border-border bg-primary/5 px-4 py-3">
                    <p className="text-xs font-semibold">¿Qué hago ahora?</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{data.siguiente_paso}</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
