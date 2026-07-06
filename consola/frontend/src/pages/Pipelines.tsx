import { AlertTriangle, Bot, ChevronDown, ChevronRight, Clock, Coins, Cog, OctagonAlert, ShieldCheck, Sparkles } from "lucide-react";
import * as React from "react";

import { aspectoEstado, ChipEstado } from "@/components/comunes/ChipEstado";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Markdown } from "@/components/ui/Markdown";
import { tiempoRelativo } from "@/lib/fecha";
import { costeUsd, duracion, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { cn } from "@/lib/utils";
import type {
  Pipeline,
  PipelineActividad,
  PipelineCluster,
  PipelineEtapa,
  PipelineGeneracion,
  PipelineHallazgo,
  PipelineMetricas,
  PipelineVerificacionFuente,
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

// Etapa (clave) -> código de etapa de los eventos de actividad (la traza Fusionar/Priorizar/Verificar/Decisor/Redactar/Sugerir hashtags/Ilustrar/Carrusel).
export const ETAPA_A_EVENTO: Record<string, string> = {
  fusionar: "FUSIONAR", priorizar: "PRIORIZAR", admitir: "ADMITIR", verificar: "VERIFICAR", decisor: "DECISOR", redactar: "REDACTAR", sugerir_hashtags: "SUGERIR_HASHTAGS", ilustrar: "ILUSTRAR", carrusel: "CARRUSEL", critica: "CRITICA",
};

// Catálogo de etapas para el filtro `?etapa=` (espeja `_ETAPAS` del back, en orden de flujo).
// «Sugerir hashtags» y «Carrusel» NO entran: el filtro lista runs PARADAS en una etapa, y
// ninguna de las dos bloquea (solo "ok"/"saltada", son trabajo opcional), así que filtrar por
// ellas no daría nada. Decisor SÍ entra: bloquea de verdad el arranque de Redactar mientras
// está pendiente.
export const ETAPAS_FILTRO: { clave: string; nombre: string }[] = [
  { clave: "fusionar", nombre: "Fusionar" },
  { clave: "priorizar", nombre: "Priorizar" },
  { clave: "admitir", nombre: "Admitir" },
  { clave: "verificar", nombre: "Verificar" },
  { clave: "decisor", nombre: "Decisor" },
  { clave: "redactar", nombre: "Redactar" },
  { clave: "ilustrar", nombre: "Ilustrar" },
  { clave: "aprobar", nombre: "Aprobar" },
  { clave: "critica", nombre: "Crítica" },
];
// Valores del filtro `?estado=` (el `estado_global` de la run). Nombres = los del chip
// único (`aspectoEstado`): el filtro y el badge dicen lo mismo.
export const ESTADOS_FILTRO: { clave: string; nombre: string }[] = [
  { clave: "pendiente", nombre: "Pendiente" },
  { clave: "en_curso", nombre: "En curso" },
  { clave: "revisar", nombre: "Revisar" },
  { clave: "fallo", nombre: "Error" },
  { clave: "ok", nombre: "Completado" },
];

/** Chip de la verificación de la fuente: ✅ "Verificada", ⚠️ "Requiere revisión" (la IA no pudo
 *  confirmar) o ❗ "Rechazada". Nada si aún no hay verificacion (la tira de etapas lo cubre). */
function BadgeVerificacionFuente({ verificación, className }: { verificación?: PipelineVerificacionFuente; className?: string }) {
  if (!verificación) return null;
  if (verificación.rechazado) {
    return (
      <Badge
        variant="secondary"
        className={cn("gap-1 border border-destructive/30 bg-destructive/10 text-destructive", className)}
        title={verificación.resumen || "La verificación rechazó la fuente; sin copy."}
      >
        <OctagonAlert className="h-3 w-3" aria-hidden="true" />
        Rechazada
      </Badge>
    );
  }
  if (verificación.requiere_humano) {
    return (
      <Badge
        variant="secondary"
        className={cn("gap-1 border border-amber-500/30 bg-amber-500/15 text-amber-600", className)}
        title={verificación.resumen || "La IA no pudo verificarla; requiere revisión humana."}
      >
        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
        Requiere revisión
      </Badge>
    );
  }
  if (verificación.verificado) {
    return (
      <Badge
        variant="secondary"
        className={cn("gap-1 border border-emerald-500/30 bg-emerald-500/15 text-emerald-600", className)}
        title="Confirmada con fuentes fiables"
      >
        <ShieldCheck className="h-3 w-3" aria-hidden="true" />
        Verificada
      </Badge>
    );
  }
  return null;
}

/** Lista de hallazgos de la verificación (lo que está mal en la nota de origen). Nada si vacía. */
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

/** Chips de las señales del cluster. `modo` decide cuáles: "fusionar" (dedup: fuentes/notas) o
 *  "priorizar" (score/verificación/viralidad). */
function ProcedenciaIA({ cluster, modo }: { cluster: PipelineCluster; modo: "fusionar" | "priorizar" }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {modo === "fusionar" && (
        <>
          <Badge variant="outline" className="text-[10px]">{cluster.n_fuentes} fuentes</Badge>
          {cluster.n_items > 1 && (
            <Badge variant="outline" className="text-[10px]">{cluster.n_items} notas</Badge>
          )}
        </>
      )}
      {modo === "priorizar" && (
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

/** Tira horizontal de etapas, estilo pipeline de GitLab. Los procesos de IA (`es_ia`) son ETAPAS
 *  (cajas 🤖); los de software (Admitir, Aprobar) son FRONTERAS (⚙, línea con etiqueta). Una etapa
 *  que NO corrió («saltada») NO se pinta: conserva su RANURA como un tramo de línea (el conector se
 *  alarga), para que las etapas visibles queden alineadas entre runs (comparativa visual). El
 *  backend devuelve SIEMPRE las mismas etapas en orden, así que cada ranura es la misma columna. */
export function TiraEtapas({ etapas }: { etapas: PipelineEtapa[] }) {
  return (
    <div className="flex items-center gap-1.5">
      {etapas.map((e) =>
        e.estado === "saltada" ? (
          // No corrió: hueco con la línea conectora (mantiene la posición de las demás).
          <span key={e.clave} className="h-px min-w-[14px] flex-1 bg-border" aria-hidden="true" />
        ) : (
          <div key={e.clave} className="flex min-w-0 flex-1 items-center justify-center">
            {e.es_ia ? (
              <div
                className={cn(
                  "flex min-w-0 items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
                  aspectoEstado(e.estado).clase || "text-muted-foreground",
                )}
                title={e.detalle}
              >
                <Punto estado={e.estado} />
                <Bot className="h-3 w-3 shrink-0" aria-label="IA" />
                <span className="truncate font-medium">{e.nombre}</span>
              </div>
            ) : (
              <span
                className="flex min-w-0 items-center gap-1 border-l border-dashed border-muted-foreground/40 pl-2 text-[11px] uppercase tracking-wide text-muted-foreground"
                title={e.detalle}
              >
                <Cog className="h-3 w-3 shrink-0" aria-label="software" />
                <span className="truncate">{e.nombre}</span>
                <Punto estado={e.estado} />
              </span>
            )}
          </div>
        ),
      )}
    </div>
  );
}

/** Chips de las MÉTRICAS de un item del feed (tokens · coste · duración). Nada si no hay
 *  ninguna métrica todavía (run sin generaciones / trabajo aún en cola). */
export function MetricasPipeline({ metricas, className }: { metricas?: PipelineMetricas; className?: string }) {
  if (!metricas) return null;
  const { tokens, coste_usd, duration_ms } = metricas;
  if (tokens == null && coste_usd == null && duration_ms == null) return null;
  if (!metricas.items && !tokens && !coste_usd && !duration_ms) return null;
  return (
    <span className={cn("flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground", className)}>
      {tokens != null && (
        <Badge variant="outline" className="gap-1 text-[10px] tabular-nums" title={`${numeroCompleto(tokens)} tokens`}>
          {numeroCompacto(tokens)} tok
        </Badge>
      )}
      {coste_usd != null && (
        <Badge variant="outline" className="gap-1 text-[10px] tabular-nums" title="Coste de las generaciones">
          <Coins className="h-2.5 w-2.5" aria-hidden="true" />
          {costeUsd(coste_usd)}
        </Badge>
      )}
      {duration_ms != null && duration_ms > 0 && (
        <Badge variant="outline" className="gap-1 text-[10px] tabular-nums" title="Tiempo de cómputo IA">
          <Clock className="h-2.5 w-2.5" aria-hidden="true" />
          {duracion(duration_ms)}
        </Badge>
      )}
    </span>
  );
}

/** Etapas a PINTAR de un item del feed: las de la run tal cual; en un item SUELTO, su única
 *  etapa lleva como nombre la etiqueta legible de su tipo de trabajo (copy, imagen, run…). */
export function etapasDeItem(run: Pipeline): PipelineEtapa[] {
  if (run.clase !== "actividad") return run.etapas;
  return run.etapas.map((e) => ({ ...e, nombre: etiquetaTipoGeneracion(run.tipo || e.nombre) }));
}

/** Tarjeta de un item del feed de Producción (run del pipeline o trabajo suelto): TODA la
 *  tarjeta es clicable (abre su detalle) salvo que no haya detalle que abrir (`onAbrir` null). */
function FilaPipeline({ run, onAbrir }: { run: Pipeline; onAbrir: ((run: Pipeline) => void) | null }) {
  const esActividad = run.clase === "actividad";
  // Tema FUTURO: pipeline aún sin trabajar. Se atenúa y se rotula «En cola» para leerlo como
  // algo que todavía no ha corrido, al final del feed.
  const esFuturo = run.futuro === true;
  return (
    <Card
      role={onAbrir ? "button" : undefined}
      tabIndex={onAbrir ? 0 : undefined}
      onClick={onAbrir ? () => onAbrir(run) : undefined}
      onKeyDown={(e) => {
        if (onAbrir && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onAbrir(run);
        }
      }}
      className={cn(
        "transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        onAbrir && "cursor-pointer hover:bg-accent",
        esFuturo && "opacity-60",
      )}
    >
      <CardContent className="flex items-center gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="shrink-0">{run.marca_nombre || run.marca}</Badge>
            {esActividad && (
              <Badge variant="secondary" className="shrink-0 gap-1 text-[10px]" title="Trabajo manual">
                <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
                {etiquetaTipoGeneracion(run.tipo || "")}
              </Badge>
            )}
            {esFuturo && (
              <Badge
                variant="secondary"
                className="shrink-0 gap-1 text-[10px] text-muted-foreground"
                title="Tema del tablero aún sin trabajar: el pipeline no ha corrido"
              >
                <Clock className="h-2.5 w-2.5" aria-hidden="true" />
                En cola
              </Badge>
            )}
            <ChipEstado estado={run.estado_global} />
            <BadgeVerificacionFuente verificación={run.verificacion ?? undefined} />
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
            <MetricasPipeline metricas={run.metricas} className="ml-auto" />
          </div>
          <p className="truncate text-sm font-medium" title={run.titulo}>{run.titulo}</p>
          <TiraEtapas etapas={etapasDeItem(run)} />
        </div>
        {onAbrir && <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />}
      </CardContent>
    </Card>
  );
}

export { FilaPipeline };

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

/** Bloque de TRANSPARENCIA de una etapa IA: el PROMPT de entrada, el RAZONAMIENTO (stream del
 *  agente, token a token mientras corre) y el RESULTADO. Solo se enseña si la etapa CORRIÓ o está
 *  corriendo (`gen` existe); si aún no ha corrido NO se pinta un in/out vacío. */
function BloqueIA({ gen, plantilla }: { gen?: PipelineGeneracion; plantilla?: string }) {
  // Sin generación real, la etapa no ha corrido: no enseñamos in/out (ni la plantilla suelta).
  if (!gen) return null;
  const enCurso = gen?.estado === "ejecutando";
  const salida = (gen?.salida ?? "").trim();
  const prompt = (gen?.prompt || plantilla || "").trim();
  const esPlantilla = !gen?.prompt && !!plantilla;
  const m = gen?.metricas;
  return (
    <div className="space-y-2 rounded-md border border-violet-500/20 bg-violet-500/5 p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="h-3 w-3 text-violet-600" aria-hidden="true" />
        <span className="text-xs font-semibold text-foreground">IA</span>
        {gen
          ? <ChipEstado estado={enCurso ? "en_curso" : gen.estado === "error" ? "fallo" : "ok"} />
          : <span className="text-[11px] text-muted-foreground">aún no ejecutado</span>}
        {/* Métricas REALES de la llamada (tokens/coste/duración), si la generación las dejó. */}
        {m && (
          <MetricasPipeline
            className="ml-auto"
            metricas={{
              items: 1,
              tokens: (m.tokens_in ?? 0) + (m.tokens_out ?? 0) || null,
              coste_usd: m.total_cost_usd ?? null,
              duration_ms: m.duration_ms ?? null,
            }}
          />
        )}
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
              {enCurso ? "En curso…" : "Aún no ejecutada"}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** Publicacion COMPLETO específico de cada etapa. Las etapas IA enseñan SIEMPRE el BloqueIA
 *  (prompt + razonamiento + resultado); las no-IA muestran su dato propio. */
function PublicacionEtapa({
  clave,
  estado,
  run,
  generacion,
  plantilla,
}: {
  clave: string;
  estado: string;
  run: Pipeline;
  generacion?: PipelineGeneracion;
  plantilla?: string;
}) {
  if (clave === "fusionar" || clave === "priorizar") {
    return (
      <div className="space-y-2 text-xs">
        {run.cluster
          ? <ProcedenciaIA cluster={run.cluster} modo={clave} />
          : <p className="text-muted-foreground">Sin historia.</p>}
        <BloqueIA gen={generacion} plantilla={plantilla} />
      </div>
    );
  }
  if (clave === "admitir") {
    // Admitir: crea el tema en BD (no es IA). Solo la nota de origen.
    return run.descripcion
      ? <Markdown className="text-xs text-muted-foreground">{run.descripcion}</Markdown>
      : null;
  }
  if (clave === "redactar") {
    // Solo el bloque IA (prompt | razonamiento + resultado): el copy final por red ya se ve
    // en la SALIDA del bloque y, sobre todo, en el feed/aprobación (su sitio). No repetimos aquí
    // las tarjetas por red (X/Instagram/Facebook con placa): serían contenido duplicado.
    return <BloqueIA gen={generacion} plantilla={plantilla} />;
  }
  if (clave === "ilustrar") {
    // Solo si Ilustrar CORRIÓ (estado ok): una pieza puede traer la FOTO de la nota de una
    // fuente propia (bajada al recolectar) sin que esta etapa la generara — esa foto vive en
    // la pieza (feed/aprobación), no aquí. Enseñarla con la etapa apagada mentía ("Ilustrar ok").
    const imagenes = estado === "ok" ? run.piezas.filter((p) => p.imagen_url) : [];
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
  if (clave === "verificar") {
    const verificación = run.verificacion;
    return (
      <div className="space-y-2">
        <BloqueIA gen={generacion} plantilla={plantilla} />
        {verificación && (verificación.verificado || verificación.requiere_humano || verificación.rechazado) && (
          <div className="space-y-2 rounded-md border p-2">
            <BadgeVerificacionFuente verificación={verificación} />
            {verificación.resumen && <p className="text-xs text-foreground/90">{verificación.resumen}</p>}
            <ListaHallazgos hallazgos={verificación.hallazgos} />
          </div>
        )}
      </div>
    );
  }
  if (
    clave === "trabajo" ||
    clave === "critica" ||
    clave === "sugerir_hashtags" ||
    clave === "decisor" ||
    clave === "carrusel"
  ) {
    // Trabajo SUELTO (item `clase="actividad"`), Crítica IA (revisión con visión en la cadena
    // de aprobación), Sugerir hashtags (propuesta tras Redactar), Decisor (formato foto/carrusel,
    // justo antes de Redactar) o Carrusel (convierte el copy ya redactado en slides, justo
    // después de Ilustrar): el contenido es el bloque entrada/salida (prompt + razonamiento +
    // resultado).
    return <BloqueIA gen={generacion} plantilla={plantilla} />;
  }
  // aprobar — gate HUMANO (no IA).
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

/** Panel de una etapa. Los procesos de IA (`es_ia`) son ETAPAS plegables con su detalle COMPLETO
 *  (prompt + razonamiento + resultado). Los de software (Admitir/Aprobar) son FRONTERAS: una banda
 *  separadora fina, sin desplegar IA, con su dato propio inline (no son cómputo IA). */
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
  if (!etapa.es_ia) {
    // FRONTERA: límite de software (Admitir = Sistema/BD, Aprobar = humano). Banda fina con
    // su estado y su dato propio inline; NO se despliega como una etapa IA.
    return (
      <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Cog className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="font-medium">{etapa.nombre}</span>
          <Badge variant="outline" className="text-[10px] text-muted-foreground">
            {etapa.clave === "aprobar" ? "Humano" : "Sistema"}
          </Badge>
          <ChipEstado estado={etapa.estado} />
          {etapa.detalle && <span className="text-muted-foreground">· {etapa.detalle}</span>}
        </div>
        <div className="mt-2">
          <PublicacionEtapa clave={etapa.clave} estado={etapa.estado} run={run} generacion={generacion} plantilla={plantilla} />
        </div>
      </div>
    );
  }
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
          {/* Marca clara IA vs no-IA (Admitir/Recolectar = Sistema/BD; Aprobar = Humano). */}
          {etapa.es_ia ? (
            <Badge variant="outline" className="gap-1 border-violet-500/30 text-[10px] text-violet-600">
              <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />IA
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] text-muted-foreground">
              {etapa.clave === "aprobar" ? "Humano" : "Sistema"}
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
          <PublicacionEtapa clave={etapa.clave} estado={etapa.estado} run={run} generacion={generacion} plantilla={plantilla} />
        </div>
      )}
    </div>
  );
}