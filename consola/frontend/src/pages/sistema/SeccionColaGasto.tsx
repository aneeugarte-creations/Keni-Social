import { useQuery } from "@tanstack/react-query";
import { Coins, ExternalLink, ListOrdered } from "lucide-react";
import { Link } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { ChipNivelPresupuesto } from "@/components/comunes/ChipEstado";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import { costeUsd, numeroCompacto } from "@/lib/formato";

import { INTERVALO_RECURSOS_MS } from "./lib";

// Ruta del Monitor de la cola: es donde se OPERA (cancelar/purgar, kill switch, máquina).
// Este panel solo OBSERVA: misma fuente (`/api/actividad/cola`), mismas etiquetas, y un
// enlace en vez de duplicar controles.
const RUTA_MONITOR = "/datos/actividad/monitor";

/**
 * Sección compacta de cola de generación + economía de tokens del panel Sistema.
 * Solo LECTURA sobre el contrato de `/api/actividad/cola`: las acciones (purgar,
 * cancelar, pausar, toggles) viven en el Monitor, su sitio natural — aquí se enlaza.
 * Chip de nivel y formato de tokens/coste COMPARTIDOS con el Monitor
 * (`ChipNivelPresupuesto`, `@/lib/formato`): el mismo dato se lee igual en ambos.
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
            <Link
              to={RUTA_MONITOR}
              className="ml-auto inline-flex items-center gap-1 text-xs font-normal text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              Abrir Monitor
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </Link>
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
            Economía de tokens (hoy)
            {presupuesto && <ChipNivelPresupuesto nivel={presupuesto.nivel} />}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0 text-sm text-muted-foreground">
          {!presupuesto ? (
            <p>Este backend aún no expone la economía de tokens.</p>
          ) : (
            <>
              <p>
                <span className="text-2xl font-semibold tabular-nums text-foreground">
                  {numeroCompacto(presupuesto.gastado.tokens)}
                </span>{" "}
                tokens · {costeUsd(presupuesto.gastado.coste_usd)} ·{" "}
                {presupuesto.gastado.generaciones} generación(es)
              </p>
              <p className="mt-1 text-xs">
                {presupuesto.presupuesto_tokens_dia > 0 ? (
                  <>
                    {presupuesto.pct_usado}% del presupuesto diario (
                    {numeroCompacto(presupuesto.presupuesto_tokens_dia)}) · restante{" "}
                    {numeroCompacto(presupuesto.restante_tokens ?? 0)}
                  </>
                ) : (
                  "Sin presupuesto diario configurado (sin límite)."
                )}
                {presupuesto.pausada && " · Generación PAUSADA (se reanuda desde el Monitor)."}
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
