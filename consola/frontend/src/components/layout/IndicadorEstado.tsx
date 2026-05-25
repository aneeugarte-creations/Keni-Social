/**
 * Indicador de salud del sistema en la topbar (issue #88).
 *
 * Sustituye la antigua página "Estado": un punto verde / ámbar / rojo según el
 * PEOR estado de `GET /api/estado`, con un popover que lista los chequeos
 * (reutilizando el render de filas). Los chequeos de herramientas locales
 * (whisper / ffmpeg) se agrupan bajo "Herramientas locales" para que sus avisos
 * no alarmen: son opcionales y solo afectan a la transcripción de medios.
 *
 * No usamos una dependencia de popover: un panel posicionado con cierre por
 * clic-fuera y tecla Escape cubre el caso sin añadir peso al bundle.
 */
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  RefreshCw,
  TriangleAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { NivelEstado, ResultadoEstado } from "@/types";

/** Metadatos visuales por nivel de estado. */
const META_NIVEL: Record<
  NivelEstado,
  { icono: LucideIcon; etiqueta: string; clase: string; punto: string; variante: "ok" | "aviso" | "error" }
> = {
  ok: {
    icono: CheckCircle2,
    etiqueta: "OK",
    clase: "text-emerald-500",
    punto: "bg-emerald-500",
    variante: "ok",
  },
  aviso: {
    icono: TriangleAlert,
    etiqueta: "Aviso",
    clase: "text-amber-500",
    punto: "bg-amber-500",
    variante: "aviso",
  },
  error: {
    icono: XCircle,
    etiqueta: "Error",
    clase: "text-red-500",
    punto: "bg-red-500",
    variante: "error",
  },
};

function meta(nivel: NivelEstado) {
  return META_NIVEL[nivel] ?? META_NIVEL.aviso;
}

/** Orden de severidad para calcular el peor estado. */
const SEVERIDAD: Record<NivelEstado, number> = { ok: 0, aviso: 1, error: 2 };

/** Devuelve el peor nivel de una lista de chequeos. */
function peorNivel(resultados: ResultadoEstado[]): NivelEstado {
  let peor: NivelEstado = "ok";
  for (const r of resultados) {
    if (SEVERIDAD[r.estado] > SEVERIDAD[peor]) peor = r.estado;
  }
  return peor;
}

/** ¿Es un chequeo de herramienta local (whisper / ffmpeg)? */
function esHerramientaLocal(r: ResultadoEstado): boolean {
  const n = r.nombre.toLowerCase();
  return n.includes("whisper") || n.includes("ffmpeg");
}

/** Una fila de chequeo: icono coloreado, nombre, detalle y badge de nivel. */
function FilaChequeo({ resultado }: { resultado: ResultadoEstado }) {
  const m = meta(resultado.estado);
  const Icono = m.icono;
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <Icono className={cn("mt-0.5 h-4 w-4 shrink-0", m.clase)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{resultado.nombre}</span>
          <Badge variant={m.variante}>{m.etiqueta}</Badge>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{resultado.detalle}</p>
      </div>
    </li>
  );
}

export function IndicadorEstado() {
  const [abierto, setAbierto] = React.useState(false);
  const contenedorRef = React.useRef<HTMLDivElement>(null);

  const { data, isPending, isError, refetch, isFetching } = useQuery({
    queryKey: ["estado"],
    queryFn: ({ signal }) => api.estado(signal),
    // Refresco suave al volver a la pestaña; no es crítico que esté siempre fresco.
    staleTime: 30_000,
  });

  // Cierre por clic fuera y tecla Escape.
  React.useEffect(() => {
    if (!abierto) return;
    function onClick(e: MouseEvent) {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [abierto]);

  const resultados = data?.resultados ?? [];
  const nivel: NivelEstado = isError ? "error" : peorNivel(resultados);
  const m = meta(nivel);

  // Texto de estado para accesibilidad/tooltip.
  const etiquetaEstado = isPending
    ? "Comprobando el estado del sistema…"
    : isError
      ? "No se pudo comprobar el estado"
      : data?.resumen || `Estado del sistema: ${m.etiqueta}`;

  // Separa chequeos principales de las herramientas locales.
  const principales = resultados.filter((r) => !esHerramientaLocal(r));
  const locales = resultados.filter(esHerramientaLocal);

  return (
    <div className="relative" ref={contenedorRef}>
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex h-9 items-center gap-2 rounded-md px-2.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        aria-label={etiquetaEstado}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        title={etiquetaEstado}
      >
        <span className="relative flex h-2.5 w-2.5">
          {isPending ? (
            <span className="inline-flex h-2.5 w-2.5 animate-pulse rounded-full bg-muted-foreground/50" />
          ) : (
            <span className={cn("inline-flex h-2.5 w-2.5 rounded-full", m.punto)} />
          )}
        </span>
        <span className="hidden text-xs font-medium sm:inline">Estado</span>
      </button>

      {abierto && (
        <div
          role="dialog"
          aria-label="Estado del sistema"
          className="absolute right-0 z-50 mt-2 w-[22rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-lg"
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
      )}
    </div>
  );
}
