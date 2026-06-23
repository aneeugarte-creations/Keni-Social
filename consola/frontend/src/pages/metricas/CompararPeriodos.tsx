/**
 * Sub-sección "Comparar periodos".
 *
 * Selecciona el periodo A ("Comparar con (antes)"), el periodo B ("Periodo actual") y
 * marca, consulta `api.metricasComparar` y pinta una tabla con una fila por métrica:
 * el valor del periodo actual (B), el anterior (A) y la variación (`InsigniaComparativa`).
 * Bajo los totales, el desglose `por_marca` como grupos de filas. Qué columnas se ven y en
 * qué orden lo decide el editor de campos de la cabecera (`vistaConfig.columnas.comparativa`).
 * Por defecto A es el periodo inmediatamente ANTERIOR adyacente a B (misma longitud); si los
 * periodos elegidos no son comparables (distinta duración o solape) se avisa, sin bloquear.
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
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { nombreMarca, numeroCompleto } from "@/lib/formato";
import { cn } from "@/lib/utils";
import type { ComparativaMetrica, ComparativaPorMarca, OpcionesMetricas } from "@/types";

import type { ColumnaMeta } from "./columnasMeta";
import { MARCA_TODAS, SelectorTiempo } from "./Controles";
import { InsigniaComparativa } from "./InsigniaComparativa";
import { METRICAS } from "./metricas-meta";
import { diasDePeriodo, periodoAnterior, seSolapan } from "./rango";
import { Seccion } from "./Seccion";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

/**
 * Columnas FIJAS de la tabla comparativa: la métrica como etiqueta de fila, los dos periodos
 * (actual = B, antes = A) y su variación. El id "comparativa" persiste orden/ocultas en
 * `vistaConfig.columnas`, así el editor de campos de la cabecera las muestra/oculta y reordena.
 */
const TABLA_COMPARATIVA = "comparativa";

const COLUMNAS: ColumnaMeta[] = [
  { id: "metrica", etiqueta: "Métrica" },
  { id: "actual", etiqueta: "Periodo actual" },
  { id: "antes", etiqueta: "Antes" },
  { id: "variacion", etiqueta: "Variación" },
];

const IDS_COMPARATIVA = COLUMNAS.map((c) => c.id);

/** Cabecera de una columna: la métrica alineada a la izquierda, el resto a la derecha. */
function encabezado(id: string) {
  const etiqueta = COLUMNAS.find((c) => c.id === id)?.etiqueta ?? id;
  if (id === "metrica") {
    return (
      <TableHead key={id} className="pl-6">
        {etiqueta}
      </TableHead>
    );
  }
  return (
    <TableHead key={id} className="pr-6 text-right last:pr-6">
      {etiqueta}
    </TableHead>
  );
}

/** Celda de una métrica para la columna `id` (valor de un periodo o insignia de variación). */
function celdaComp(comp: ComparativaMetrica, id: string) {
  if (id === "metrica") {
    return (
      <TableCell key={id} className="pl-6 font-medium">
        {etiquetaMetrica(comp.metrica)}
      </TableCell>
    );
  }
  if (id === "variacion") {
    return (
      <TableCell key={id} className="pr-6 last:pr-6">
        <div className="flex justify-end">
          <InsigniaComparativa comp={comp} />
        </div>
      </TableCell>
    );
  }
  const valor = id === "antes" ? comp.a : comp.b;
  return (
    <TableCell key={id} className="pr-6 text-right tabular-nums last:pr-6">
      {formatoValor(comp.metrica, valor)}
    </TableCell>
  );
}

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

  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA_COMPARATIVA]);
  const cfg = cfgGuardada ?? { orden: IDS_COMPARATIVA, ocultas: [] };
  const columnas = columnasVisibles(IDS_COMPARATIVA, cfg);

  return (
    <Seccion
      id="comparativa"
      titulo="Comparar periodos"
      icono={ArrowLeftRight}
      tablaId={TABLA_COMPARATIVA}
      columnas={COLUMNAS}
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

          <Card className="overflow-hidden py-2">
            <Table>
              <TableHeader>
                <TableRow>{columnas.map(encabezado)}</TableRow>
              </TableHeader>
              <TableBody>
                {/* Totales: una fila por métrica con A, B y variación. */}
                {data.total.metricas.map((comp) => (
                  <TableRow key={comp.metrica}>
                    {columnas.map((id) => celdaComp(comp, id))}
                  </TableRow>
                ))}
                {/* Desglose por marca: cada marca como un grupo de filas precedido por su nombre. */}
                {data.por_marca.map((pm) => (
                  <React.Fragment key={pm.marca_id}>
                    <TableRow className="bg-muted/30">
                      <TableCell
                        colSpan={columnas.length}
                        className="pl-6 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                      >
                        {etiquetaMarca(pm, opciones.marcas)}
                      </TableCell>
                    </TableRow>
                    {pm.comparativa.map((comp) => (
                      <TableRow key={comp.metrica}>
                        {columnas.map((id) => celdaComp(comp, id))}
                      </TableRow>
                    ))}
                  </React.Fragment>
                ))}
              </TableBody>
            </Table>
          </Card>
        </>
      )}
    </Seccion>
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
