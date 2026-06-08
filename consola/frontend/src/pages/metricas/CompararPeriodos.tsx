/**
 * Sub-sección "Comparar periodos".
 *
 * Selecciona Periodo A (origen), Periodo B (comparado) y marca, consulta
 * `api.metricasComparar` y muestra por métrica el valor A, el valor B y la variación
 * con flecha y color (Tremor BadgeDelta: verde sube / rojo baja). Incluye el desglose
 * `por_marca`.
 *
 * Ambos periodos usan `SelectorTiempo` (atajos · mes concreto · rango personalizado),
 * así que se pueden comparar periodos ARBITRARIOS —p. ej. "mayo 2026" vs "abril 2026"
 * o dos rangos de fechas a medida—, no solo presets contra presets. El backend
 * (`/api/metricas/comparar`) acepta cualquier token (`mes:AAAA-MM`,
 * `rango:AAAA-MM-DD_AAAA-MM-DD` o preset).
 */
import { useQuery } from "@tanstack/react-query";
import { BadgeDelta, type DeltaType } from "@tremor/react";
import { AlertCircle, RefreshCw } from "lucide-react";
import * as React from "react";

import {
  marcaMetricasDesdeCanonica,
  marcaParam,
} from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { nombreMarca, numeroCompleto, variacion } from "@/lib/formato";
import { cn } from "@/lib/utils";
import type { ComparativaMetrica, ComparativaPorMarca, OpcionesMetricas } from "@/types";

import { MARCA_TODAS, SelectorTiempo } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";
import { METRICAS } from "./metricas-meta";

/**
 * Metadatos de las métricas EXTRA de la comparativa (granulares + seguidores) que no están
 * en `METRICAS` (las 4 del reporte). Las inyecta el backend en `total.metricas` cuando el
 * desglose/serie de seguidores las trae; aquí solo definimos su etiqueta y formato. Son
 * conteos, así que se formatean con separador de miles.
 */
const ETIQUETAS_EXTRA: Record<string, string> = {
  likes: "Likes",
  comentarios: "Comentarios",
  compartidos: "Compartidos",
  guardados: "Guardados",
  video_views: "Reproducciones",
  clics_enlace: "Clicks",
  seguidores_netos: "Seguidores netos",
};

/** Etiqueta legible de una métrica del backend según su nombre interno. */
function etiquetaMetrica(metrica: string): string {
  return (
    METRICAS.find((m) => m.metrica === metrica)?.etiqueta ?? ETIQUETAS_EXTRA[metrica] ?? metrica
  );
}

/**
 * Nombre legible de una marca del desglose: prioriza el catálogo de opciones
 * (resuelto por `marca_id`); si el id no está, cae al nombre que ya trae el backend
 * (`pm.marca`), nunca al id crudo (degradación honesta).
 */
function etiquetaMarca(
  pm: ComparativaPorMarca,
  marcas: OpcionesMetricas["marcas"],
): string {
  const porCatalogo = nombreMarca(pm.marca_id, marcas);
  return porCatalogo !== pm.marca_id ? porCatalogo : pm.marca || pm.marca_id;
}

/** Formatea un valor según el tipo de métrica (porcentaje vs número). */
function formatoValor(metrica: string, valor: number | null): string {
  // Valor ausente (p. ej. engagement no comparable entre redes heterogéneas, o una
  // métrica que ya no se mide) -> "—". Sin esta guardia, `valor.toLocaleString` sobre
  // null reventaba TODA la página de Analíticas (error boundary).
  if (valor == null || !Number.isFinite(valor)) return "—";
  const meta = METRICAS.find((m) => m.metrica === metrica);
  // Métricas extra (granulares + seguidores) son conteos: separador de miles es-MX.
  return meta ? meta.completo(valor) : numeroCompleto(valor);
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
  rangoActual,
}: {
  opciones: OpcionesMetricas;
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

  // La MARCA la manda SIEMPRE el switch global de la barra superior (`useMarcaActiva`):
  // la comparativa no tiene selector propio. `marcaActiva` es el id canónico (o null =
  // "Todas"); esta frontera habla en `id_metricas`, así que lo traducimos y validamos
  // contra el catálogo (fuera de catálogo → agregado "Todas").
  const { marcaActiva } = useMarcaActiva();
  const marca = React.useMemo(() => {
    if (!marcaActiva) return MARCA_TODAS;
    const idMetricas = marcaMetricasDesdeCanonica(marcaActiva);
    return opciones.marcas.some((m) => m.id === idMetricas) ? idMetricas : MARCA_TODAS;
  }, [marcaActiva, opciones.marcas]);

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
    <SeccionColapsable
      titulo="Comparar periodos"
      acciones={
        <div className="grid grid-cols-1 gap-3 sm:flex sm:flex-wrap sm:items-center">
          <div className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-xs font-medium text-muted-foreground sm:w-auto">
              Periodo A
            </span>
            <SelectorTiempo rangos={rangos} valor={rangoA} onCambio={setRangoA} />
          </div>
          <div className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-xs font-medium text-muted-foreground sm:w-auto">
              Periodo B
            </span>
            <SelectorTiempo rangos={rangos} valor={rangoB} onCambio={setRangoB} />
          </div>
        </div>
      }
      contentClassName="space-y-6"
    >
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
                      <p className="mb-3 text-sm font-medium">
                        {etiquetaMarca(pm, opciones.marcas)}
                      </p>
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
    </SeccionColapsable>
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
