/**
 * Tabla CONSOLIDADA de piezas del periodo (fusiona Lista + Top/Peores + Rendimiento).
 *
 * UNA sola tabla rica con todo el kit, consistente:
 *   - Filtros (client-side): marca, línea editorial, red y buscador por título.
 *   - Estadísticas del conjunto filtrado: nº de piezas, vistas media/mediana y
 *     engagement medio/mediana (top/peores = ordenar por la columna Vistas).
 *   - Columnas ordenables (día / vistas / engagement / comentarios / compartidos /
 *     guardados / clics a enlace, estas con icono en la cabecera) reusando `useOrdenTabla`.
 *     El día es UNA columna más (ordenable), no el eje de la vista. Los clics a enlace
 *     (tráfico fuera de la red) absorben la antigua tabla "Tráfico web".
 *   - Paginación de 20 piezas por página sobre el conjunto filtrado+ordenado (pager
 *     Prev/Siguiente). Orden por defecto = Vistas desc, así la página 1 es el top 20
 *     del rango (p. ej. el top 20 del mes), no de un solo día.
 *   - Cada fila muestra "Plataforma · Línea (· Marca)" + badge de rendimiento relativo y
 *     es ABRIBLE: drill-down al `DetallePieza` (métricas + granulares + histórico + velocidad).
 *
 * Datos de `/api/metricas/piezas-listado` (TODAS las piezas del rango, con su línea,
 * marca y granulares). Sigue el rango global; el filtro por marca es propio de la tabla
 * (lo controla también el drill-down desde la tabla por marca).
 */
import { useQuery } from "@tanstack/react-query";
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  ListChecks,
  type LucideIcon,
  MessageCircle,
  MousePointerClick,
  Search,
  Share2,
} from "lucide-react";
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
  redCanonica,
  REDES_CANONICAS,
  rendimientoRel,
} from "@/lib/formato";
import type { MarcaDisponible, PiezaListado } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { DetallePieza } from "./DetallePieza";
import { useOrdenTabla } from "./useOrdenTabla";

/** Piezas de ejemplo en la vista compacta. */
const PREVIEW = 5;
/** Piezas por página al desplegar (listado completo paginado, sin scroll infinito). */
const POR_PAGINA = 20;

type ClaveOrden =
  | "publicado"
  | "visualizaciones"
  | "engagement_pct"
  | "comentarios"
  | "compartidos"
  | "guardados"
  | "clics_enlace";

const ACCESORES: Record<ClaveOrden, (p: PiezaListado) => number | string | null> = {
  // ISO (AAAA-MM-DD): la comparación de strings es cronológica.
  publicado: (p) => p.publicado || null,
  visualizaciones: (p) => p.visualizaciones,
  engagement_pct: (p) => p.engagement_pct,
  comentarios: (p) => p.comentarios,
  compartidos: (p) => p.compartidos,
  guardados: (p) => p.guardados,
  clics_enlace: (p) => p.clics_enlace,
};

/** Columnas con icono (logo) en la cabecera + número por fila, ordenables: el desglose
 * de interacción más los clics a enlace (tráfico fuera de la red, clave en Facebook). */
const COLS_INTERACCION: Array<{ clave: ClaveOrden; etiqueta: string; icono: LucideIcon }> = [
  { clave: "comentarios", etiqueta: "Comentarios", icono: MessageCircle },
  { clave: "compartidos", etiqueta: "Compartidos", icono: Share2 },
  { clave: "guardados", etiqueta: "Guardados", icono: Bookmark },
  { clave: "clics_enlace", etiqueta: "Clics a enlace", icono: MousePointerClick },
];

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

/** Etiqueta compacta de un día ISO (AAAA-MM-DD) en es-MX para la columna: "1 jun". */
function etiquetaDiaCorto(iso: string): string {
  const [a, m, d] = (iso || "").split("-").map((n) => parseInt(n, 10));
  if (!a || !m || !d) return "—";
  return new Date(a, m - 1, d).toLocaleDateString("es-MX", {
    day: "numeric",
    month: "short",
  });
}

export function PiezasConsolidada({
  marcaActual = MARCA_TODAS,
  rangoActual,
  marcas,
}: {
  /** Marca global del dashboard (switch de la barra superior): acota la consulta. */
  marcaActual?: string;
  /** Rango global del dashboard: el periodo listado. */
  rangoActual?: string;
  /** Catálogo {id, nombre} para resolver el id crudo de marca de cada pieza. */
  marcas: MarcaDisponible[];
}) {
  const marca_ = marcaParam(marcaActual);
  const [busqueda, setBusqueda] = React.useState("");
  const [redFiltro, setRedFiltro] = React.useState(TODAS);
  const [lineaFiltro, setLineaFiltro] = React.useState(TODAS);
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

  // Opciones de los filtros, derivadas del listado completo.
  const marcasDisponibles = React.useMemo(
    () => Array.from(new Set(piezas.map((p) => p.cuenta).filter(Boolean) as string[])).sort(),
    [piezas],
  );
  // El filtro de Red ofrece SIEMPRE las redes canónicas en orden (no solo las
  // presentes en los datos): así una red sin piezas se puede seleccionar igualmente
  // (la tabla mostrará entonces su estado vacío). Mismo universo que el resto de vistas.
  const redesDisponibles = REDES_CANONICAS;
  const lineasDisponibles = React.useMemo(() => {
    const set = new Set<string>();
    for (const p of piezas) set.add(p.linea || SIN_LINEA);
    return Array.from(set).sort((a, b) =>
      a === SIN_LINEA ? 1 : b === SIN_LINEA ? -1 : a.localeCompare(b, "es-MX"),
    );
  }, [piezas]);

  // Filtro combinado: línea + red + título. La marca la acota el switch global (la
  // consulta ya viene scopeada); aquí solo se filtra dentro de lo recibido.
  const filtradas = React.useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return piezas.filter((p) => {
      // La plataforma se normaliza a su forma canónica (twitter→x) antes de comparar.
      if (redFiltro !== TODAS && redCanonica(p.plataforma) !== redFiltro) return false;
      if (lineaFiltro !== TODAS && (p.linea || SIN_LINEA) !== lineaFiltro) return false;
      if (q && !(p.titulo || "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [piezas, redFiltro, lineaFiltro, busqueda]);

  // Estadísticas del conjunto FILTRADO (reflejan los filtros activos). El engagement
  // agregado es POOLED (interacciones ÷ vistas del conjunto), no la media de porcentajes:
  // pondera cada pieza por sus vistas reales.
  const stats = React.useMemo(() => {
    const vistas = filtradas.map((p) => p.visualizaciones);
    const eng = filtradas.map((p) => p.engagement_pct);
    const sumVistas = vistas.reduce((a, b) => a + b, 0);
    const sumInteracciones = filtradas.reduce((a, p) => a + p.interacciones, 0);
    return {
      total: filtradas.length,
      vistasMedia: media(vistas),
      vistasMediana: mediana(vistas),
      engPooled: sumVistas > 0 ? (sumInteracciones / sumVistas) * 100 : null,
      engMediana: mediana(eng),
    };
  }, [filtradas]);

  // Orden sobre TODO el conjunto filtrado (el día es solo una columna ordenable más).
  // Por defecto Vistas desc → la página 1 es el top del rango (top 20 del mes).
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<PiezaListado, ClaveOrden>(
    filtradas,
    ACCESORES,
    { clave: "visualizaciones", direccion: "desc" },
  );

  // Vista compacta: 5 piezas de ejemplo (el "top 5" del orden activo). "Mostrar más"
  // despliega el listado COMPLETO pero PAGINADO (páginas de 20 con pager), sin scroll infinito.
  const [expandido, setExpandido] = React.useState(false);
  const [paginaIdx, setPaginaIdx] = React.useState(0);
  React.useEffect(() => {
    setPaginaIdx(0);
  }, [filasOrdenadas]);
  const totalPaginas = Math.max(1, Math.ceil(filasOrdenadas.length / POR_PAGINA));
  const paginaActual = Math.min(paginaIdx, totalPaginas - 1);
  const desde = paginaActual * POR_PAGINA;
  const filasMostradas = expandido
    ? filasOrdenadas.slice(desde, desde + POR_PAGINA)
    : filasOrdenadas.slice(0, PREVIEW);
  const hayMas = filasOrdenadas.length > PREVIEW;

  function abrir(pieza: PiezaListado) {
    setSeleccion(pieza);
    setDetalleAbierto(true);
  }

  const variasMarcas = marcasDisponibles.length > 1;

  return (
    <>
      <SeccionColapsable
        titulo="Piezas del periodo"
        icono={ListChecks}
        descripcion="Todas las piezas del periodo. Filtra, ordena y toca para ver detalles."
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
              etiqueta="Vistas: promedio · mediana"
              valor={`${stats.vistasMedia == null ? "—" : numeroCompacto(stats.vistasMedia)} · ${
                stats.vistasMediana == null ? "—" : numeroCompacto(stats.vistasMediana)
              }`}
            />
            <TarjetaKpi
              etiqueta="Engagement (agregado)"
              valor={stats.engPooled == null ? "—" : porcentaje(stats.engPooled)}
              titulo="Total de interacciones dividido por total de vistas del filtro actual"
            />
            <TarjetaKpi
              etiqueta="Engagement (mediana por pieza)"
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
        ) : filasOrdenadas.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Ninguna pieza coincide con los filtros.
          </p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pieza</TableHead>
                  <CabeceraOrdenable
                    activa={estado.clave === "publicado"}
                    direccion={estado.direccion}
                    onClick={() => alClicar("publicado")}
                    alinear="right"
                    className="text-right"
                  >
                    Día
                  </CabeceraOrdenable>
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
                    Engagement
                  </CabeceraOrdenable>
                  {COLS_INTERACCION.map(({ clave, etiqueta, icono: Icono }) => (
                    <CabeceraOrdenable
                      key={clave}
                      activa={estado.clave === clave}
                      direccion={estado.direccion}
                      onClick={() => alClicar(clave)}
                      alinear="right"
                      className="hidden text-right sm:table-cell"
                    >
                      <span className="inline-flex items-center" title={etiqueta}>
                        <Icono className="h-3.5 w-3.5" aria-hidden="true" />
                        <span className="sr-only">{etiqueta}</span>
                      </span>
                    </CabeceraOrdenable>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filasMostradas.map((p) => (
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
            {hayMas && (
              <div className="flex items-center justify-between gap-3 px-6 py-3">
                {expandido ? (
                  <p className="text-xs text-muted-foreground tabular-nums">
                    Página {paginaActual + 1} de {totalPaginas}
                  </p>
                ) : (
                  <span />
                )}
                <div className="flex items-center gap-1">
                  {expandido && (
                    <>
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => setPaginaIdx((i) => Math.max(0, i - 1))}
                        disabled={paginaActual <= 0}
                        aria-label="Página anterior"
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => setPaginaIdx((i) => Math.min(totalPaginas - 1, i + 1))}
                        disabled={paginaActual >= totalPaginas - 1}
                        aria-label="Página siguiente"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="font-normal text-muted-foreground hover:text-foreground"
                    aria-expanded={expandido}
                    onClick={() => {
                      setExpandido((v) => !v);
                      setPaginaIdx(0);
                    }}
                  >
                    {expandido ? "Mostrar menos" : "Mostrar más"}
                  </Button>
                </div>
              </div>
            )}
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

  // Accesibilidad: el control real (focusable, accionable con teclado) es el BOTÓN del
  // título; el onClick de la fila se conserva solo como atajo de ratón. El enlace externo
  // ya no queda anidado dentro de un control con role="button".
  return (
    <TableRow onClick={onAbrir} className="cursor-pointer">
      <TableCell className="max-w-[20rem]">
        <button
          type="button"
          onClick={onAbrir}
          className="block max-w-full truncate text-left font-medium underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
          title={titulo}
        >
          {titulo}
        </button>
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{partes.join(" · ")}</span>
          {pieza.url ? (
            <a
              href={pieza.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center underline-offset-4 hover:underline"
              aria-label="Abrir la pieza en la red"
            >
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          ) : null}
          {pieza.rendimiento_relativo != null && (
            <Badge
              variant={pieza.rendimiento_relativo >= 1 ? "ok" : "error"}
              title="Cómo se compara esta pieza contra el promedio de su red y marca"
            >
              {rendimientoRel(pieza.rendimiento_relativo)}
            </Badge>
          )}
        </span>
      </TableCell>
      <TableCell className="whitespace-nowrap text-right text-xs text-muted-foreground tabular-nums">
        {etiquetaDiaCorto(pieza.publicado)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {numeroCompleto(pieza.visualizaciones)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {porcentaje(pieza.engagement_pct)}
      </TableCell>
      {COLS_INTERACCION.map(({ clave }) => {
        const valor = pieza[clave] as number | null;
        return (
          <TableCell
            key={clave}
            className="hidden text-right tabular-nums sm:table-cell"
            title={valor == null ? undefined : numeroCompleto(valor)}
          >
            {valor == null ? "—" : numeroCompacto(valor)}
          </TableCell>
        );
      })}
    </TableRow>
  );
}
