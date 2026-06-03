/**
 * Lista COMPLETA de piezas del periodo (todas, no solo top/peores), abrible.
 *
 * Tabla con TODAS las piezas que la fuente única emite para el periodo
 * (`/api/metricas/piezas-listado`). Sobre el listado:
 *   - FILTROS (client-side): buscador por título + red + línea editorial.
 *   - PAGINACIÓN POR DÍA: un día por página (pager Prev/Siguiente). Dentro del día,
 *     orden por vistas / engagement / clics (reúsa `useOrdenTabla`).
 *   - Cada fila muestra "Plataforma · Línea" y es ABRIBLE: abre el `DetallePieza`
 *     (métricas + granulares + curva histórica + velocidad).
 *
 * Sigue la marca/rango global del dashboard, como el resto de las secciones de detalle.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, ListChecks, Search } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { nombreRed, numeroCompacto, porcentaje } from "@/lib/formato";
import type { PiezaListado } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { DetallePieza } from "./DetallePieza";
import { useOrdenTabla } from "./useOrdenTabla";

type ClaveOrden = "visualizaciones" | "engagement_pct" | "clics_enlace";

const ACCESORES: Record<ClaveOrden, (p: PiezaListado) => number | string | null> = {
  visualizaciones: (p) => p.visualizaciones,
  engagement_pct: (p) => p.engagement_pct,
  clics_enlace: (p) => p.clics_enlace,
};

const TODAS = "__todas__";
const SIN_LINEA = "Sin línea";

/** Etiqueta legible de un día ISO (AAAA-MM-DD) en es-MX: "lun 1 jun 2026". */
function etiquetaDia(iso: string): string {
  const [a, m, d] = iso.split("-").map((n) => parseInt(n, 10));
  if (!a || !m || !d) return iso;
  const fecha = new Date(a, m - 1, d);
  return fecha.toLocaleDateString("es-MX", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function ListaPiezas({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Marca global del dashboard: la lista la sigue. */
  marcaActual?: string;
  /** Rango global del dashboard: el periodo listado. */
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const [busqueda, setBusqueda] = React.useState("");
  const [redFiltro, setRedFiltro] = React.useState(TODAS);
  const [lineaFiltro, setLineaFiltro] = React.useState(TODAS);
  const [diaIdx, setDiaIdx] = React.useState(0);
  const [seleccion, setSeleccion] = React.useState<PiezaListado | null>(null);
  const [detalleAbierto, setDetalleAbierto] = React.useState(false);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-listado", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasPiezasListado({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const piezas = React.useMemo(() => data?.piezas ?? [], [data]);

  // Opciones de los filtros, derivadas del listado completo (no de lo ya filtrado).
  const redesDisponibles = React.useMemo(
    () => Array.from(new Set(piezas.map((p) => p.plataforma).filter(Boolean))).sort(),
    [piezas],
  );
  const lineasDisponibles = React.useMemo(() => {
    const set = new Set<string>();
    for (const p of piezas) set.add(p.linea || SIN_LINEA);
    return Array.from(set).sort((a, b) =>
      // "Sin línea" siempre al final; el resto alfabético.
      a === SIN_LINEA ? 1 : b === SIN_LINEA ? -1 : a.localeCompare(b, "es-MX"),
    );
  }, [piezas]);

  // Filtro combinado: título (texto) + red + línea.
  const filtradas = React.useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return piezas.filter((p) => {
      if (q && !(p.titulo || "").toLowerCase().includes(q)) return false;
      if (redFiltro !== TODAS && p.plataforma !== redFiltro) return false;
      if (lineaFiltro !== TODAS && (p.linea || SIN_LINEA) !== lineaFiltro) return false;
      return true;
    });
  }, [piezas, busqueda, redFiltro, lineaFiltro]);

  // Días presentes en lo filtrado, del más reciente al más antiguo (una "página" = un día).
  const dias = React.useMemo(() => {
    const set = new Set<string>();
    for (const p of filtradas) if (p.publicado) set.add(p.publicado);
    return Array.from(set).sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
  }, [filtradas]);

  // Si cambian los filtros, el día visible puede quedar fuera de rango: lo reanclamos.
  React.useEffect(() => {
    setDiaIdx((i) => (i >= dias.length ? 0 : i));
  }, [dias.length]);

  const diaActual = dias[Math.min(diaIdx, Math.max(dias.length - 1, 0))] ?? "";
  const piezasDelDia = React.useMemo(
    () => filtradas.filter((p) => p.publicado === diaActual),
    [filtradas, diaActual],
  );

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<PiezaListado, ClaveOrden>(
    piezasDelDia,
    ACCESORES,
    { clave: "visualizaciones", direccion: "desc" },
  );

  function abrir(pieza: PiezaListado) {
    setSeleccion(pieza);
    setDetalleAbierto(true);
  }

  const hayFiltros = busqueda.trim() !== "" || redFiltro !== TODAS || lineaFiltro !== TODAS;

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Todas las piezas del periodo</CardTitle>
        </div>
        <p className="text-sm text-muted-foreground">
          Listado completo de la fuente. Filtra por red o línea, navega día a día y toca
          una pieza para ver su desglose y su curva histórica.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="relative max-w-sm flex-1">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar por título…"
              className="pl-8"
              aria-label="Buscar piezas por título"
            />
          </div>
          <Select value={redFiltro} onValueChange={setRedFiltro}>
            <SelectTrigger className="w-full sm:w-44" aria-label="Filtrar por red">
              <SelectValue placeholder="Red" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODAS}>Todas las redes</SelectItem>
              {redesDisponibles.map((r) => (
                <SelectItem key={r} value={r}>
                  {nombreRed(r)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={lineaFiltro} onValueChange={setLineaFiltro}>
            <SelectTrigger className="w-full sm:w-48" aria-label="Filtrar por línea">
              <SelectValue placeholder="Línea" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODAS}>Todas las líneas</SelectItem>
              {lineasDisponibles.map((l) => (
                <SelectItem key={l} value={l}>
                  {l}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>

      <CardContent className="px-0 pb-0">
        {isPending ? (
          <Skeleton className="mx-6 mb-6 h-72 rounded-lg" />
        ) : isError ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No se pudo cargar el listado de piezas.
          </p>
        ) : piezas.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Sin piezas en este periodo.
          </p>
        ) : dias.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Ninguna pieza coincide con los filtros.
          </p>
        ) : (
          <>
            {/* Pager por día: un día por página, del más reciente al más antiguo. */}
            <div className="flex items-center justify-between gap-3 px-6 pb-3">
              <div>
                <p className="text-sm font-semibold capitalize text-foreground">
                  {etiquetaDia(diaActual)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {piezasDelDia.length} {piezasDelDia.length === 1 ? "pieza" : "piezas"} · día{" "}
                  {diaIdx + 1} de {dias.length}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setDiaIdx((i) => Math.max(0, i - 1))}
                  disabled={diaIdx <= 0}
                  aria-label="Día más reciente"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setDiaIdx((i) => Math.min(dias.length - 1, i + 1))}
                  disabled={diaIdx >= dias.length - 1}
                  aria-label="Día más antiguo"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pieza</TableHead>
                  <CabeceraOrdenable
                    activa={estado.clave === "visualizaciones"}
                    direccion={estado.direccion}
                    onClick={() => alClicar("visualizaciones")}
                    alinear="right"
                    className="text-right"
                  >
                    Vistas
                  </CabeceraOrdenable>
                  <CabeceraOrdenable
                    activa={estado.clave === "engagement_pct"}
                    direccion={estado.direccion}
                    onClick={() => alClicar("engagement_pct")}
                    alinear="right"
                    className="text-right"
                  >
                    Eng.
                  </CabeceraOrdenable>
                  <CabeceraOrdenable
                    activa={estado.clave === "clics_enlace"}
                    direccion={estado.direccion}
                    onClick={() => alClicar("clics_enlace")}
                    alinear="right"
                    className="hidden text-right sm:table-cell"
                  >
                    Clics
                  </CabeceraOrdenable>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filasOrdenadas.map((p) => (
                  <FilaPieza key={p.id} pieza={p} onAbrir={() => abrir(p)} />
                ))}
              </TableBody>
            </Table>
            <p className="px-6 py-3 text-xs text-muted-foreground">
              {hayFiltros
                ? `${filtradas.length} de ${piezas.length} piezas (filtrado) · ${dias.length} días`
                : `${piezas.length} piezas · ${dias.length} días`}
            </p>
          </>
        )}
      </CardContent>

      <DetallePieza
        pieza={seleccion}
        abierto={detalleAbierto}
        onOpenChange={setDetalleAbierto}
      />
    </Card>
  );
}

function FilaPieza({ pieza, onAbrir }: { pieza: PiezaListado; onAbrir: () => void }) {
  const titulo = pieza.titulo || "(sin título)";
  // Subtítulo: plataforma · línea (la línea cae a "Sin línea" cuando no es atribuible).
  const linea = pieza.linea || SIN_LINEA;

  return (
    <TableRow
      onClick={onAbrir}
      tabIndex={0}
      role="button"
      aria-label={`Ver detalle de "${titulo}"`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onAbrir();
        }
      }}
      className="cursor-pointer"
    >
      <TableCell className="max-w-[18rem]">
        <span className="block truncate font-medium" title={titulo}>
          {titulo}
        </span>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          {nombreRed(pieza.plataforma)} · {linea}
          {pieza.url ? (
            <a
              href={pieza.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center underline-offset-4 hover:underline"
              aria-label="Abrir el post en la red"
            >
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          ) : null}
        </span>
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {numeroCompacto(pieza.visualizaciones)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {porcentaje(pieza.engagement_pct)}
      </TableCell>
      <TableCell className="hidden text-right tabular-nums sm:table-cell">
        {pieza.clics_enlace == null ? "—" : numeroCompacto(pieza.clics_enlace)}
      </TableCell>
    </TableRow>
  );
}
