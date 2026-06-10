import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronRight, GitBranch, OctagonAlert, RefreshCw, Sparkles } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { aspectoEstado, ChipEstado } from "@/components/comunes/ChipEstado";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Markdown } from "@/components/ui/Markdown";
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
import { tiempoRelativo } from "@/lib/fecha";
import { INTERVALO_SERIE_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import type {
  Pipeline,
  PipelineActividad,
  PipelineCluster,
  PipelineEtapa,
  PipelineGeneracion,
  PipelineHallazgo,
  PipelineQaFuente,
  RespuestaPipelines,
} from "@/types";

// Verificación por corroboración (Ola D) -> etiqueta corta para los chips de procedencia IA.
const VERIFICACION_TEXTO: Record<string, string> = {
  corroborada: "corroborada",
  unica_fuente: "1 sola fuente",
  dudosa: "dudosa",
};

// El aspecto de los estados (badge + etiqueta) vive CONSOLIDADO en el chip único de la
// consola (`components/comunes/ChipEstado`): misma etiqueta y color que Actividad/Monitor.
export { ChipEstado };

// Etapa (clave) -> código de etapa de los eventos de actividad (la traza CI/CD/QA).
export const ETAPA_A_EVENTO: Record<string, string> = {
  fusion: "FUSION", editorial: "EDITORIAL", ci: "CI", qa: "QA", cd: "CD", arte: "ARTE",
};

// Catálogo de etapas para el filtro `?etapa=` (espeja `_ETAPAS` del back, en orden de flujo).
const ETAPAS_FILTRO: { clave: string; nombre: string }[] = [
  { clave: "fusion", nombre: "Fusión" },
  { clave: "editorial", nombre: "Editorial" },
  { clave: "ci", nombre: "Selección" },
  { clave: "qa", nombre: "Validación" },
  { clave: "cd", nombre: "Copy" },
  { clave: "arte", nombre: "Arte" },
  { clave: "aprobacion", nombre: "Aprobación" },
];
// Valores del filtro `?estado=` (el `estado_global` de la run). Nombres = los del chip
// único (`aspectoEstado`): el filtro y el badge dicen lo mismo.
const ESTADOS_FILTRO: { clave: string; nombre: string }[] = [
  { clave: "pendiente", nombre: "Pendiente" },
  { clave: "en_curso", nombre: "En curso" },
  { clave: "revisar", nombre: "Revisar" },
  { clave: "fallo", nombre: "Error" },
  { clave: "ok", nombre: "Completado" },
];
// Tamaño de página del botón «Cargar más» (se pide `limite = páginas * PAGINA`, offset 0).
const PAGINA = 20;

/** Chip de la criba de la fuente (rediseño QPC): ⚠️ "No verificado" o ❗ "QA: problema".
 *  Nada si aún no hay veredicto (criba pendiente/en curso: lo cubre la tira de etapas). */
function BadgeQaFuente({ qa, className }: { qa?: PipelineQaFuente; className?: string }) {
  if (!qa) return null;
  if (qa.problema) {
    return (
      <Badge
        variant="secondary"
        className={cn("gap-1 border border-destructive/30 bg-destructive/10 text-destructive", className)}
        title={qa.resumen || "La criba encontró un problema de peso; no se generó copy."}
      >
        <OctagonAlert className="h-3 w-3" aria-hidden="true" />
        Problema
      </Badge>
    );
  }
  if (qa.no_verificado) {
    return (
      <Badge
        variant="secondary"
        className={cn("gap-1 border border-amber-500/30 bg-amber-500/15 text-amber-600", className)}
        title="Fuente apta pero NO verificada a fondo: revisa antes de aprobar."
      >
        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
        No verificado
      </Badge>
    );
  }
  return null;
}

/** Lista de hallazgos de la criba (lo que está mal en la nota de origen). Nada si vacía. */
function ListaHallazgos({ hallazgos }: { hallazgos: PipelineHallazgo[] }) {
  if (!hallazgos || hallazgos.length === 0) return null;
  return (
    <ul className="space-y-1.5">
      {hallazgos.map((h, i) => (
        <li key={i} className="rounded border border-destructive/20 bg-destructive/5 p-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            {h.tipo && <Badge variant="outline" className="text-[10px]">{h.tipo}</Badge>}
            {h.gravedad && (
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px]",
                  h.gravedad === "error" && "border-destructive/40 text-destructive",
                )}
              >
                {h.gravedad}
              </Badge>
            )}
          </div>
          {h.fragmento && <p className="mt-1 italic text-muted-foreground">«{h.fragmento}»</p>}
          {h.explicacion && <p className="mt-1 text-foreground/90">{h.explicacion}</p>}
          {h.sugerencia && <p className="mt-1 text-muted-foreground">Sugerencia: {h.sugerencia}</p>}
        </li>
      ))}
    </ul>
  );
}

/** Chips de las señales del cluster. `modo` decide cuáles: "fusion" (dedup: fuentes/notas) o
 *  "editorial" (score/verificación/viralidad). */
function ProcedenciaIA({ cluster, modo }: { cluster: PipelineCluster; modo: "fusion" | "editorial" }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {modo === "fusion" && (
        <>
          <Badge variant="outline" className="text-[10px]">{cluster.n_fuentes} fuentes</Badge>
          {cluster.n_items > 1 && (
            <Badge variant="outline" className="text-[10px]">{cluster.n_items} notas</Badge>
          )}
        </>
      )}
      {modo === "editorial" && (
        <>
          <Badge variant="outline" className="text-[10px]">Score {cluster.score.toFixed(2)}</Badge>
          {cluster.verificacion && (
            <Badge variant="outline" className="text-[10px]">
              {VERIFICACION_TEXTO[cluster.verificacion] ?? cluster.verificacion}
            </Badge>
          )}
          {cluster.breaking && (
            <Badge variant="secondary" className="border border-amber-500/30 bg-amber-500/15 text-[10px] text-amber-600">
              🔥 breaking
            </Badge>
          )}
          {cluster.senal > 0 && (
            <Badge variant="outline" className="text-[10px]">viralidad {cluster.senal.toLocaleString("es-MX")}</Badge>
          )}
        </>
      )}
    </div>
  );
}

function Punto({ estado }: { estado: string }) {
  return (
    <span
      className={cn(
        "h-2 w-2 shrink-0 rounded-full",
        estado === "ok" && "bg-emerald-500",
        estado === "en_curso" && "bg-sky-500 animate-pulse",
        estado === "revisar" && "bg-amber-500",
        estado === "pendiente" && "bg-muted-foreground/40",
        estado === "saltada" && "bg-muted-foreground/20 ring-1 ring-muted-foreground/30",
        estado === "fallo" && "bg-destructive",
      )}
    />
  );
}

/** Tira horizontal de etapas (CI · CD · QA · Aprobación), estilo pipeline de GitLab. */
export function TiraEtapas({ etapas }: { etapas: PipelineEtapa[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {etapas.map((e, i) => (
        <React.Fragment key={e.clave}>
          <div
            className={cn(
              "flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
              aspectoEstado(e.estado).clase || "text-muted-foreground",
            )}
            title={e.detalle}
          >
            <Punto estado={e.estado} />
            <span className="font-medium">{e.nombre}</span>
          </div>
          {i < etapas.length - 1 && <span className="text-muted-foreground/40">→</span>}
        </React.Fragment>
      ))}
    </div>
  );
}

/** Tarjeta de una run: TODA la tarjeta es clicable (abre el detalle). */
function FilaPipeline({ run, onAbrir }: { run: Pipeline; onAbrir: (id: string) => void }) {
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onAbrir(run.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onAbrir(run.id);
        }
      }}
      className="cursor-pointer transition-colors hover:bg-muted/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <CardContent className="flex items-center gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="shrink-0">{run.marca_nombre || run.marca}</Badge>
            <ChipEstado estado={run.estado_global} />
            <BadgeQaFuente qa={run.qa_fuente} />
            {run.cluster && (
              <Badge
                variant="outline"
                className="shrink-0 gap-1 text-[10px]"
                title={`Historia jerarquizada por IA: ${run.cluster.n_fuentes} fuente(s), score ${run.cluster.score.toFixed(2)}`}
              >
                <Sparkles className="h-3 w-3" aria-hidden="true" />
                {run.cluster.n_fuentes} fuente(s)
              </Badge>
            )}
            <span className="truncate text-xs text-muted-foreground">{tiempoRelativo(run.creado)}</span>
          </div>
          <p className="truncate text-sm font-medium" title={run.titulo}>{run.titulo}</p>
          <TiraEtapas etapas={run.etapas} />
        </div>
        <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      </CardContent>
    </Card>
  );
}

function EventosEtapa({ eventos }: { eventos: PipelineActividad[] }) {
  if (eventos.length === 0) return null;
  return (
    <ul className="space-y-1">
      {eventos.map((ev, i) => (
        <li key={i} className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <span className="truncate" title={ev.etiqueta}>{ev.etiqueta}</span>
          <span className="shrink-0">{tiempoRelativo(ev.fecha)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Bloque de TRANSPARENCIA de una etapa IA: el PROMPT de entrada (real si corrió; plantilla si
 *  no), el RAZONAMIENTO (proceso de pensamiento, stream del agente) y el RESULTADO. Se enseña
 *  SIEMPRE en etapas IA, aunque aún no se haya ejecutado (entonces el prompt es la plantilla y el
 *  proceso/resultado quedan "pendiente"). `gen` es la generación real (si existe). */
function BloqueIA({ gen, plantilla }: { gen?: PipelineGeneracion; plantilla?: string }) {
  const enCurso = gen?.estado === "ejecutando";
  const salida = (gen?.salida ?? "").trim();
  const prompt = (gen?.prompt || plantilla || "").trim();
  const esPlantilla = !gen?.prompt && !!plantilla;
  return (
    <div className="space-y-2 rounded-md border border-violet-500/20 bg-violet-500/5 p-2.5">
      <div className="flex items-center gap-2">
        <Sparkles className="h-3 w-3 text-violet-600" aria-hidden="true" />
        <span className="text-xs font-semibold text-foreground">IA</span>
        {gen
          ? <ChipEstado estado={enCurso ? "en_curso" : gen.estado === "error" ? "fallo" : "ok"} />
          : <span className="text-[11px] text-muted-foreground">aún no ejecutado</span>}
      </div>
      {/* ENTRADA (prompt) ↔ SALIDA (razonamiento + resultado), lado a lado en pantallas anchas
          (la página dedicada) y apilados en estrecho (el feed móvil). */}
      <div className="grid gap-2 lg:grid-cols-2">
        <div className="min-w-0 space-y-1">
          <div className="text-[11px] font-medium text-muted-foreground">
            Entrada · prompt{esPlantilla ? " (plantilla)" : ""}
          </div>
          {prompt ? (
            <div className="max-h-72 overflow-y-auto rounded bg-background/60 p-2">
              <Markdown className="text-xs text-foreground/80">{prompt}</Markdown>
            </div>
          ) : <p className="text-[11px] italic text-muted-foreground">Prompt no disponible.</p>}
        </div>
        <div className="min-w-0 space-y-1">
          <div className="text-[11px] font-medium text-muted-foreground">Salida · razonamiento + resultado</div>
          {salida ? (
            <div className="max-h-72 overflow-y-auto rounded bg-background/60 p-2">
              <Markdown className="text-xs text-foreground/90">{salida}</Markdown>
            </div>
          ) : (
            <p className="text-xs italic text-muted-foreground">
              {enCurso ? "En curso…" : "Pendiente: esta etapa aún no se ha ejecutado."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** Contenido COMPLETO específico de cada etapa. Las etapas IA enseñan SIEMPRE el BloqueIA
 *  (prompt + razonamiento + resultado); las no-IA muestran su dato propio. */
function ContenidoEtapa({
  clave,
  run,
  generacion,
  plantilla,
}: {
  clave: string;
  run: Pipeline;
  generacion?: PipelineGeneracion;
  plantilla?: string;
}) {
  if (clave === "fusion" || clave === "editorial") {
    return (
      <div className="space-y-2 text-xs">
        {run.cluster
          ? <ProcedenciaIA cluster={run.cluster} modo={clave} />
          : <p className="text-muted-foreground">Sin historia.</p>}
        <BloqueIA gen={generacion} plantilla={plantilla} />
      </div>
    );
  }
  if (clave === "ci") {
    // Selección: crea el tema en BD (no es IA). Solo la nota de origen.
    return run.descripcion
      ? <Markdown className="text-xs text-muted-foreground">{run.descripcion}</Markdown>
      : null;
  }
  if (clave === "cd") {
    return (
      <div className="space-y-3">
        <BloqueIA gen={generacion} plantilla={plantilla} />
        {run.piezas.map((p, i) => (
          <div key={`${p.red}-${i}`} className="rounded-md border p-2">
            <div className="mb-1 flex items-center gap-2">
              <span className="text-xs font-semibold">{p.red_nombre}</span>
              {p.copy_in && <Badge variant="outline" className="text-[10px]">placa: {p.copy_in}</Badge>}
            </div>
            {p.copy
              ? <Markdown className="text-xs text-foreground/90">{p.copy}</Markdown>
              : <p className="text-xs italic text-muted-foreground">Sin copy.</p>}
          </div>
        ))}
      </div>
    );
  }
  if (clave === "arte") {
    const imagenes = run.piezas.filter((p) => p.imagen_url);
    return (
      <div className="space-y-2">
        <BloqueIA gen={generacion} plantilla={plantilla} />
        {imagenes.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {imagenes.map((p, i) => (
              <img key={`${p.red}-${i}`} src={p.imagen_url} alt={p.red_nombre} loading="lazy"
                className="h-24 w-24 rounded border object-cover" />
            ))}
          </div>
        )}
      </div>
    );
  }
  if (clave === "qa") {
    const qa = run.qa_fuente;
    return (
      <div className="space-y-2">
        <BloqueIA gen={generacion} plantilla={plantilla} />
        {qa && (qa.no_verificado || qa.problema) && (
          <div className="space-y-2 rounded-md border p-2">
            <BadgeQaFuente qa={qa} />
            {qa.resumen && <p className="text-xs text-foreground/90">{qa.resumen}</p>}
            <ListaHallazgos hallazgos={qa.hallazgos} />
          </div>
        )}
      </div>
    );
  }
  // aprobacion — gate HUMANO (no IA).
  return (
    <div className="space-y-1.5">
      {run.piezas.map((p, i) => (
        <div key={`${p.red}-${i}`} className="flex items-center justify-between gap-2 rounded-md border p-2 text-xs">
          <span className="font-semibold">{p.red_nombre}</span>
          <div className="flex flex-col items-end gap-0.5 text-muted-foreground">
            <Badge variant="outline">{p.estado}</Badge>
            {p.revisor_nombre && <span>{p.revisor_nombre} · {tiempoRelativo(p.revisado_en || "")}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Panel INDEPENDIENTE y plegable de una etapa: cabecera siempre visible (nombre + estado)
 *  y, al desplegar, el detalle COMPLETO de lo ocurrido en ese paso. Cada panel se abre/cierra
 *  por su cuenta (estado local propio). */
export function PanelEtapa({
  etapa,
  run,
  eventos,
  generacion,
  plantilla,
  defaultOpen,
}: {
  etapa: PipelineEtapa;
  run: Pipeline;
  eventos: PipelineActividad[];
  generacion?: PipelineGeneracion;
  plantilla?: string;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="rounded-lg border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-left hover:bg-muted/40"
      >
        <span className="flex items-center gap-2">
          <Punto estado={etapa.estado} />
          <span className="text-sm font-semibold">{etapa.nombre}</span>
          {/* Marca clara IA vs no-IA (Selección = Sistema/BD; Aprobación = Humano). */}
          {etapa.es_ia ? (
            <Badge variant="outline" className="gap-1 border-violet-500/30 text-[10px] text-violet-600">
              <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />IA
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] text-muted-foreground">
              {etapa.clave === "aprobacion" ? "Humano" : "Sistema"}
            </Badge>
          )}
          <ChipEstado estado={etapa.estado} />
        </span>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div className="space-y-3 border-t p-3">
          {etapa.detalle && <p className="text-xs text-muted-foreground">{etapa.detalle}</p>}
          <EventosEtapa eventos={eventos} />
          <ContenidoEtapa clave={etapa.clave} run={run} generacion={generacion} plantilla={plantilla} />
        </div>
      )}
    </div>
  );
}

/** Vista «Pipelines» del hub Actividad IA (runs del pipeline por contenido, etapa a
 * etapa). Era una página propia; CONSOLIDADA como vista de Actividad (?vista=pipelines):
 * una sola superficie de histórico con dos lentes (Feed / Pipelines). El detalle de una
 * run sigue siendo página aparte (/datos/actividad/pipelines/:id). */
export function VistaPipelines() {
  // Cada run abre su PÁGINA dedicada (estilo GitLab/Azure), no un pop-up.
  const navigate = useNavigate();
  const abrir = React.useCallback(
    (id: string) => navigate(`/datos/actividad/pipelines/${encodeURIComponent(id)}`),
    [navigate],
  );
  // La vista respeta el switch global de marca de la barra superior (no tiene selector
  // propio). `marcaActiva` es el id canónico (o null = "Todas", solo admin) que el back
  // valida; null → sin filtro de marca.
  const { marcaActiva } = useMarcaActiva();
  // Filtros (etapa donde está parada / estado global) y paginación incremental.
  const [etapa, setEtapa] = React.useState("");
  const [estado, setEstado] = React.useState("");
  const [paginas, setPaginas] = React.useState(1);
  // Al cambiar un filtro (o la marca activa), volvemos a la 1ª página.
  React.useEffect(() => { setPaginas(1); }, [etapa, estado, marcaActiva]);

  const q = useQuery({
    queryKey: ["pipelines", "lista", marcaActiva ?? "todas", etapa, estado, paginas],
    queryFn: ({ signal }) =>
      api.pipelines(
        { marca: marcaActiva ?? undefined, etapa, estado, limite: paginas * PAGINA },
        signal,
      ),
    refetchInterval: INTERVALO_SERIE_MS,
    placeholderData: (prev) => prev,  // no parpadea al «Cargar más» ni al cambiar de filtro
  });
  const datos = q.data as RespuestaPipelines | undefined;
  const runs = datos?.pipelines ?? [];
  const total = datos?.paginacion?.total ?? runs.length;
  const hayFiltro = !!(etapa || estado);

  return (
    <div className="space-y-5">
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu icono={RefreshCw} onClick={() => q.refetch()} disabled={q.isFetching}>
            Actualizar
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* Filtros: por la etapa donde está parada la run y por su estado global. */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={etapa || "todas"} onValueChange={(v) => setEtapa(v === "todas" ? "" : v)}>
          <SelectTrigger className="h-9 w-full sm:w-[200px]"><SelectValue placeholder="Etapa" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas las etapas</SelectItem>
            {ETAPAS_FILTRO.map((e) => (
              <SelectItem key={e.clave} value={e.clave}>{e.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={estado || "todos"} onValueChange={(v) => setEstado(v === "todos" ? "" : v)}>
          <SelectTrigger className="h-9 w-full sm:w-[170px]"><SelectValue placeholder="Estado" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Cualquier estado</SelectItem>
            {ESTADOS_FILTRO.map((e) => (
              <SelectItem key={e.clave} value={e.clave}>{e.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hayFiltro && (
          <Button variant="ghost" size="sm" onClick={() => { setEtapa(""); setEstado(""); }}>
            Limpiar
          </Button>
        )}
        {!q.isPending && (
          <span className="ml-auto text-xs text-muted-foreground">
            {total} {total === 1 ? "run" : "runs"}{hayFiltro ? " (filtrado)" : ""}
          </span>
        )}
      </div>

      {q.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
      ) : q.isError ? (
        <BloqueError
          titulo="No se pudieron cargar los pipelines"
          mensaje={q.error instanceof ApiError ? q.error.message : "Inténtalo de nuevo."}
          onReintentar={() => q.refetch()}
          cargando={q.isFetching}
        />
      ) : runs.length === 0 ? (
        <EstadoVacio
          icono={GitBranch}
          titulo={hayFiltro ? "Sin runs con ese filtro" : "Aún no hay pipelines"}
          texto={
            hayFiltro
              ? "Ninguna run coincide con la etapa/estado elegidos. Prueba a quitar el filtro."
              : "Cuando el pipeline automático ingiera temas (RSS/tendencias), cada pieza aparecerá aquí con sus etapas. Actívalo en Ajustes (toggles por etapa)."
          }
        />
      ) : (
        <>
          <div className="space-y-3">
            {runs.map((run) => (
              <FilaPipeline key={run.id} run={run} onAbrir={abrir} />
            ))}
          </div>
          {runs.length < total && (
            <div className="flex justify-center pt-1">
              <Button
                variant="outline"
                onClick={() => setPaginas((p) => p + 1)}
                disabled={q.isFetching}
              >
                {q.isFetching ? "Cargando…" : `Cargar más (${runs.length} de ${total})`}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
