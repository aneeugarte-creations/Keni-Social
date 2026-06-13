import { useQuery } from "@tanstack/react-query";
import { Coins, Factory, RefreshCw, SquarePen } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
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
import type { Pipeline, RespuestaPipelines } from "@/types";

import { ESTADOS_FILTRO, ETAPAS_FILTRO, FilaPipeline } from "./Pipelines";

// Tamaño de página del botón «Cargar más» (se pide `limite = páginas * PAGINA`, offset 0).
const PAGINA = 20;

/**
 * Página PRODUCCIÓN (antes «Actividad IA», con pestañas Feed/Pipelines hoy FUSIONADAS): el
 * FEED de todo lo que la máquina produce, en una sola línea temporal — el drill-down de «qué
 * hizo la máquina».
 *
 * El feed unificado (`GET /api/pipelines`): las runs del pipeline (tarjeta con su tira de
 * etapas) y la actividad suelta (generación manual/lote, run de agente) como tarjeta de UNA
 * etapa con el nombre de su trabajo — mismo aspecto, mismas métricas (tokens · coste ·
 * duración), mismo detalle entrada/salida al abrirla.
 *
 * La ECONOMÍA de tokens (conteos del periodo + desglose por tipo/día) se MOVIÓ al dashboard de
 * Workers (`/maquina/cola`), donde vive JUNTA con el gasto por proceso y el pool reactivo; aquí
 * queda solo el feed. (El catálogo de tipos del filtro sigue saliendo de los mismos agregados.)
 *
 * `embebido`: cuando el feed se monta DENTRO del dashboard de Workers (sección «Actividad»,
 * `/maquina/cola`), no aporta su propio título/menú de página (los pone Workers) ni el enlace
 * «Economía de tokens → Workers» (sería circular). Como página suelta (default) sí los pinta.
 */
export default function Produccion({ embebido = false }: { embebido?: boolean }) {
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
      {/* Como página suelta porta su título/menú a la cabecera y enlaza a la economía (en Workers).
          Embebido en Workers (sección «Actividad») no los pinta: el título y el menú son de la Cola
          y el enlace a la economía sería circular (la economía vive en la misma página). */}
      {!embebido && (
        <>
          <TituloPagina titulo="Producción" icono={Factory} />
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

          {/* La economía de tokens (conteos + desglose por tipo/día) se unificó en el dashboard de
              Workers, junto al gasto por proceso y el pool. Aquí queda el feed; enlace breve allí. */}
          <Link
            to="/maquina/cola"
            className="flex items-center gap-1.5 text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            <Coins className="h-4 w-4" aria-hidden="true" />
            Economía de tokens → Workers
          </Link>
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
