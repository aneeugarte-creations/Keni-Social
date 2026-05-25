/**
 * Panel de autodiagnóstico del sistema (issue #88, movido desde la topbar).
 *
 * Antes vivía en `IndicadorEstado` como un popover en la topbar; ahora se usa
 * como una sección dentro de Configuración. Consulta `GET /api/estado` y lista
 * los chequeos con icono/badge por nivel (ok/aviso/error), agrupando las
 * "Herramientas locales" (whisper / ffmpeg) para que sus avisos no alarmen: son
 * opcionales y solo afectan a la transcripción de medios. Muestra también el
 * `resumen` y el `siguiente_paso`, con un botón para volver a comprobar.
 */
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { NivelEstado, ResultadoEstado } from "@/types";

/** Color del punto de estado por nivel (el color basta; el detalle va al lado). */
const PUNTO_NIVEL: Record<NivelEstado, string> = {
  ok: "bg-emerald-500",
  aviso: "bg-amber-500",
  error: "bg-red-500",
};

function puntoNivel(nivel: NivelEstado): string {
  return PUNTO_NIVEL[nivel] ?? PUNTO_NIVEL.aviso;
}

/** ¿Es un chequeo de herramienta local (whisper / ffmpeg)? */
function esHerramientaLocal(r: ResultadoEstado): boolean {
  const n = r.nombre.toLowerCase();
  return n.includes("whisper") || n.includes("ffmpeg");
}

/** Una fila de chequeo: punto de color por nivel, nombre y detalle. */
function FilaChequeo({ resultado }: { resultado: ResultadoEstado }) {
  return (
    <li className="flex items-start gap-3 px-4 py-3">
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
 * Render reutilizable del autodiagnóstico: lista de chequeos + botón "Volver a
 * comprobar" + estados cargando/error. Se usa como sección de página.
 */
export function PanelEstado() {
  const { data, isPending, isError, refetch, isFetching } = useQuery({
    queryKey: ["estado"],
    queryFn: ({ signal }) => api.estado(signal),
    // Refresco suave al volver a la pestaña; no es crítico que esté siempre fresco.
    staleTime: 30_000,
  });

  const resultados = data?.resultados ?? [];

  // Separa chequeos principales de las herramientas locales.
  const principales = resultados.filter((r) => !esHerramientaLocal(r));
  const locales = resultados.filter(esHerramientaLocal);

  return (
    <div className="overflow-hidden rounded-lg border border-border">
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

      <div>
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
              {principales.map((r, i) => (
                <FilaChequeo key={`${r.nombre}-${i}`} resultado={r} />
              ))}
            </ul>

            {locales.length > 0 && (
              <div className="border-t border-border">
                <p className="px-4 pb-1 pt-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Herramientas locales
                </p>
                <p className="px-4 pb-1 text-xs text-muted-foreground">
                  Opcionales: solo para transcribir audio y video.
                </p>
                <ul className="divide-y divide-border">
                  {locales.map((r, i) => (
                    <FilaChequeo key={`local-${r.nombre}-${i}`} resultado={r} />
                  ))}
                </ul>
              </div>
            )}

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
  );
}
