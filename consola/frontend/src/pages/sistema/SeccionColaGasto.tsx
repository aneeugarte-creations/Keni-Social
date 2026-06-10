import { useQuery } from "@tanstack/react-query";
import { Coins, ListOrdered } from "lucide-react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { INTERVALO_RECURSOS_MS } from "./lib";

const ETIQUETA_NIVEL: Record<string, string> = {
  normal: "Normal",
  solo_manual: "Solo manual",
  agotado: "Agotado",
  pausado: "Pausado",
};

function tonoNivel(nivel: string): string {
  if (nivel === "normal")
    return "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400";
  if (nivel === "solo_manual")
    return "bg-amber-500/15 text-amber-600 dark:text-amber-400";
  return "bg-red-500/15 text-red-600 dark:text-red-400"; // agotado / pausado
}

function formatoTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} k`;
  return String(n);
}

/**
 * Sección compacta de cola de generación + economía de tokens del panel Sistema.
 * Solo LECTURA sobre el contrato de `/api/actividad/cola` (las acciones —purgar,
 * reencolar, toggles— viven en el Monitor de Actividad IA, su sitio natural).
 */
export function SeccionColaGasto() {
  const query = useQuery({
    queryKey: ["sistema", "cola"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });

  if (query.isPending) {
    return <Skeleton className="h-32 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer la cola de generación"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { capacidad, conteo, cola_llena, slots_libres, workers_activos, presupuesto } =
    query.data;

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
            <ListOrdered className="h-4 w-4" aria-hidden="true" />
            Cola de generación
            {cola_llena && (
              <Badge
                variant="outline"
                className="border-transparent bg-red-500/15 text-red-600 dark:text-red-400"
              >
                Llena
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0 text-sm text-muted-foreground">
          <p>
            <span className="text-2xl font-semibold tabular-nums text-foreground">
              {conteo.reclamados}
            </span>{" "}
            en curso · {conteo.pendientes} esperando · {slots_libres} slot(s) libre(s) de{" "}
            {capacidad.max_jobs}
          </p>
          <p className="mt-1 text-xs">
            Tope de admisión {capacidad.tope} · worker(s) activo(s):{" "}
            {workers_activos.length > 0 ? workers_activos.join(", ") : "ninguno"}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
            <Coins className="h-4 w-4" aria-hidden="true" />
            Gasto de IA (hoy)
            {presupuesto && (
              <Badge
                variant="outline"
                className={cn("border-transparent", tonoNivel(presupuesto.nivel))}
              >
                {ETIQUETA_NIVEL[presupuesto.nivel] ?? presupuesto.nivel}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0 text-sm text-muted-foreground">
          {!presupuesto ? (
            <p>Este backend aún no expone la economía de tokens.</p>
          ) : (
            <>
              <p>
                <span className="text-2xl font-semibold tabular-nums text-foreground">
                  {formatoTokens(presupuesto.gastado.tokens)}
                </span>{" "}
                tokens · ${presupuesto.gastado.coste_usd.toFixed(2)} ·{" "}
                {presupuesto.gastado.generaciones} generación(es)
              </p>
              <p className="mt-1 text-xs">
                {presupuesto.presupuesto_tokens_dia > 0 ? (
                  <>
                    {presupuesto.pct_usado}% del presupuesto diario (
                    {formatoTokens(presupuesto.presupuesto_tokens_dia)}) · restante{" "}
                    {formatoTokens(presupuesto.restante_tokens ?? 0)}
                  </>
                ) : (
                  "Sin presupuesto diario configurado (sin límite)."
                )}
                {presupuesto.pausada && " · Generación PAUSADA (kill switch)."}
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
