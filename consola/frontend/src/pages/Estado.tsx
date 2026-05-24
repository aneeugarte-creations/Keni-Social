import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, CheckCircle2, RefreshCw, TriangleAlert, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { NivelEstado, ResultadoEstado } from "@/types";

/** Metadatos visuales por nivel de estado del doctor. */
const META_NIVEL: Record<
  NivelEstado,
  { icono: LucideIcon; etiqueta: string; clase: string; variante: "ok" | "aviso" | "error" }
> = {
  ok: { icono: CheckCircle2, etiqueta: "OK", clase: "text-emerald-500", variante: "ok" },
  aviso: { icono: TriangleAlert, etiqueta: "Aviso", clase: "text-amber-500", variante: "aviso" },
  error: { icono: XCircle, etiqueta: "Error", clase: "text-red-500", variante: "error" },
};

function meta(nivel: NivelEstado) {
  return META_NIVEL[nivel] ?? META_NIVEL.aviso;
}

/** Una fila de chequeo: icono coloreado, nombre, detalle y badge de nivel. */
function FilaChequeo({ resultado }: { resultado: ResultadoEstado }) {
  const m = meta(resultado.estado);
  const Icono = m.icono;
  return (
    <li className="flex items-start gap-3 px-4 py-3.5">
      <Icono className={cn("mt-0.5 h-5 w-5 shrink-0", m.clase)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{resultado.nombre}</span>
          <Badge variant={m.variante}>{m.etiqueta}</Badge>
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">{resultado.detalle}</p>
      </div>
    </li>
  );
}

/** Esqueleto de carga que imita la lista de chequeos. */
function EsqueletoEstado() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-20 w-full rounded-xl" />
      <Card>
        <CardContent className="divide-y divide-border p-0">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-start gap-3 px-4 py-3.5">
              <Skeleton className="mt-0.5 h-5 w-5 rounded-full" />
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
 * Pagina de referencia COMPLETA: autodiagnostico del sistema.
 * Consume `GET /api/estado` via React Query y maneja los tres estados
 * (cargando / error / datos) con UI profesional y soporte de modo oscuro.
 */
export default function Estado() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["estado"],
    queryFn: ({ signal }) => api.estado(signal),
  });

  const acciones = (
    <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
      <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
      Volver a comprobar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Estado del sistema"
        descripcion="Revisamos tu equipo y te decimos, en lenguaje sencillo, si todo está listo para trabajar."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoEstado />
      ) : isError ? (
        <Card className="border-destructive/40">
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">No se pudo ejecutar el autodiagnóstico</p>
              <p className="max-w-md text-sm text-muted-foreground">
                {error instanceof Error
                  ? error.message
                  : "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento."}
              </p>
            </div>
            <Button onClick={() => void refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          <Resumen resultados={data.resultados} texto={data.resumen} />

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Comprobaciones</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
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

/** Tarjeta de resumen con el conteo OK / aviso / error y la frase del doctor. */
function Resumen({ resultados, texto }: { resultados: ResultadoEstado[]; texto: string }) {
  const oks = resultados.filter((r) => r.estado === "ok").length;
  const avisos = resultados.filter((r) => r.estado === "aviso").length;
  const errores = resultados.filter((r) => r.estado === "error").length;
  const hayError = errores > 0;

  return (
    <Card className={cn(hayError ? "border-destructive/40" : "border-emerald-500/40")}>
      <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          {hayError ? (
            <XCircle className="mt-0.5 h-6 w-6 shrink-0 text-red-500" />
          ) : (
            <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-emerald-500" />
          )}
          <p className="text-sm font-medium leading-relaxed">{texto}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="ok">{oks} OK</Badge>
          <Badge variant="aviso">{avisos} aviso{avisos === 1 ? "" : "s"}</Badge>
          <Badge variant="error">{errores} error{errores === 1 ? "" : "es"}</Badge>
        </div>
      </CardContent>
    </Card>
  );
}

/** Bloque destacado con el siguiente paso accionable. */
function SiguientePaso({ texto }: { texto: string }) {
  if (!texto) return null;
  return (
    <Card className="bg-primary/5">
      <CardContent className="flex items-start gap-3 py-5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
          <ArrowRight className="h-4 w-4" />
        </div>
        <div className="space-y-0.5">
          <p className="text-sm font-semibold">¿Qué hago ahora?</p>
          <p className="text-sm text-muted-foreground">{texto}</p>
        </div>
      </CardContent>
    </Card>
  );
}
