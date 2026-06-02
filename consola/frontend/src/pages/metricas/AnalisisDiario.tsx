/**
 * Sub-sección "Lectura del periodo" (análisis diario con narrativa, F6 / #146).
 *
 * Sobre las métricas ya visibles arriba, pinta la LECTURA: qué subió/bajó, la(s)
 * pieza(s) que lo explican y un siguiente paso accionable (loop a la acción,
 * UX-roadmap #11). No son cifras nuevas: el backend (`/api/metricas/analisis`)
 * ensambla reporte + picos y aquí solo se redacta.
 *
 * Honestidad (issue #131): si los datos son de muestra, lo marca con un aviso
 * destacado. Si no hay movimientos, lo dice sin forzar una narrativa vacía. La
 * decisión final de qué cambiar queda en el equipo (la frontera del producto).
 */
import { useQuery } from "@tanstack/react-query";
import { BadgeDelta, type DeltaType } from "@tremor/react";
import { AlertCircle, ArrowRight, RefreshCw, Sparkles } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { numeroCompacto, porcentaje, variacion } from "@/lib/formato";
import { cn } from "@/lib/utils";
import type { AnalisisDiario as Analisis, MovimientoAnalisis } from "@/types";

import { MARCA_TODAS } from "./Controles";

/** Traduce la dirección del movimiento al `deltaType` de Tremor BadgeDelta. */
function deltaType(direccion: string): DeltaType {
  if (direccion === "sube") return "increase";
  if (direccion === "baja") return "decrease";
  return "unchanged";
}

export function AnalisisDiario({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Marca seleccionada arriba en el dashboard: la lectura la sigue. */
  marcaActual?: string;
  /** Rango seleccionado arriba: la lectura se hace sobre ese periodo. */
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const habilitado = Boolean(rangoActual);

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["metricas", "analisis", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasAnalisis({ rango: rangoActual, marca: marca_ }, signal),
    enabled: habilitado,
    // 2 min: al cambiar marca/rango la lectura se repinta pronto, sin re-pedir en cada
    // toque; servido desde la cache del backend; "Actualizar" lo invalida al refrescar.
    staleTime: 2 * 60_000,
  });

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Lectura del periodo</CardTitle>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {!habilitado ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Elige un rango para leer el periodo.
          </p>
        ) : isPending ? (
          <EsqueletoAnalisis />
        ) : isError ? (
          <ErrorAnalisis
            mensaje={error instanceof Error ? error.message : undefined}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : (
          <CuerpoAnalisis data={data} />
        )}
      </CardContent>
    </Card>
  );
}

function CuerpoAnalisis({ data }: { data: Analisis }) {
  const hayMovimientos = data.movimientos.length > 0;
  return (
    <>
      {data.cobertura_parcial.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>Cobertura parcial en {data.cobertura_parcial.join(", ")}.</span>
        </div>
      )}

      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        Periodo: <span className="font-medium text-foreground">{data.etiqueta_rango}</span>
      </div>

      {/* Lo que se movió. */}
      {hayMovimientos ? (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">Lo que se movió</h4>
          <ul className="space-y-2">
            {data.movimientos.map((m) => (
              <FilaMovimiento key={m.marca_id} mov={m} />
            ))}
          </ul>
          {(data.movimientos_resto > 0 || data.marcas_estables > 0) && (
            <p className="text-xs text-muted-foreground">
              {data.movimientos_resto > 0 &&
                `… y ${data.movimientos_resto} ${
                  data.movimientos_resto === 1 ? "marca más" : "marcas más"
                } con movimiento. `}
              {data.marcas_estables > 0 &&
                `${data.marcas_estables} ${
                  data.marcas_estables === 1 ? "marca se mantuvo" : "marcas se mantuvieron"
                } estable${data.marcas_estables === 1 ? "" : "s"}.`}
            </p>
          )}
        </div>
      ) : (
        <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
          {data.marcas_estables > 0
            ? `Sin movimientos destacados: ${
                data.marcas_estables === 1 ? "la marca se mantuvo estable" : `las ${data.marcas_estables} marcas se mantuvieron estables`
              } vs. el periodo anterior.`
            : "Sin datos suficientes para una lectura del periodo."}
        </p>
      )}

      {/* Siguiente paso: el loop de vuelta a la acción. */}
      {data.siguiente_paso && (
        <aside
          aria-label="Siguiente paso"
          className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-4"
        >
          <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-foreground" aria-hidden="true" />
          <div className="space-y-1">
            <p className="text-sm font-semibold">Siguiente paso</p>
            <p className="text-sm text-muted-foreground">{data.siguiente_paso.texto}</p>
          </div>
        </aside>
      )}
    </>
  );
}

function FilaMovimiento({ mov }: { mov: MovimientoAnalisis }) {
  return (
    <li className="rounded-lg border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-sm font-medium">{mov.marca}</p>
        <BadgeDelta deltaType={deltaType(mov.direccion)} size="xs" className="shrink-0">
          {variacion(mov.variacion_vis_pct)}
        </BadgeDelta>
      </div>
      <p className="mt-1 text-xs text-muted-foreground tabular-nums">
        {numeroCompacto(mov.visualizaciones)} visualizaciones
        {mov.engagement_pct != null && ` · ${porcentaje(mov.engagement_pct)} engagement`}
      </p>
      {mov.pieza && (
        <p className="mt-1 text-xs text-muted-foreground">
          Lo explica{" "}
          <span className="font-medium text-foreground">«{mov.pieza.titulo}»</span> en{" "}
          {mov.pieza.plataforma} ({porcentaje(mov.pieza.engagement_pct)} eng).
        </p>
      )}
    </li>
  );
}

function EsqueletoAnalisis() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-5 w-40" />
      {Array.from({ length: 3 }).map((_, i) => (
        <Skeleton key={i} className="h-16 w-full rounded-lg" />
      ))}
      <Skeleton className="h-20 w-full rounded-lg" />
    </div>
  );
}

function ErrorAnalisis({
  mensaje,
  onReintentar,
  cargando,
}: {
  mensaje?: string;
  onReintentar: () => void;
  cargando: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <AlertCircle className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
      <p className="max-w-md text-sm text-muted-foreground">
        {mensaje ?? "No se pudo generar la lectura del periodo. Vuelve a intentarlo."}
      </p>
      <Button variant="outline" size="sm" onClick={onReintentar} disabled={cargando}>
        <RefreshCw className={cn("h-4 w-4", cargando && "animate-spin")} />
        Reintentar
      </Button>
    </div>
  );
}
