import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarClock,
  ClipboardCheck,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";

import { BadgeFuente } from "@/components/comunes/BadgeFuente";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { numeroCompacto, porcentaje } from "@/lib/formato";
import type { PicoPanel, ProximaPanel } from "@/types";

import { formatearFechaHora } from "./publicaciones/meta";

const CABECERA = {
  titulo: "Panel",
  descripcion:
    "Un vistazo: rendimiento del periodo, qué espera revisión y qué se publica pronto.",
};

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Esqueleto de carga del panel (KPIs + dos columnas). */
function EsqueletoPanel() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    </div>
  );
}

/** Flecha + color según la dirección del movimiento ("sube" | "baja" | "estable"). */
function IconoDireccion({ direccion }: { direccion: string }) {
  if (direccion === "sube") {
    return <ArrowUpRight className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />;
  }
  if (direccion === "baja") {
    return <ArrowDownRight className="h-4 w-4 text-rose-600 dark:text-rose-400" aria-hidden="true" />;
  }
  return <ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />;
}

/** Fila de un "pico" (movimiento destacado del periodo). */
function FilaPico({ pico }: { pico: PicoPanel }) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-border/60 py-2 last:border-0">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{pico.marca}</p>
        {pico.pieza_titulo && (
          <p className="truncate text-xs text-muted-foreground">{pico.pieza_titulo}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5 tabular-nums">
        <IconoDireccion direccion={pico.direccion} />
        <span className="text-sm">{numeroCompacto(pico.visualizaciones)}</span>
      </div>
    </li>
  );
}

/** Fila de una pieza programada próxima (con su marca dry-run si ya venció). */
function FilaProxima({ pieza }: { pieza: ProximaPanel }) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-border/60 py-2 last:border-0">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{pieza.titulo || "(sin título)"}</p>
        <p className="truncate text-xs text-muted-foreground">
          {[pieza.marca_nombre, pieza.red_nombre].filter(Boolean).join(" · ")}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className="text-xs tabular-nums text-muted-foreground">
          {formatearFechaHora(pieza.fecha_programada)}
        </span>
        {pieza.preparado_en ? (
          <Badge variant="ok" title="Preparada (dry-run): el posteo real está pendiente de #5/#8.">
            Lista (dry-run)
          </Badge>
        ) : (
          <Badge variant="secondary">Programada</Badge>
        )}
      </div>
    </li>
  );
}

export default function Panel() {
  // El panel es de lectura; se refresca al volver a la pestaña como el resto.
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["panel", "semana"],
    queryFn: ({ signal }) => api.panel({ rango: "semana" }, signal),
  });

  return (
    <div>
      <PageHeader titulo={CABECERA.titulo} descripcion={CABECERA.descripcion} />

      {isLoading && <EsqueletoPanel />}
      {isError && (
        <BloqueError
          titulo="No se pudo cargar el panel"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      )}

      {data && (
        <div className="space-y-6">
          {/* Resumen de métricas (reusa el camino de lectura de Métricas). */}
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-muted-foreground">
                Rendimiento de la semana
              </h3>
              <BadgeFuente fuente={data.metricas.fuente} />
            </div>
            {data.metricas.disponible && data.metricas.total ? (
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <TarjetaKpi
                  variante="card"
                  etiqueta="Visualizaciones"
                  valor={numeroCompacto(data.metricas.total.visualizaciones)}
                />
                <TarjetaKpi
                  variante="card"
                  etiqueta="Alcance"
                  valor={numeroCompacto(data.metricas.total.alcance)}
                />
                <TarjetaKpi
                  variante="card"
                  etiqueta="Interacciones"
                  valor={numeroCompacto(data.metricas.total.interacciones)}
                />
                <TarjetaKpi
                  variante="card"
                  etiqueta="Engagement"
                  valor={porcentaje(data.metricas.total.engagement_pct)}
                />
              </div>
            ) : (
              <Card>
                <CardContent className="py-8 text-center text-sm text-muted-foreground">
                  Las métricas no están disponibles ahora mismo.
                </CardContent>
              </Card>
            )}
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Cola de aprobación. */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ClipboardCheck className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  Cola de aprobación
                </CardTitle>
                <Button asChild variant="ghost" size="sm">
                  <Link to="/publicaciones">Ver todo</Link>
                </Button>
              </CardHeader>
              <CardContent>
                {data.cola.total > 0 ? (
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-semibold tabular-nums">
                      {data.cola.total}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {data.cola.total === 1 ? "pieza espera revisión" : "piezas esperan revisión"}
                    </span>
                  </div>
                ) : (
                  <p className="py-4 text-sm text-muted-foreground">
                    Nada pendiente de revisión. Buen trabajo.
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Picos del periodo. */}
            <Card>
              <CardHeader className="space-y-0">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  Picos de la semana
                </CardTitle>
              </CardHeader>
              <CardContent>
                {data.metricas.picos.length > 0 ? (
                  <ul>
                    {data.metricas.picos.map((pico, i) => (
                      <FilaPico key={`${pico.marca}-${i}`} pico={pico} />
                    ))}
                  </ul>
                ) : (
                  <p className="py-4 text-sm text-muted-foreground">
                    Sin movimientos destacados en el periodo.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Próximas programadas. */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <CalendarClock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Próximas programadas
              </CardTitle>
              {data.proximas.total > data.proximas.items.length && (
                <span className="text-xs text-muted-foreground">
                  {data.proximas.total} en total
                </span>
              )}
            </CardHeader>
            <CardContent>
              {data.proximas.items.length > 0 ? (
                <ul>
                  {data.proximas.items.map((pieza) => (
                    <FilaProxima key={pieza.id} pieza={pieza} />
                  ))}
                </ul>
              ) : (
                <EstadoVacio
                  icono={CalendarClock}
                  titulo="Nada programado todavía"
                  texto="Aprueba una pieza y prográmala desde Publicaciones."
                  accion={
                    <Button asChild variant="outline" size="sm">
                      <Link to="/publicaciones">Ir a Publicaciones</Link>
                    </Button>
                  }
                />
              )}
            </CardContent>
          </Card>

          {/* Frontera del producto: el sistema NO publica solo (gated por #5/#8). */}
          {!data.gating.publicacion_real_activa && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800 dark:text-amber-300">
              {data.gating.nota}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
