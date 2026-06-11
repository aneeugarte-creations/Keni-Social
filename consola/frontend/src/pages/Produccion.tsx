import { useQuery } from "@tanstack/react-query";
import { Factory, RefreshCw, SquarePen } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, ApiError, mensajeError } from "@/lib/api";
import { formatearDia } from "@/lib/fecha";
import { costeUsd, duracion, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { INTERVALO_SERIE_MS } from "@/lib/refresco";
import type {
  ActividadPorDia,
  ActividadPorTipo,
  ActividadTotal,
  Pipeline,
  RespuestaPipelines,
} from "@/types";

import { ESTADOS_FILTRO, ETAPAS_FILTRO, FilaPipeline } from "./Pipelines";

// Tamaño de página del botón «Cargar más» (se pide `limite = páginas * PAGINA`, offset 0).
const PAGINA = 20;

/** Fila de KPIs con los CONTEOS del periodo disponible (toda la actividad de IA:
 *  generaciones del pipeline, manuales, runs de agente). */
function KpisTotales({ total }: { total: ActividadTotal }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <TarjetaKpi variante="card" etiqueta="Trabajos IA" valor={numeroCompleto(total.items)} />
      <TarjetaKpi variante="card" etiqueta="Coste total" valor={costeUsd(total.coste_usd)} />
      <TarjetaKpi
        variante="card"
        etiqueta="Tokens"
        valor={numeroCompacto(total.tokens)}
        titulo={numeroCompleto(total.tokens)}
      />
      <TarjetaKpi
        variante="card"
        etiqueta="Tiempo de cómputo"
        valor={total.duration_ms ? duracion(total.duration_ms) : "—"}
      />
    </div>
  );
}

/** Mini-tabla de desglose por tipo de trabajo. */
function DesglosePorTipo({ filas }: { filas: ActividadPorTipo[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por tipo</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Tipo</TableHead>
              <TableHead className="text-right">Items</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Sin actividad por tipo.
                </TableCell>
              </TableRow>
            ) : (
              filas.map((f) => (
                <TableRow key={f.tipo}>
                  <TableCell className="pl-6 font-medium">
                    {f.tipo ? etiquetaTipoGeneracion(f.tipo) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.items)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(f.tokens)}>
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
function DesglosePorDia({ filas }: { filas: ActividadPorDia[] }) {
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
              <TableHead className="text-right">Items</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordenadas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                  Sin actividad por día.
                </TableCell>
              </TableRow>
            ) : (
              ordenadas.map((f) => (
                <TableRow key={f.dia}>
                  <TableCell className="pl-6 font-medium">{formatearDia(f.dia)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.items)}
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

/**
 * Página PRODUCCIÓN (antes «Actividad IA», con pestañas Feed/Pipelines hoy FUSIONADAS):
 * todo lo que la máquina produce, en una sola línea temporal.
 *
 * Arriba, los CONTEOS del periodo (trabajos, coste, tokens, tiempo de cómputo) y los
 * desgloses por tipo/día (`GET /api/actividad/agregados`). Debajo, el feed unificado
 * (`GET /api/pipelines`): las runs del pipeline (tarjeta con su tira de etapas) y la
 * actividad suelta (generación manual/lote, run de agente) como tarjeta de UNA etapa con
 * el nombre de su trabajo — mismo aspecto, mismas métricas (tokens · coste · duración),
 * mismo detalle entrada/salida al abrirla.
 */
export default function Produccion() {
  const navigate = useNavigate();
  // La marca la MANDA el switch global de la barra superior (workspace); Producción no
  // tiene selector propio. `marcaActiva` es el id canónico (o null = "Todas", solo admin).
  const { marcaActiva } = useMarcaActiva();
  const marcaParam = marcaActiva ?? undefined;
  // Filtros del feed (etapa donde está parada la run / estado global / tipo de trabajo).
  const [etapa, setEtapa] = React.useState("");
  const [estado, setEstado] = React.useState("");
  const [tipo, setTipo] = React.useState("");
  const [paginas, setPaginas] = React.useState(1);
  // Al cambiar un filtro (o la marca activa), volvemos a la 1ª página.
  React.useEffect(() => {
    setPaginas(1);
  }, [etapa, estado, tipo, marcaActiva]);

  const listaQuery = useQuery({
    queryKey: ["pipelines", "lista", marcaParam ?? "todas", etapa, estado, tipo, paginas],
    queryFn: ({ signal }) =>
      api.pipelines(
        { marca: marcaParam, etapa, estado, tipo, limite: paginas * PAGINA },
        signal,
      ),
    refetchInterval: INTERVALO_SERIE_MS,
    placeholderData: (prev) => prev, // no parpadea al «Cargar más» ni al cambiar de filtro
  });
  const agregadosQuery = useQuery({
    queryKey: ["actividad", "agregados", marcaParam ?? "todas"],
    queryFn: ({ signal }) => api.actividadAgregados({ marca: marcaParam }, signal),
  });

  const datos = listaQuery.data as RespuestaPipelines | undefined;
  const items = datos?.pipelines ?? [];
  const total = datos?.paginacion?.total ?? items.length;
  const hayFiltro = !!(etapa || estado || tipo);

  // Catálogo de tipos para el filtro: de los agregados (visión global, no solo lo cargado).
  const tipos = React.useMemo(
    () =>
      (agregadosQuery.data?.por_tipo ?? [])
        .map((t) => t.tipo)
        .filter((t) => t && t !== "pipeline") // el trabajo del pipeline ya se ve como runs
        .sort((a, b) => a.localeCompare(b, "es-MX")),
    [agregadosQuery.data],
  );

  function refrescar() {
    void listaQuery.refetch();
    void agregadosQuery.refetch();
  }

  // Cada item abre su detalle: una run, su página estilo GitLab; un trabajo suelto, la
  // página de entrada/salida de su generación. Los runs de agente no tienen detalle propio.
  const abrir = React.useCallback(
    (item: Pipeline) => {
      if (item.clase === "actividad") {
        if (item.origen === "generacion") {
          navigate(`/datos/produccion/actividad/${encodeURIComponent(item.id)}`);
        }
        return;
      }
      navigate(`/datos/produccion/pipelines/${encodeURIComponent(item.id)}`);
    },
    [navigate],
  );

  const cargandoTodo = listaQuery.isPending || agregadosQuery.isPending;

  return (
    <div className="space-y-6">
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu
            icono={RefreshCw}
            onClick={refrescar}
            disabled={listaQuery.isFetching || agregadosQuery.isFetching}
          >
            Actualizar
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* Conteos arriba: totales del periodo + desgloses. */}
      {agregadosQuery.isPending ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : agregadosQuery.isError ? (
        <BloqueError
          titulo="No se pudieron cargar los totales"
          mensaje={mensajeError(agregadosQuery.error)}
          onReintentar={refrescar}
          cargando={agregadosQuery.isFetching}
        />
      ) : (
        <>
          <KpisTotales total={agregadosQuery.data.total} />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <DesglosePorTipo filas={agregadosQuery.data.por_tipo} />
            <DesglosePorDia filas={agregadosQuery.data.por_dia} />
          </div>
        </>
      )}

      {/* Filtros del feed: etapa (runs), estado (todo), tipo (trabajos sueltos). */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={etapa || "todas"} onValueChange={(v) => setEtapa(v === "todas" ? "" : v)}>
          <SelectTrigger className="h-9 w-full sm:w-[190px]" aria-label="Filtrar por etapa">
            <SelectValue placeholder="Etapa" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas las etapas</SelectItem>
            {ETAPAS_FILTRO.map((e) => (
              <SelectItem key={e.clave} value={e.clave}>{e.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={estado || "todos"} onValueChange={(v) => setEstado(v === "todos" ? "" : v)}>
          <SelectTrigger className="h-9 w-full sm:w-[160px]" aria-label="Filtrar por estado">
            <SelectValue placeholder="Estado" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Cualquier estado</SelectItem>
            {ESTADOS_FILTRO.map((e) => (
              <SelectItem key={e.clave} value={e.clave}>{e.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={tipo || "todos"} onValueChange={(v) => setTipo(v === "todos" ? "" : v)}>
          <SelectTrigger className="h-9 w-full sm:w-[190px]" aria-label="Filtrar por tipo">
            <SelectValue placeholder="Tipo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Todos los tipos</SelectItem>
            {tipos.map((t) => (
              <SelectItem key={t} value={t}>{etiquetaTipoGeneracion(t)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hayFiltro && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setEtapa("");
              setEstado("");
              setTipo("");
            }}
          >
            Limpiar
          </Button>
        )}
        {!listaQuery.isPending && (
          <span className="ml-auto text-xs text-muted-foreground">
            {numeroCompleto(total)} {total === 1 ? "item" : "items"}
            {hayFiltro ? " (filtrado)" : ""}
          </span>
        )}
      </div>

      {/* Enlace cruzado proceso → Biblioteca (ADR 0011 F2): las etapas con IA del proceso
          (Copy, Arte) se editan en la Biblioteca de Prompts; deep-link con el doc abierto. */}
      <p className="-mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <SquarePen className="h-3 w-3" aria-hidden />
        Prompts del proceso en la Biblioteca:
        <Link
          to="/contenido/texto/documentos?doc=prompt%2Fcopy"
          className="underline-offset-2 hover:text-foreground hover:underline"
          title="Editar el prompt de Copy en la Biblioteca"
        >
          Copy
        </Link>
        ·
        <Link
          to="/contenido/texto/documentos?doc=prompt%2Farte"
          className="underline-offset-2 hover:text-foreground hover:underline"
          title="Editar el prompt de Arte en la Biblioteca"
        >
          Arte
        </Link>
      </p>

      {/* Feed unificado: runs del pipeline + actividad suelta, recientes primero. */}
      {cargandoTodo && listaQuery.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : listaQuery.isError ? (
        <BloqueError
          titulo="No se pudo cargar la producción"
          mensaje={
            listaQuery.error instanceof ApiError
              ? listaQuery.error.message
              : "Inténtalo de nuevo."
          }
          onReintentar={() => listaQuery.refetch()}
          cargando={listaQuery.isFetching}
        />
      ) : items.length === 0 ? (
        <EstadoVacio
          icono={Factory}
          titulo={hayFiltro ? "Sin items con ese filtro" : "Aún no hay producción"}
          texto={
            hayFiltro
              ? "No hay items con ese filtro"
              : "Los trabajos aparecerán aquí cuando la máquina produzca"
          }
        />
      ) : (
        <>
          <div className="space-y-3">
            {items.map((item) => (
              <FilaPipeline
                key={`${item.clase ?? "run"}-${item.id}`}
                run={item}
                onAbrir={
                  item.clase === "actividad" && item.origen !== "generacion" ? null : abrir
                }
              />
            ))}
          </div>
          {items.length < total && (
            <div className="flex justify-center pt-1">
              <Button
                variant="outline"
                onClick={() => setPaginas((p) => p + 1)}
                disabled={listaQuery.isFetching}
              >
                {listaQuery.isFetching
                  ? "Cargando…"
                  : `Cargar más (${items.length} de ${total})`}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
