/**
 * Sub-sección "Comparar periodos".
 *
 * Selecciona el periodo A ("Comparar con (antes)"), el periodo B ("Periodo actual") y
 * marca, consulta `api.metricasComparar` y muestra por métrica el valor A, el valor B
 * y la variación con flecha y color (Tremor BadgeDelta: verde sube / rojo baja).
 * Incluye el desglose `por_marca`. Por defecto A es el periodo inmediatamente ANTERIOR
 * adyacente a B (misma longitud); si los periodos elegidos no son comparables (distinta
 * duración o solape) se avisa, sin bloquear.
 *
 * Ambos periodos usan `SelectorTiempo` (periodos comunes · mes · fechas exactas),
 * así que se pueden comparar periodos ARBITRARIOS —p. ej. "mayo 2026" vs "abril 2026"
 * o dos rangos de fechas a medida—, no solo presets contra presets. El backend
 * (`/api/metricas/comparar`) acepta cualquier token (`mes:AAAA-MM`,
 * `rango:AAAA-MM-DD_AAAA-MM-DD` o preset).
 */
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, ArrowLeftRight, RefreshCw } from "lucide-react";
import * as React from "react";

import {
  marcaMetricasDesdeCanonica,
  marcaParam,
} from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { nombreMarca, numeroCompleto } from "@/lib/formato";
import { cn } from "@/lib/utils";
import type { ComparativaMetrica, ComparativaPorMarca, OpcionesMetricas } from "@/types";

import { MARCA_TODAS, SelectorTiempo } from "./Controles";
import { InsigniaComparativa } from "./InsigniaComparativa";
import { SeccionColapsable } from "./SeccionColapsable";
import { METRICAS } from "./metricas-meta";
import { diasDePeriodo, periodoAnterior, seSolapan } from "./rango";

/**
 * Metadatos de las métricas EXTRA de la comparativa (granulares + seguidores) que no están
 * en `METRICAS` (las 4 del reporte). Las inyecta el backend en `total.metricas` cuando el
 * desglose/serie de seguidores las trae; aquí solo definimos su etiqueta y formato. Son
 * conteos, así que se formatean con separador de miles.
 */
const ETIQUETAS_EXTRA: Record<string, string> = {
  likes: "Me gusta",
  comentarios: "Comentarios",
  compartidos: "Compartidos",
  guardados: "Guardados",
  video_views: "Reproducciones",
  clics_enlace: "Clics enlace",
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
  // null revienta TODA la página de Analíticas (error boundary).
  if (valor == null || !Number.isFinite(valor)) return "—";
  const meta = METRICAS.find((m) => m.metrica === metrica);
  // Métricas extra (granulares + seguidores) son conteos: separador de miles es-MX.
  return meta ? meta.completo(valor) : numeroCompleto(valor);
}

/**
 * Avisos de COMPARABILIDAD entre los dos periodos: distinta duración (la variación de
 * conteos no es comparable) y solape (la comparación no es fiable). Solo avisa: no
 * bloquea, comparar periodos arbitrarios sigue permitido.
 */
function AvisosComparabilidad({ rangoA, rangoB }: { rangoA: string; rangoB: string }) {
  const diasA = diasDePeriodo(rangoA);
  const diasB = diasDePeriodo(rangoB);
  const distintaDuracion = diasA != null && diasB != null && diasA !== diasB;
  const solapados = seSolapan(rangoA, rangoB);
  if (!distintaDuracion && !solapados) return null;
  return (
    <div className="space-y-2">
      {distintaDuracion && (
        <p
          className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200"
          role="status"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            Periodos con distinta duración ({diasA} vs {diasB} días): variación no comparable.
          </span>
        </p>
      )}
      {solapados && (
        <p
          className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200"
          role="status"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>Los periodos se solapan: la comparación no es fiable.</span>
        </p>
      )}
    </div>
  );
}

export function CompararPeriodos({
  opciones,
  rangoActual,
}: {
  opciones: OpcionesMetricas;
  /** Periodo seleccionado arriba: se usa como periodo B (actual) por defecto. */
  rangoActual?: string;
}) {
  const rangos = opciones.rangos;
  // B (actual) hereda el periodo que se está viendo arriba; A (antes) parte del
  // periodo inmediatamente ANTERIOR de la misma longitud, para que la comparativa
  // sea comparable por defecto (misma duración, sin solape).
  const rangoBInicial = rangoActual ?? rangos[0]?.id ?? "";
  const rangoAInicial =
    periodoAnterior(rangoBInicial) ??
    rangos.find((r) => r.id !== rangoBInicial)?.id ??
    rangos[0]?.id ??
    "";
  const [rangoA, setRangoA] = React.useState(rangoAInicial);
  const [rangoB, setRangoB] = React.useState(rangoBInicial);
  // ¿El usuario eligió A a mano? Mientras no lo haga, A sigue derivándose de B.
  const usuarioTocoA = React.useRef(false);

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

  // Si arriba cambia el periodo visible, lo reflejamos como periodo B (actual) y,
  // mientras el usuario no haya tocado A a mano, re-derivamos A como su anterior
  // adyacente (misma longitud) para mantener la comparativa comparable.
  React.useEffect(() => {
    if (!rangoActual) return;
    setRangoB(rangoActual);
    if (!usuarioTocoA.current) {
      setRangoA(
        periodoAnterior(rangoActual) ??
          rangos.find((r) => r.id !== rangoActual)?.id ??
          rangos[0]?.id ??
          "",
      );
    }
  }, [rangoActual, rangos]);

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
      icono={ArrowLeftRight}
      acciones={
        <div className="grid grid-cols-1 gap-3 sm:flex sm:flex-wrap sm:items-center">
          <div className="flex items-center gap-2">
            <span className="w-28 shrink-0 text-xs font-medium text-muted-foreground sm:w-auto">
              Comparar con
            </span>
            <SelectorTiempo
              rangos={rangos}
              valor={rangoA}
              onCambio={(token) => {
                usuarioTocoA.current = true;
                setRangoA(token);
              }}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="w-28 shrink-0 text-xs font-medium text-muted-foreground sm:w-auto">
              Periodo actual
            </span>
            <SelectorTiempo rangos={rangos} valor={rangoB} onCambio={setRangoB} />
          </div>
        </div>
      }
      contentClassName="space-y-6"
    >
      {!habilitado ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Selecciona dos periodos
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

            <AvisosComparabilidad rangoA={rangoA} rangoB={rangoB} />

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

/** Tarjeta destacada de una métrica con valor A, valor B y su insignia comparativa
 * (variación relativa para conteos, diferencia en pts para engagement, "Nuevo" para
 * arranques desde cero; ver InsigniaComparativa). */
function TarjetaComparativa({ comp }: { comp: ComparativaMetrica }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-sm font-medium text-muted-foreground">
          {etiquetaMetrica(comp.metrica)}
        </p>
        <InsigniaComparativa comp={comp} />
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
      <InsigniaComparativa comp={comp} />
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
