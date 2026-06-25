/**
 * Tabla CONSOLIDADA de piezas del periodo (fusiona Lista + Top/Peores + Rendimiento).
 *
 * UNA sola tabla rica con todo el kit, consistente:
 *   - Filtros (client-side): categoría y buscador por título. El foco de red lo
 *     manda el selector GLOBAL de la cabecera; la marca, el switch global.
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
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Seccion } from "./Seccion";
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
  formatoEnFoco,
  nombreFormato,
  nombreMarca,
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
  redEnFoco,
  rendimientoRel,
} from "@/lib/formato";
import type { MarcaDisponible, PiezaListado } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { idsColumnas, metaColumnas, TABLA_PIEZAS } from "./columnasMeta";
import { MARCA_TODAS } from "./Controles";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";
import { DetallePieza } from "./DetallePieza";
import { NOTA_VISTAS_CROSSRED } from "./metricas-meta";
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

/** Columnas de interacción (icono + número) indexadas por id, para render por columna. */
const META_INTERACCION = new Map(COLS_INTERACCION.map((c) => [c.clave as string, c]));

const IDS_PIEZAS_BASE = idsColumnas(TABLA_PIEZAS);

const TODAS = "__todas__";
const SIN_LINEA = "Sin categoría";

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
  const redGlobal = useVistaConfig((s) => s.red);
  const formato = useVistaConfig((s) => s.formato);
  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA_PIEZAS]);
  const cfgCols = cfgGuardada ?? { orden: IDS_PIEZAS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_PIEZAS_BASE, cfgCols);
  const [busqueda, setBusqueda] = React.useState("");
  const [lineaFiltro, setLineaFiltro] = React.useState(TODAS);
  const [seleccion, setSeleccion] = React.useState<PiezaListado | null>(null);
  const [detalleAbierto, setDetalleAbierto] = React.useState(false);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-listado", rangoActual ?? "", marca_ ?? "todas", redGlobal ?? "todas", formato ?? "todos"],
    queryFn: ({ signal }) =>
      api.metricasPiezasListado({ rango: rangoActual, marca: marca_, red: redGlobal ?? undefined, formato: formato ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const piezas = React.useMemo(() => data?.piezas ?? [], [data]);

  // Opciones de los filtros, derivadas del listado completo.
  const marcasDisponibles = React.useMemo(
    () => Array.from(new Set(piezas.map((p) => p.cuenta).filter(Boolean) as string[])).sort(),
    [piezas],
  );
  const lineasDisponibles = React.useMemo(() => {
    const set = new Set<string>();
    for (const p of piezas) set.add(p.linea || SIN_LINEA);
    return Array.from(set).sort((a, b) =>
      a === SIN_LINEA ? 1 : b === SIN_LINEA ? -1 : a.localeCompare(b, "es-MX"),
    );
  }, [piezas]);

  // Filtro combinado: línea + título. El foco de red lo manda el selector GLOBAL
  // (`redEnFoco`); la marca la acota el switch global (la consulta ya viene scopeada).
  const filtradas = React.useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return piezas.filter((p) => {
      if (!redEnFoco(redGlobal, p.plataforma)) return false;
      if (!formatoEnFoco(formato, p.formato)) return false;
      if (lineaFiltro !== TODAS && (p.linea || SIN_LINEA) !== lineaFiltro) return false;
      if (q && !(p.titulo || "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [piezas, redGlobal, formato, lineaFiltro, busqueda]);

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

  // Cabecera de una columna por su id (orden/visibilidad del panel "Configurar vista").
  // "pieza" no es ordenable; el resto reusa `CabeceraOrdenable`.
  const encabezadoPieza = (id: string) => {
    if (id === "pieza") {
      return <TableHead key={id}>Pieza</TableHead>;
    }
    const inter = META_INTERACCION.get(id);
    if (inter) {
      const Icono = inter.icono;
      return (
        <CabeceraOrdenable
          key={id}
          activa={estado.clave === inter.clave}
          direccion={estado.direccion}
          onClick={() => alClicar(inter.clave)}
          alinear="right"
          className="hidden text-right sm:table-cell"
        >
          <span className="inline-flex items-center" title={inter.etiqueta}>
            <Icono className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="sr-only">{inter.etiqueta}</span>
          </span>
        </CabeceraOrdenable>
      );
    }
    const etiqueta = id === "publicado" ? "Día" : id === "visualizaciones" ? "Vistas" : "Engagement";
    const clave = id as ClaveOrden;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear="right"
        className="text-right"
      >
        {etiqueta}
      </CabeceraOrdenable>
    );
  };

  return (
    <>
      <Seccion
        id="piezas-tabla"
        titulo="Piezas del periodo"
        icono={ListChecks}
        tablaId={TABLA_PIEZAS}
        columnas={metaColumnas(TABLA_PIEZAS)}
      >
        <Card className="overflow-hidden">
        <div className="space-y-3 px-6 pb-3 pt-4">
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
            <SelectTrigger className="w-full sm:w-48" aria-label="Filtrar por categoría">
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

        {/* Estadísticas del conjunto filtrado */}
        {!isPending && !isError && piezas.length > 0 && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <TarjetaKpi etiqueta="Piezas" valor={numeroCompleto(stats.total)} />
            <TarjetaKpi
              etiqueta="Vistas promedio"
              valor={stats.vistasMedia == null ? "—" : numeroCompacto(stats.vistasMedia)}
              titulo={NOTA_VISTAS_CROSSRED}
            />
            <TarjetaKpi
              etiqueta="Vistas mediana"
              valor={stats.vistasMediana == null ? "—" : numeroCompacto(stats.vistasMediana)}
              titulo={NOTA_VISTAS_CROSSRED}
            />
            <TarjetaKpi
              etiqueta="Engagement (agregado)"
              valor={stats.engPooled == null ? "—" : porcentaje(stats.engPooled)}
              titulo="Total de interacciones dividido por total de vistas del filtro actual"
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
        ) : filasOrdenadas.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Ninguna pieza coincide con los filtros.
          </p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>{columnas.map(encabezadoPieza)}</TableRow>
              </TableHeader>
              <TableBody>
                {filasMostradas.map((p) => (
                  <FilaPieza
                    key={p.id}
                    pieza={p}
                    columnas={columnas}
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
        </Card>
      </Seccion>

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
  columnas,
  marcas,
  mostrarMarca,
  onAbrir,
}: {
  pieza: PiezaListado;
  /** Ids de columna en el orden/visibilidad efectivos ("Configurar vista"). */
  columnas: string[];
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

  // Modelo item-first: click izquierdo sobre la fila abre el detalle (primaria); el
  // resto vive en el menú (click derecho · long-press · teclado), incluido "Abrir en la red".
  const acciones: EntradaMenuContextual[] = [];
  const urlPieza = pieza.url;
  if (urlPieza) {
    acciones.push({
      etiqueta: "Abrir en la red",
      icono: ExternalLink,
      onClick: () => window.open(urlPieza, "_blank", "noopener,noreferrer"),
    });
  }

  const celda = (id: string) => {
    if (id === "pieza") {
      return (
        <TableCell key={id} className="max-w-[20rem]">
          <span className="block max-w-full truncate font-medium" title={titulo}>
            {titulo}
          </span>
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span>{partes.join(" · ")}</span>
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
      );
    }
    if (id === "publicado") {
      return (
        <TableCell
          key={id}
          className="whitespace-nowrap text-right text-xs text-muted-foreground tabular-nums"
        >
          {etiquetaDiaCorto(pieza.publicado)}
        </TableCell>
      );
    }
    if (id === "visualizaciones") {
      return (
        <TableCell key={id} className="text-right tabular-nums">
          {numeroCompleto(pieza.visualizaciones)}
        </TableCell>
      );
    }
    if (id === "engagement_pct") {
      return (
        <TableCell key={id} className="text-right tabular-nums">
          {porcentaje(pieza.engagement_pct)}
        </TableCell>
      );
    }
    // Columnas de interacción (comentarios/compartidos/guardados/clics_enlace): se ocultan
    // en móvil (sm:table-cell), como la cabecera.
    const valor = pieza[id as ClaveOrden] as number | null;
    return (
      <TableCell
        key={id}
        className="hidden text-right tabular-nums sm:table-cell"
        title={valor == null ? undefined : numeroCompleto(valor)}
      >
        {valor == null ? "—" : numeroCompacto(valor)}
      </TableCell>
    );
  };

  return (
    <FilaConAcciones
      como="tr"
      onPrimaria={onAbrir}
      acciones={acciones}
      etiquetaAcciones={`Acciones de ${titulo}`}
      kebab="nunca"
    >
      {columnas.map(celda)}
    </FilaConAcciones>
  );
}
