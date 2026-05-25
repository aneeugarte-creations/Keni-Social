import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CircleDollarSign,
  Coins,
  Loader2,
  type LucideIcon,
  Play,
  RefreshCw,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import type { BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { costeUsd, duracion, numeroCompacto, numeroCompleto } from "@/pages/metricas/formato";
import type {
  AgregadoPorAgente,
  AgregadoPorDia,
  EstadoRun,
  RespuestaRunsAgregados,
  Run,
  TotalRuns,
} from "@/types";

/** Centinela del filtro "todos los agentes". */
const AGENTE_TODOS = "__todos__";

/** Sondeo suave del Monitor mientras haya algún run en curso. */
const INTERVALO_SONDEO_MS = 3000;

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Formatea una fecha ISO completa en formato corto es-MX; tolera inválidas. */
function formatearFecha(iso: string): string {
  if (!iso) return "—";
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(fecha);
}

/** Formatea un día (`YYYY-MM-DD`) en es-MX; tolera valores inesperados. */
function formatearDia(dia: string): string {
  if (!dia) return "—";
  // Interpretamos como fecha local a mediodía para evitar desfases de zona.
  const fecha = new Date(`${dia}T12:00:00`);
  if (Number.isNaN(fecha.getTime())) return dia;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(fecha);
}

/** Etiqueta legible (es-MX) del modo de un run. */
function etiquetaModo(modo: Run["modo"]): string {
  return modo === "interactivo" ? "Interactivo" : "Headless";
}

/** `true` mientras el run está en curso. */
function estaEjecutando(estado: EstadoRun): boolean {
  return estado === "ejecutando";
}

/** Etiqueta + variante de badge para el estado de un run. */
function presentacionEstado(estado: EstadoRun): {
  texto: string;
  variante: BadgeProps["variant"];
  spinner?: boolean;
} {
  switch (estado) {
    case "completado":
      return { texto: "Completado", variante: "ok" };
    case "error":
      return { texto: "Error", variante: "error" };
    case "ejecutando":
      return { texto: "Ejecutando…", variante: "aviso", spinner: true };
    case "lanzado":
      return { texto: "Lanzado", variante: "secondary" };
    default:
      return { texto: estado, variante: "secondary" };
  }
}

/** Tarjeta KPI de un agregado (icono con acento + valor grande). */
function TarjetaKpi({
  etiqueta,
  valor,
  titulo,
  icono: Icono,
  acentoTexto,
  acentoFondo,
}: {
  etiqueta: string;
  valor: string;
  titulo?: string;
  icono: LucideIcon;
  acentoTexto: string;
  acentoFondo: string;
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="flex items-start justify-between gap-3 p-5">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium text-muted-foreground">{etiqueta}</p>
          <p className="truncate text-3xl font-semibold tracking-tight" title={titulo ?? valor}>
            {valor}
          </p>
        </div>
        <div
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
            acentoFondo,
            acentoTexto,
          )}
        >
          <Icono className="h-5 w-5" />
        </div>
      </CardContent>
    </Card>
  );
}

/** Fila de KPIs con los totales del periodo disponible. */
function KpisTotales({ total }: { total: TotalRuns }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <TarjetaKpi
        etiqueta="Coste total"
        valor={costeUsd(total.coste_usd)}
        icono={CircleDollarSign}
        acentoTexto="text-emerald-600 dark:text-emerald-400"
        acentoFondo="bg-emerald-500/10"
      />
      <TarjetaKpi
        etiqueta="Tokens"
        valor={numeroCompacto(total.tokens)}
        titulo={numeroCompleto(total.tokens)}
        icono={Coins}
        acentoTexto="text-sky-600 dark:text-sky-400"
        acentoFondo="bg-sky-500/10"
      />
      <TarjetaKpi
        etiqueta="Ejecuciones"
        valor={numeroCompleto(total.runs)}
        icono={Activity}
        acentoTexto="text-violet-600 dark:text-violet-400"
        acentoFondo="bg-violet-500/10"
      />
    </div>
  );
}

/** Mini-tabla de desglose por agente. */
function DesglosePorAgente({ filas }: { filas: AgregadoPorAgente[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por agente</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Agente</TableHead>
              <TableHead className="text-right">Runs</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Sin actividad por agente.
                </TableCell>
              </TableRow>
            ) : (
              filas.map((f) => (
                <TableRow key={f.agente}>
                  <TableCell className="pl-6 font-medium">{f.agente_nombre}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.runs)}
                  </TableCell>
                  <TableCell
                    className="text-right tabular-nums"
                    title={numeroCompleto(f.tokens)}
                  >
                    {numeroCompacto(f.tokens)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {costeUsd(f.coste_usd)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** Mini-tabla de desglose por día (más reciente primero). */
function DesglosePorDia({ filas }: { filas: AgregadoPorDia[] }) {
  // Por si el backend no lo ordena: mostramos del más reciente al más antiguo.
  const ordenadas = React.useMemo(
    () => [...filas].sort((a, b) => b.dia.localeCompare(a.dia)),
    [filas],
  );
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por día</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Día</TableHead>
              <TableHead className="text-right">Runs</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordenadas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Sin actividad por día.
                </TableCell>
              </TableRow>
            ) : (
              ordenadas.map((f) => (
                <TableRow key={f.dia}>
                  <TableCell className="pl-6 font-medium">{formatearDia(f.dia)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.runs)}
                  </TableCell>
                  <TableCell
                    className="text-right tabular-nums"
                    title={numeroCompleto(f.tokens)}
                  >
                    {numeroCompacto(f.tokens)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {costeUsd(f.coste_usd)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** Tabla principal de runs (recientes primero), con filtro por agente. */
function TablaRuns({ runs }: { runs: Run[] }) {
  const [agente, setAgente] = React.useState<string>(AGENTE_TODOS);

  // Catálogo de agentes presentes en la lista (id → nombre legible).
  const agentes = React.useMemo(() => {
    const mapa = new Map<string, string>();
    for (const r of runs) {
      if (r.agente) mapa.set(r.agente, r.agente_nombre || r.agente);
    }
    return Array.from(mapa, ([id, nombre]) => ({ id, nombre })).sort((a, b) =>
      a.nombre.localeCompare(b.nombre, "es-MX"),
    );
  }, [runs]);

  const filtrados = React.useMemo(
    () => (agente === AGENTE_TODOS ? runs : runs.filter((r) => r.agente === agente)),
    [runs, agente],
  );

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          Ejecuciones
          <Badge variant="secondary">{filtrados.length}</Badge>
        </CardTitle>
        <Select value={agente} onValueChange={setAgente}>
          <SelectTrigger className="w-full sm:w-[220px]" aria-label="Filtrar por agente">
            <SelectValue placeholder="Agente" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={AGENTE_TODOS}>Todos los agentes</SelectItem>
            {agentes.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                {a.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Agente</TableHead>
              <TableHead>Prompt</TableHead>
              <TableHead>Modo</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Fecha</TableHead>
              <TableHead className="text-right">Turnos</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="text-right">Coste</TableHead>
              <TableHead className="pr-6 text-right">Duración</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtrados.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
                  No hay ejecuciones para este filtro.
                </TableCell>
              </TableRow>
            ) : (
              filtrados.map((r) => {
                const { texto, variante, spinner } = presentacionEstado(r.estado);
                const m = r.metricas;
                return (
                  <TableRow key={r.id}>
                    <TableCell className="pl-6 font-medium">
                      {r.agente_nombre || r.agente || "—"}
                    </TableCell>
                    <TableCell className="max-w-[22rem]">
                      <span className="block truncate" title={r.prompt}>
                        {r.prompt || <span className="text-muted-foreground">Sin prompt</span>}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{etiquetaModo(r.modo)}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={variante} className={cn(spinner && "gap-1")}>
                        {spinner && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
                        {texto}
                      </Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatearFecha(r.fecha_inicio)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {m ? numeroCompleto(m.num_turns) : "—"}
                    </TableCell>
                    <TableCell
                      className="text-right tabular-nums"
                      title={m ? `Entrada / salida` : undefined}
                    >
                      {m
                        ? `${numeroCompacto(m.tokens_in)} / ${numeroCompacto(m.tokens_out)}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {m ? costeUsd(m.total_cost_usd) : "—"}
                    </TableCell>
                    <TableCell className="pr-6 text-right tabular-nums">
                      {m ? duracion(m.duration_ms) : "—"}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** Esqueleto de carga que imita la estructura del monitor. */
function EsqueletoMonitor() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
      <Skeleton className="h-80 w-full rounded-xl" />
    </div>
  );
}

/**
 * Página Monitor (Actividad IA): vista global de los runs de todos los agentes.
 *
 * Combina dos consultas independientes: los agregados (`GET /api/runs/agregados`)
 * para las tarjetas y desgloses, y el listado de runs (`GET /api/runs`) para la
 * tabla con filtro por agente. Cada bloque maneja su propio estado de carga;
 * un error en cualquiera de las dos consultas se muestra como bloque de error.
 */
export default function Monitor() {
  // Sondeo suave mientras haya algún run en curso: la lista se refresca y, si
  // hay actividad en vivo, también los agregados. Sin runs ejecutando, no hay
  // polling (devolvemos `false`).
  const runsQuery = useQuery({
    queryKey: ["runs", "lista"],
    queryFn: ({ signal }) => api.runs(signal),
    refetchInterval: (query) =>
      (query.state.data?.runs ?? []).some((r) => estaEjecutando(r.estado))
        ? INTERVALO_SONDEO_MS
        : false,
  });
  const hayEjecutando = (runsQuery.data?.runs ?? []).some((r) => estaEjecutando(r.estado));
  const agregadosQuery = useQuery({
    queryKey: ["runs", "agregados"],
    queryFn: ({ signal }) => api.runsAgregados(signal),
    refetchInterval: hayEjecutando ? INTERVALO_SONDEO_MS : false,
  });

  const cargando = agregadosQuery.isPending || runsQuery.isPending;
  const conError = agregadosQuery.isError || runsQuery.isError;
  const refrescando = agregadosQuery.isFetching || runsQuery.isFetching;

  function refrescar() {
    void agregadosQuery.refetch();
    void runsQuery.refetch();
  }

  const acciones = (
    <Button variant="outline" onClick={refrescar} disabled={refrescando}>
      <RefreshCw className={cn("h-4 w-4", refrescando && "animate-spin")} />
      Actualizar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Actividad IA"
        descripcion="Tokens, coste y duración de los runs de IA de todos los agentes."
        acciones={acciones}
      />

      {cargando ? (
        <EsqueletoMonitor />
      ) : conError ? (
        <BloqueError
          titulo="No se pudo cargar la actividad IA"
          mensaje={mensajeError(agregadosQuery.error ?? runsQuery.error)}
          onReintentar={refrescar}
          cargando={refrescando}
        />
      ) : (
        <Contenido agregados={agregadosQuery.data} runs={runsQuery.data.runs} />
      )}
    </>
  );
}

/** Cuerpo del monitor una vez resueltas ambas consultas. */
function Contenido({
  agregados,
  runs,
}: {
  agregados: RespuestaRunsAgregados;
  runs: Run[];
}) {
  const sinDatos = agregados.total.runs === 0 && runs.length === 0;
  if (sinDatos) {
    return (
      <EstadoVacio
        icono={Activity}
        titulo="Aún no hay actividad IA"
        texto="Cuando lances runs desde los agentes, aquí verás sus tokens, coste y duración."
        accion={
          <Button asChild variant="outline" size="sm">
            <Link to="/agentes">
              <Play className="h-4 w-4" />
              Ir a Agentes
            </Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <KpisTotales total={agregados.total} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DesglosePorAgente filas={agregados.por_agente} />
        <DesglosePorDia filas={agregados.por_dia} />
      </div>
      <TablaRuns runs={runs} />
    </div>
  );
}
