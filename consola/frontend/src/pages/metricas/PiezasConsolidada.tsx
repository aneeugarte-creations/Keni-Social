/**
 * Tabla CONSOLIDADA de piezas del periodo (fusiona Lista + Top/Peores + Rendimiento).
 *
 * UNA sola tabla rica con todo el kit, consistente:
 *   - Filtros (client-side): marca, línea editorial, red y buscador por título.
 *   - Estadísticas del conjunto filtrado: nº de piezas, vistas media/mediana y
 *     engagement medio/mediana (top/peores = ordenar por la columna Vistas).
 *   - Orden por columna (vistas / engagement / clics) reusando `useOrdenTabla`.
 *   - Paginación POR DÍA (un día por página, pager Prev/Siguiente).
 *   - Cada fila muestra "Plataforma · Línea (· Marca)" + badge de rendimiento relativo y
 *     es ABRIBLE: drill-down al `DetallePieza` (métricas + granulares + histórico + velocidad).
 *
 * Datos de `/api/metricas/piezas-listado` (TODAS las piezas del rango, con su línea,
 * marca y granulares). Sigue el rango global; el filtro por marca es propio de la tabla
 * (lo controla también el drill-down desde la tabla por marca).
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, ListChecks, Search } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SeccionColapsable } from "./SeccionColapsable";
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
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { api } from "@/lib/api";
import {
  nombreFormato,
  nombreMarca,
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
} from "@/lib/formato";
import type { MarcaDisponible, PiezaListado } from "@/types";

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

/** Media aritmética (null si no hay datos). */
function media(nums: number[]): number | null {
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

/** Mediana (null si no hay datos). */
function mediana(nums: number[]): number | null {
  if (nums.length === 0) return null;
  const s = [...nums].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Etiqueta legible de un día ISO (AAAA-MM-DD) en es-MX: "lun 1 jun 2026". */
function etiquetaDia(iso: string): string {
  const [a, m, d] = iso.split("-").map((n) => parseInt(n, 10));
  if (!a || !m || !d) return iso;
  return new Date(a, m - 1, d).toLocaleDateString("es-MX", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function PiezasConsolidada({
  marcaActual = MARCA_TODAS,
  rangoActual,
  marcas,
  marcaFiltro,
  onMarcaFiltroChange,
}: {
  /** Marca global del dashboard: acota la consulta (todas si "todas"). */
  marcaActual?: string;
  /** Rango global del dashboard: el periodo listado. */
  rangoActual?: string;
  /** Catálogo {id, nombre} para resolver el id crudo de marca de cada pieza. */
  marcas: MarcaDisponible[];
  /** Filtro de marca controlado (lo fija el drill-down desde la tabla por marca). */
  marcaFiltro?: string;
  onMarcaFiltroChange?: (marca: string) => void;
}) {
  const marca_ = marcaParam(marcaActual);
  const [busqueda, setBusqueda] = React.useState("");
  const [redFiltro, setRedFiltro] = React.useState(TODAS);
  const [lineaFiltro, setLineaFiltro] = React.useState(TODAS);
  const [marcaInterna, setMarcaInterna] = React.useState(TODAS);
  const [diaIdx, setDiaIdx] = React.useState(0);
  const [seleccion, setSeleccion] = React.useState<PiezaListado | null>(null);
  const [detalleAbierto, setDetalleAbierto] = React.useState(false);

  // Filtro de marca: controlado por el padre (drill-down) si pasa `onMarcaFiltroChange`;
  // si no, estado interno. En forma pública "" = todas; internamente el sentinela TODAS.
  const controlado = onMarcaFiltroChange !== undefined;
  const marcaSel = controlado ? (marcaFiltro ? marcaFiltro : TODAS) : marcaInterna;
  const setMarcaSel = (v: string) => {
    if (controlado) onMarcaFiltroChange?.(v === TODAS ? "" : v);
    else setMarcaInterna(v);
  };

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-listado", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasPiezasListado({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const piezas = React.useMemo(() => data?.piezas ?? [], [data]);

  // Opciones de los filtros, derivadas del listado completo.
  const marcasDisponibles = React.useMemo(
    () => Array.from(new Set(piezas.map((p) => p.cuenta).filter(Boolean) as string[])).sort(),
    [piezas],
  );
  const redesDisponibles = React.useMemo(
    () => Array.from(new Set(piezas.map((p) => p.plataforma).filter(Boolean))).sort(),
    [piezas],
  );
  const lineasDisponibles = React.useMemo(() => {
    const set = new Set<string>();
    for (const p of piezas) set.add(p.linea || SIN_LINEA);
    return Array.from(set).sort((a, b) =>
      a === SIN_LINEA ? 1 : b === SIN_LINEA ? -1 : a.localeCompare(b, "es-MX"),
    );
  }, [piezas]);

  // Filtro combinado: marca + línea + red + título.
  const filtradas = React.useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return piezas.filter((p) => {
      if (marcaSel !== TODAS && p.cuenta !== marcaSel) return false;
      if (redFiltro !== TODAS && p.plataforma !== redFiltro) return false;
      if (lineaFiltro !== TODAS && (p.linea || SIN_LINEA) !== lineaFiltro) return false;
      if (q && !(p.titulo || "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [piezas, marcaSel, redFiltro, lineaFiltro, busqueda]);

  // Estadísticas del conjunto FILTRADO (reflejan los filtros activos).
  const stats = React.useMemo(() => {
    const vistas = filtradas.map((p) => p.visualizaciones);
    const eng = filtradas.map((p) => p.engagement_pct);
    return {
      total: filtradas.length,
      vistasMedia: media(vistas),
      vistasMediana: mediana(vistas),
      engMedia: media(eng),
      engMediana: mediana(eng),
    };
  }, [filtradas]);

  // Días presentes en lo filtrado, del más reciente al más antiguo (una página = un día).
  const dias = React.useMemo(() => {
    const set = new Set<string>();
    for (const p of filtradas) if (p.publicado) set.add(p.publicado);
    return Array.from(set).sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
  }, [filtradas]);

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

  const variasMarcas = marcasDisponibles.length > 1;
  const hayFiltros =
    busqueda.trim() !== "" ||
    redFiltro !== TODAS ||
    lineaFiltro !== TODAS ||
    marcaSel !== TODAS;

  return (
    <>
      <SeccionColapsable
        titulo="Piezas del periodo"
        icono={ListChecks}
        descripcion="Todas las piezas del rango. Filtra por marca, línea o red; ordena por columna (Vistas desc = top, asc = peores); navega día a día y toca una pieza para su detalle."
        contentClassName="px-0 pb-0"
      >
        <div className="space-y-3 px-6 pb-3">
        {/* Filtros */}
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
          {variasMarcas && (
            <Select value={marcaSel} onValueChange={setMarcaSel}>
              <SelectTrigger className="w-full sm:w-44" aria-label="Filtrar por marca">
                <SelectValue placeholder="Marca" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODAS}>Todas las marcas</SelectItem>
                {marcasDisponibles.map((m) => (
                  <SelectItem key={m} value={m}>
                    {nombreMarca(m, marcas)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
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
        </div>

        {/* Estadísticas del conjunto filtrado */}
        {!isPending && !isError && piezas.length > 0 && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <TarjetaKpi etiqueta="Piezas" valor={numeroCompleto(stats.total)} />
            <TarjetaKpi
              etiqueta="Vistas media · mediana"
              valor={`${stats.vistasMedia == null ? "—" : numeroCompacto(stats.vistasMedia)} · ${
                stats.vistasMediana == null ? "—" : numeroCompacto(stats.vistasMediana)
              }`}
            />
            <TarjetaKpi
              etiqueta="Engagement medio"
              valor={stats.engMedia == null ? "—" : porcentaje(stats.engMedia)}
            />
            <TarjetaKpi
              etiqueta="Engagement mediana"
              valor={stats.engMediana == null ? "—" : porcentaje(stats.engMediana)}
            />
          </div>
        )}
        </div>

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
            {/* Pager por día */}
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
                  <FilaPieza
                    key={p.id}
                    pieza={p}
                    marcas={marcas}
                    mostrarMarca={variasMarcas}
                    onAbrir={() => abrir(p)}
                  />
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
      </SeccionColapsable>

      <DetallePieza
        pieza={seleccion}
        abierto={detalleAbierto}
        onOpenChange={setDetalleAbierto}
      />
    </>
  );
}

function FilaPieza({
  pieza,
  marcas,
  mostrarMarca,
  onAbrir,
}: {
  pieza: PiezaListado;
  marcas: MarcaDisponible[];
  mostrarMarca: boolean;
  onAbrir: () => void;
}) {
  const titulo = pieza.titulo || "(sin título)";
  // Subtítulo: plataforma · línea (· marca cuando hay varias). Formato como sufijo
  // discreto solo si existe (evita "Sin formato" en todas).
  const partes = [
    nombreRed(pieza.plataforma),
    pieza.linea || SIN_LINEA,
    mostrarMarca && pieza.cuenta ? nombreMarca(pieza.cuenta, marcas) : "",
    pieza.formato ? nombreFormato(pieza.formato) : "",
  ].filter(Boolean);

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
      <TableCell className="max-w-[20rem]">
        <span className="block truncate font-medium" title={titulo}>
          {titulo}
        </span>
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{partes.join(" · ")}</span>
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
          {pieza.rendimiento_relativo != null && (
            <Badge
              variant={pieza.rendimiento_relativo >= 1 ? "ok" : "error"}
              title="Vistas de la pieza ÷ mediana de vistas de su red"
            >
              {pieza.rendimiento_relativo.toLocaleString("es-MX", { maximumFractionDigits: 1 })}×
              mediana
            </Badge>
          )}
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
