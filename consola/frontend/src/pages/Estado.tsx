import { useQuery } from "@tanstack/react-query";
import { AlertCircle, RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { NivelEstado, ResultadoEstado } from "@/types";

/** Color del punto de estado por nivel: el unico acento de color de la pagina. */
const COLOR_PUNTO: Record<NivelEstado, string> = {
  ok: "bg-emerald-500",
  aviso: "bg-amber-500",
  error: "bg-red-500",
};

/**
 * Limpia el texto del backend: quita emojis/simbolos (❌ ✅ ⚠️) y ordena la
 * puntuacion. El estado se transmite con el punto de color, no con iconos.
 */
function limpiarTexto(t: string): string {
  return t
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}️‍]/gu, "")
    .replace(/\(\s+/g, "(")
    .replace(/\s+([,.;:!?)])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Punto de estado pequeno (a lo Vercel): un solo toque de color. */
function Punto({ nivel, className }: { nivel: NivelEstado; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        COLOR_PUNTO[nivel] ?? COLOR_PUNTO.aviso,
        className,
      )}
      aria-hidden="true"
    />
  );
}

/** Leyenda del codigo de color, para que los puntos se entiendan de un vistazo. */
function Leyenda() {
  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <Punto nivel="ok" />
        Listo
      </span>
      <span className="flex items-center gap-1.5">
        <Punto nivel="aviso" />
        Atención
      </span>
      <span className="flex items-center gap-1.5">
        <Punto nivel="error" />
        Error
      </span>
    </div>
  );
}

/**
 * Una fila de chequeo: punto de color + nombre + detalle. El punto da el estado;
 * solo los errores muestran ademas la palabra "Error" para que salten a la vista.
 */
function FilaChequeo({ resultado }: { resultado: ResultadoEstado }) {
  return (
    <li className="flex items-start gap-3 px-5 py-4">
      <Punto nivel={resultado.estado} className="mt-1.5" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{resultado.nombre}</p>
        <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">
          {limpiarTexto(resultado.detalle)}
        </p>
      </div>
      {resultado.estado === "error" && (
        <span className="mt-0.5 shrink-0 text-xs font-medium text-red-600 dark:text-red-400">
          Error
        </span>
      )}
    </li>
  );
}

/** Esqueleto de carga que imita la lista de chequeos. */
function EsqueletoEstado() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-16 w-full rounded-xl" />
      <Card>
        <CardContent className="divide-y divide-border p-0">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-start gap-3 px-5 py-4">
              <Skeleton className="mt-1 h-2 w-2 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3 w-64" />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Pagina de autodiagnostico del sistema. Consume `GET /api/estado` y muestra,
 * en lenguaje sencillo, si el equipo esta listo. Diseno sobrio: el unico color
 * son los puntos de estado.
 */
export default function Estado() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["estado"],
    queryFn: ({ signal }) => api.estado(signal),
  });

  const acciones = (
    <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching}>
      <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
      Volver a comprobar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Estado del sistema"
        descripcion="Comprobamos que tu equipo tenga todo lo necesario para usar Keni. Si falta algo, te decimos qué hacer."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoEstado />
      ) : isError ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <AlertCircle className="h-6 w-6 text-muted-foreground" />
            <div className="space-y-1">
              <p className="text-sm font-medium">No se pudo ejecutar el autodiagnóstico</p>
              <p className="max-w-md text-sm text-muted-foreground">
                {error instanceof Error
                  ? error.message
                  : "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento."}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          <Resumen resultados={data.resultados} />

          <Card>
            <CardContent className="p-0">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
                <p className="text-sm font-medium text-foreground">Comprobaciones</p>
                <Leyenda />
              </div>
              <ul className="divide-y divide-border">
                {data.resultados.map((r, i) => (
                  <FilaChequeo key={`${r.nombre}-${i}`} resultado={r} />
                ))}
              </ul>
            </CardContent>
          </Card>

          <SiguientePaso texto={data.siguiente_paso} />
        </div>
      )}
    </>
  );
}

/**
 * Resumen claro y elegante derivado de los chequeos (sin emojis ni tecnicismos):
 * dice si el sistema esta listo, cuantos problemas hay o si solo quedan avisos.
 */
function resumenSistema(resultados: ResultadoEstado[]): string {
  const errores = resultados.filter((r) => r.estado === "error").length;
  const avisos = resultados.filter((r) => r.estado === "aviso").length;
  if (errores > 0) {
    return errores === 1
      ? "Hay 1 problema que resolver antes de empezar."
      : `Hay ${errores} problemas que resolver antes de empezar.`;
  }
  if (avisos > 0) {
    return avisos === 1
      ? "Todo listo para trabajar, con 1 aviso opcional."
      : `Todo listo para trabajar, con ${avisos} avisos opcionales.`;
  }
  return "Todo está listo para trabajar.";
}

function Resumen({ resultados }: { resultados: ResultadoEstado[] }) {
  return (
    <Card>
      <CardContent className="py-5">
        <p className="text-sm font-medium leading-relaxed text-foreground">
          {resumenSistema(resultados)}
        </p>
      </CardContent>
    </Card>
  );
}

/** Siguiente paso accionable, en bloque sobrio (sin acentos llamativos). */
function SiguientePaso({ texto }: { texto: string }) {
  if (!texto) return null;
  return (
    <Card>
      <CardContent className="space-y-1 py-5">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Siguiente paso
        </p>
        <p className="text-sm leading-relaxed text-foreground">{limpiarTexto(texto)}</p>
      </CardContent>
    </Card>
  );
}
