import { useQuery } from "@tanstack/react-query";
import { Factory } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, ApiError } from "@/lib/api";
import { numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { INTERVALO_SERIE_MS } from "@/lib/refresco";
import { TablaBacklog } from "@/pages/maquina/cola-comun";
import type { Pipeline, RespuestaPipelines } from "@/types";

import { ESTADOS_FILTRO, ETAPAS_FILTRO, FilaPipeline } from "./Pipelines";

// Tamaño de página del botón «Cargar más» (se pide `limite = páginas * PAGINA`, offset 0).
const PAGINA = 20;

/**
 * Página PRODUCCIÓN: el FEED de todo lo que la máquina produce, en una sola línea temporal —
 * el drill-down de «qué hizo la máquina».
 *
 * El feed unificado (`GET /api/pipelines`): las runs del pipeline (tarjeta con su tira de
 * etapas) y la actividad suelta (generación manual/lote, run de agente) como tarjeta de UNA
 * etapa con el nombre de su trabajo — mismo aspecto, mismas métricas (tokens · coste ·
 * duración), mismo detalle entrada/salida al abrirla.
 *
 * La ECONOMÍA de tokens (conteos del periodo + desglose por tipo/día) vive en su propia página
 * (`/maquina/economia`); aquí queda solo el feed/traza. El catálogo de tipos del filtro se deriva
 * del propio feed (no hay ya una query aparte de agregados solo para eso).
 *
 * Es la pestaña «Actividad» del hub de la máquina (`/maquina/actividad`): el título lo pinta la
 * tira de pestañas del hub, así que esta página NO porta su propio `<TituloPagina/>`. El feed se
 * auto-refresca (INTERVALO_SERIE_MS); no hay acción manual de recarga.
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

  // Embalse del tablero por marca×etapa: el contexto del flujo que esta página traza (foto
  // completa sin filtro, la misma del Monitor/Cómputo).
  const backlog = useQuery({
    queryKey: ["produccion", "backlog"],
    queryFn: ({ signal }) => api.produccionBacklog(signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });

  const datos = listaQuery.data as RespuestaPipelines | undefined;
  const items = datos?.pipelines ?? [];
  const total = datos?.paginacion?.total ?? items.length;
  const hayFiltro = !!(etapa || estado || tipo);

  // Catálogo de tipos para el filtro: se deriva del PROPIO feed (los trabajos sueltos traen
  // `tipo`), una sola fuente y una petición menos.
  const tipos = React.useMemo(
    () =>
      Array.from(
        new Set(
          (datos?.pipelines ?? [])
            .map((it) => it.tipo)
            .filter((t): t is string => !!t && t !== "pipeline"), // las runs ya se ven como tales
        ),
      ).sort((a, b) => a.localeCompare(b, "es-MX")),
    [datos],
  );

  // Cada item abre su detalle: una run, su página estilo GitLab; un trabajo suelto, la
  // página de entrada/salida de su generación. Los runs de agente no tienen detalle propio.
  const abrir = React.useCallback(
    (item: Pipeline) => {
      if (item.clase === "actividad") {
        if (item.origen === "generacion") {
          navigate(`/maquina/actividad/generacion/${encodeURIComponent(item.id)}`);
        }
        return;
      }
      navigate(`/maquina/actividad/pipelines/${encodeURIComponent(item.id)}`);
    },
    [navigate],
  );

  const cargandoTodo = listaQuery.isPending;

  return (
    <div className="space-y-6">
      {/* El título lo pinta la tira de pestañas del hub (Actividad). La lista se auto-refresca
          (INTERVALO_SERIE_MS), así que no hay acción manual de recarga. */}
      {/* Embalse del tablero: el contexto del flujo que esta traza recorre — qué se acumula ANTES
          de la cola de jobs. Sin filtro de marca (foto completa, como el endpoint). */}
      {backlog.data && <TablaBacklog backlog={backlog.data} />}
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
          texto={!hayFiltro ? "Los trabajos aparecerán aquí cuando la máquina produzca" : undefined}
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
