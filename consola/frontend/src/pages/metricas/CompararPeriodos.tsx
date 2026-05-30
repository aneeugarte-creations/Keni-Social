/**
 * Sub-sección "Comparar periodos".
 *
 * Selecciona rango A, rango B y marca, consulta `api.metricasComparar` y muestra
 * por métrica el valor A, el valor B y la variación con flecha y color (Tremor
 * BadgeDelta: verde sube / rojo baja). Incluye el desglose `por_marca`.
 */
import { useQuery } from "@tanstack/react-query";
import { BadgeDelta, type DeltaType } from "@tremor/react";
import { AlertCircle, RefreshCw } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ComparativaMetrica, OpcionesMetricas } from "@/types";

import { MARCA_TODAS, SelectorMarca, SelectorRango } from "./Controles";
import { variacion } from "./formato";
import { METRICAS } from "./metricas-meta";

/** Etiqueta legible de una métrica del backend según su nombre interno. */
function etiquetaMetrica(metrica: string): string {
  return METRICAS.find((m) => m.metrica === metrica)?.etiqueta ?? metrica;
}

/** Formatea un valor según el tipo de métrica (porcentaje vs número). */
function formatoValor(metrica: string, valor: number): string {
  const meta = METRICAS.find((m) => m.metrica === metrica);
  return meta ? meta.completo(valor) : valor.toLocaleString("es-MX");
}

/** Traduce la variación porcentual al `deltaType` de Tremor BadgeDelta. */
function deltaType(variacionPct: number): DeltaType {
  if (variacionPct > 5) return "increase";
  if (variacionPct > 0) return "moderateIncrease";
  if (variacionPct < -5) return "decrease";
  if (variacionPct < 0) return "moderateDecrease";
  return "unchanged";
}

export function CompararPeriodos({
  opciones,
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  opciones: OpcionesMetricas;
  /** Marca seleccionada arriba en el dashboard: se hereda como punto de partida. */
  marcaActual?: string;
  /** Rango seleccionado arriba: se usa como rango B (comparado) por defecto. */
  rangoActual?: string;
}) {
  const rangos = opciones.rangos;
  // B (comparado) hereda el rango que se está viendo arriba; A (origen) parte de
  // otro rango distinto para que la comparativa tenga sentido por defecto.
  const rangoBInicial = rangoActual ?? rangos[0]?.id ?? "";
  const rangoAInicial =
    rangos.find((r) => r.id !== rangoBInicial)?.id ?? rangos[0]?.id ?? "";
  const [rangoA, setRangoA] = React.useState(rangoAInicial);
  const [rangoB, setRangoB] = React.useState(rangoBInicial);
  // La marca hereda la selección del dashboard; el usuario puede cambiarla aquí.
  const [marca, setMarca] = React.useState(marcaActual);

  // Si arriba cambia la marca, la comparativa la sigue (sin perder los rangos A/B
  // que el usuario haya ajustado a mano).
  React.useEffect(() => {
    setMarca(marcaActual);
  }, [marcaActual]);

  // Si arriba cambia el rango visible, lo reflejamos como rango B (comparado).
  React.useEffect(() => {
    if (rangoActual) setRangoB(rangoActual);
  }, [rangoActual]);

  const habilitado = Boolean(rangoA && rangoB);
  const marca_ = marcaParam(marca);

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["metricas", "comparar", rangoA, rangoB, marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasComparar({ rango_a: rangoA, rango_b: rangoB, marca: marca_ }, signal),
    enabled: habilitado,
    // Servido desde la cache del backend; el botón "Actualizar" lo invalida al refrescar.
    staleTime: 5 * 60_000,
  });

  return (
    <Card>
      <CardHeader className="gap-4 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <CardTitle className="text-base">Comparar periodos</CardTitle>
        <div className="grid grid-cols-1 gap-2 sm:flex sm:items-center">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">De</span>
            <SelectorRango
              rangos={rangos}
              valor={rangoA}
              onCambio={setRangoA}
              ariaLabel="Rango A (origen)"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">a</span>
            <SelectorRango
              rangos={rangos}
              valor={rangoB}
              onCambio={setRangoB}
              ariaLabel="Rango B (comparado)"
            />
          </div>
          <SelectorMarca marcas={opciones.marcas} valor={marca} onCambio={setMarca} />
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {!habilitado ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Elige dos rangos para comparar.
          </p>
        ) : isPending ? (
          <EsqueletoComparar />
        ) : isError ? (
          <ErrorComparar
            mensaje={error instanceof Error ? error.message : undefined}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              Comparando
              <span className="font-medium text-foreground">{data.etiqueta_a}</span>
              <span aria-hidden="true">→</span>
              <span className="font-medium text-foreground">{data.etiqueta_b}</span>
            </div>

            {/* Totales: una tarjeta por métrica con A, B y variación. */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {data.total.metricas.map((comp) => (
                <TarjetaComparativa key={comp.metrica} comp={comp} />
              ))}
            </div>

            {/* Desglose por marca. */}
            {data.por_marca.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-sm font-semibold">Desglose por marca</h4>
                <div className="space-y-3">
                  {data.por_marca.map((pm) => (
                    <div key={pm.marca_id} className="rounded-lg border border-border p-4">
                      <p className="mb-3 text-sm font-medium">{pm.marca}</p>
                      <div className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
                        {pm.comparativa.map((comp) => (
                          <FilaComparativa key={comp.metrica} comp={comp} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Tarjeta destacada de una métrica con valor A, valor B y BadgeDelta. */
function TarjetaComparativa({ comp }: { comp: ComparativaMetrica }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-sm font-medium text-muted-foreground">
          {etiquetaMetrica(comp.metrica)}
        </p>
        <BadgeDelta deltaType={deltaType(comp.variacion_pct)} size="xs" className="shrink-0">
          {variacion(comp.variacion_pct)}
        </BadgeDelta>
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">
        {formatoValor(comp.metrica, comp.b)}
      </p>
      <p className="mt-1 text-xs text-muted-foreground tabular-nums">
        antes {formatoValor(comp.metrica, comp.a)}
      </p>
    </div>
  );
}

/** Fila compacta usada dentro del desglose por marca. */
function FilaComparativa({ comp }: { comp: ComparativaMetrica }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0">
        <p className="truncate text-xs text-muted-foreground">{etiquetaMetrica(comp.metrica)}</p>
        <p className="text-sm font-medium tabular-nums">{formatoValor(comp.metrica, comp.b)}</p>
      </div>
      <BadgeDelta deltaType={deltaType(comp.variacion_pct)} size="xs" className="shrink-0">
        {variacion(comp.variacion_pct)}
      </BadgeDelta>
    </div>
  );
}

function EsqueletoComparar() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-28 w-full rounded-lg" />
      ))}
    </div>
  );
}

function ErrorComparar({
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
        {mensaje ?? "No se pudo calcular la comparativa. Vuelve a intentarlo."}
      </p>
      <Button variant="outline" size="sm" onClick={onReintentar} disabled={cargando}>
        <RefreshCw className={cn("h-4 w-4", cargando && "animate-spin")} />
        Reintentar
      </Button>
    </div>
  );
}
