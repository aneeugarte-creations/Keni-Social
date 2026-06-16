/**
 * DetalleFase — el panel inline que se despliega bajo una fila del pipeline en la página
 * «Contexto». Reúne, para UNA fase, todo lo suyo en tres pestañas:
 *   · Prompt   — el documento de la Prompts que alimenta la fase, en el editor completo
 *     (Versiones / Compilado / Publicar). Solo si la fase tiene prompt.
 *   · Contexto — el contexto editorial de la marca que la fase inyecta. En Investigación, las
 *     líneas de contenido y los orígenes que clasifican/priorizan; en Producción, la estrategia
 *     de marca (voz/tropicalización/reglas) y los hashtags. Solo si la fase es `contextoMarca`.
 *   · Logs     — el HISTÓRICO real de runs paradas en esta etapa (`GET /api/pipelines?etapa=`)
 *     cuando la fase tiene `etapa`; si no, los trabajos en vivo de su cola.
 *
 * No navega a otras páginas: abrir un documento del contexto usa el overlay (mismo editor, en un
 * diálogo) y los hashtags su propio diálogo.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Save } from "lucide-react";
import * as React from "react";

import { EditorPromptOverlay } from "@/components/prompts/EditorPromptOverlay";
import { PanelAcerca } from "@/components/prompts/PanelAcerca";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { FasePipeline } from "@/pages/monitor/PanelPipeline";
import { GestionHashtags } from "@/pages/publicaciones/GestionHashtags";
import {
  type AccionesPublicarSubpagina,
  DetalleDocumento,
} from "@/pages/prompts/DetalleDocumento";
import { EstrategiaMarca } from "@/pages/prompts/estrategia/EstrategiaMarca";
import { PanelClase } from "@/pages/prompts/gestion-lineas/PanelClase";
import type { ColaJob, ColaMonitor } from "@/types";

type Proceso = "investigacion" | "produccion";
type PestanaFase = "prompt" | "contexto" | "logs";

/** Estado abierto/colapsado de la tarjeta «Acerca de» (recordado entre sesiones). */
const CLAVE_ACERCA = "keni.fase.acerca-abierto";

const VARIANTE_ESTADO: Record<string, "ok" | "aviso" | "error" | "secondary"> = {
  ok: "ok",
  en_curso: "secondary",
  pendiente: "secondary",
  revisar: "aviso",
  fallo: "error",
};

/** Una fila de log de la cola viva: el trabajo de la fase con su marca y estado. */
function FilaCola({ job }: { job: ColaJob }) {
  return (
    <li className="flex items-center justify-between gap-3 px-2 py-1.5 text-xs">
      <span className="min-w-0 truncate">
        <span className="font-medium">{job.etiqueta || job.tipo}</span>
        {job.marca ? <span className="text-muted-foreground"> · {job.marca}</span> : null}
      </span>
      <span className="shrink-0 tabular-nums text-muted-foreground">{job.gen_estado || job.estado}</span>
    </li>
  );
}

/** Logs de la fase: histórico real por etapa (`api.pipelines`) o, sin etapa, la cola viva. */
function LogsFase({
  fase,
  marca,
  cola,
  queuePorTipo,
}: {
  fase: FasePipeline;
  marca: string | null;
  cola?: ColaMonitor;
  queuePorTipo: Record<string, string>;
}) {
  const historico = useQuery({
    queryKey: ["pipelines", "fase", fase.etapa, marca ?? "todas"],
    queryFn: ({ signal }) =>
      api.pipelines({ marca: marca ?? undefined, etapa: fase.etapa, limite: 12 }, signal),
    enabled: !!fase.etapa,
  });

  if (fase.etapa) {
    if (historico.isPending) return <Skeleton className="h-24 w-full" />;
    const runs = historico.data?.pipelines ?? [];
    if (runs.length === 0) {
      return <p className="text-sm text-muted-foreground">Sin runs recientes en esta etapa.</p>;
    }
    return (
      <ul className="divide-y divide-border/60 rounded-md border border-border/60">
        {runs.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-3 px-2 py-1.5 text-xs">
            <span className="min-w-0 truncate">
              <span className="font-medium">{r.titulo}</span>
              {r.marca_nombre ? <span className="text-muted-foreground"> · {r.marca_nombre}</span> : null}
            </span>
            <span className="flex shrink-0 items-center gap-2">
              <Badge variant={VARIANTE_ESTADO[r.estado_global] ?? "secondary"} className="text-[11px]">
                {r.estado_global}
              </Badge>
              <span className="tabular-nums text-muted-foreground">
                {tiempoRelativo(r.actualizado) || r.actualizado?.slice(0, 10)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    );
  }

  // Sin etapa propia (fases deterministas/heredadas): la cola viva de su `queue`.
  const enCurso = (cola?.en_curso ?? []).filter((j) => fase.queue && queuePorTipo[j.tipo] === fase.queue);
  const esperando = (cola?.esperando ?? []).filter((j) => fase.queue && queuePorTipo[j.tipo] === fase.queue);
  if (!fase.queue) {
    return (
      <p className="text-sm text-muted-foreground">
        Esta fase no encola trabajos propios (corre junto a su fase maestra).
      </p>
    );
  }
  if (enCurso.length === 0 && esperando.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin trabajos en curso ni en cola.</p>;
  }
  return (
    <div className="space-y-3">
      {enCurso.length > 0 ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            En curso ({enCurso.length})
          </p>
          <ul className="divide-y divide-border/60 rounded-md border border-border/60">
            {enCurso.map((j) => (
              <FilaCola key={j.job_id} job={j} />
            ))}
          </ul>
        </div>
      ) : null}
      {esperando.length > 0 ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            En cola ({esperando.length})
          </p>
          <ul className="divide-y divide-border/60 rounded-md border border-border/60">
            {esperando.map((j) => (
              <FilaCola key={j.job_id} job={j} />
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Contexto editorial que inyecta la fase, según el motor. */
function ContextoFase({
  proceso,
  marca,
  onAbrirDoc,
}: {
  proceso: Proceso;
  marca: string | null;
  onAbrirDoc: (docId: string) => void;
}) {
  const [hashtagsAbierto, setHashtagsAbierto] = React.useState(false);
  // Marcas para el diálogo de hashtags (mismo origen que la gestión de líneas).
  const catalogos = useQuery({
    queryKey: ["contenido", "catalogos"],
    queryFn: ({ signal }) => api.contenido({}, signal),
    enabled: proceso === "produccion",
  });

  if (proceso === "investigacion") {
    // Lo que clasifica/prioriza usa: las líneas de contenido y los orígenes de la marca.
    return (
      <div className="grid gap-6 lg:grid-cols-2">
        <PanelClase clase="vertical" />
        <PanelClase clase="origen" />
      </div>
    );
  }

  // Producción: la estrategia de marca (orden de inyección + pilares) y los hashtags.
  return (
    <div className="space-y-4">
      {marca ? (
        <EstrategiaMarca marca={marca} onAbrirDoc={onAbrirDoc} />
      ) : (
        <p className="text-sm text-muted-foreground">
          Elige una marca en la barra superior para ver el contexto que inyecta esta fase.
        </p>
      )}
      <Button variant="outline" size="sm" onClick={() => setHashtagsAbierto(true)}>
        Gestionar hashtags
      </Button>
      <GestionHashtags
        abierto={hashtagsAbierto}
        onCerrar={() => setHashtagsAbierto(false)}
        marcas={catalogos.data?.catalogos?.marcas ?? []}
      />
    </div>
  );
}

export function DetalleFase({
  fase,
  proceso,
  marca,
  cola,
  queuePorTipo,
}: {
  fase: FasePipeline;
  /** Motor de la fase: decide qué contexto editorial se muestra. */
  proceso: Proceso;
  /** Marca activa (la del switch global); el contexto editorial es por marca. */
  marca: string | null;
  /** Snapshot de cola para los logs en vivo de las fases sin etapa propia. */
  cola?: ColaMonitor;
  /** Mapa tipo-de-job → clave de cola, para filtrar los logs en vivo de esta fase. */
  queuePorTipo: Record<string, string>;
}) {
  // Documento editorial abierto desde la pestaña Contexto (overlay, no navegación).
  const [docContexto, setDocContexto] = React.useState<string | null>(null);

  // El flujo de la máquina alimenta la pestaña «Uso» del editor de prompt.
  const maquinaQuery = useQuery({
    queryKey: ["prompts-maquina"],
    queryFn: ({ signal }) => api.maquinaPrompts(signal),
    enabled: !!fase.doc,
  });

  const tieneprompt = !!fase.doc;
  const tieneContexto = !!fase.contextoMarca;
  const inicial: PestanaFase = tieneprompt ? "prompt" : tieneContexto ? "contexto" : "logs";
  const [pestana, setPestana] = React.useState<PestanaFase>(inicial);

  // Documento (para la tarjeta «Acerca de»). Misma queryKey que el editor → React Query dedupe.
  const docQuery = useQuery({
    queryKey: ["prompts-doc", fase.doc],
    queryFn: ({ signal }) => api.documento(fase.doc as string, signal),
    enabled: tieneprompt,
  });
  const doc = docQuery.data?.documento ?? null;

  // El botón Publicar del editor sube AQUÍ (a la fila de pestañas) como icono Guardar. El editor
  // reporta su estado/acción vía callback ESTABLE; al desmontarse (otra pestaña) reporta `null`.
  const [acciones, setAcciones] = React.useState<AccionesPublicarSubpagina | null>(null);
  const reportarAcciones = React.useCallback((a: AccionesPublicarSubpagina | null) => {
    setAcciones(a);
  }, []);

  // «Acerca» colapsable: recuerda el estado en localStorage; por defecto, colapsada.
  const [acercaAbierto, setAcercaAbierto] = React.useState(() => {
    try {
      return localStorage.getItem(CLAVE_ACERCA) === "true";
    } catch {
      return false;
    }
  });
  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_ACERCA, String(acercaAbierto));
    } catch {
      /* almacenamiento no disponible: el estado vive solo en memoria */
    }
  }, [acercaAbierto]);

  const tituloPublicar = acciones?.puedePublicar
    ? acciones.esAdmin
      ? "Publicar para que lo usen los agentes"
      : "Proponer estos cambios para publicar"
    : acciones?.cuerpoVacio
      ? "El cuerpo está vacío"
      : "No hay cambios sin publicar";

  return (
    <div className="space-y-4">
      {/* ───────── «Acerca»: permanente sobre las pestañas (visible en Prompt/Contexto/Logs),
          colapsable. Click en TODA la tarjeta colapsa/expande. Solo cuando la fase tiene
          documento de prompt. ───────── */}
      {tieneprompt && doc ? (
        <Card
          role="button"
          tabIndex={0}
          aria-expanded={acercaAbierto}
          onClick={() => setAcercaAbierto((v) => !v)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setAcercaAbierto((v) => !v);
            }
          }}
          className="cursor-pointer"
        >
          <div className="flex w-full items-center justify-between gap-2 p-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Acerca
            </span>
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                !acercaAbierto && "-rotate-90",
              )}
              aria-hidden
            />
          </div>
          {acercaAbierto ? (
            <div className="px-3 pb-3">
              <PanelAcerca doc={doc} maquina={maquinaQuery.data} />
            </div>
          ) : null}
        </Card>
      ) : null}

      <Tabs value={pestana} onValueChange={(v) => setPestana(v as PestanaFase)}>
        {/* Fila de pestañas: a su derecha, el botón Guardar (publicar) monocromo del editor. */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TabsList>
            {tieneprompt ? <TabsTrigger value="prompt">Prompt</TabsTrigger> : null}
            {tieneContexto ? <TabsTrigger value="contexto">Contexto</TabsTrigger> : null}
            <TabsTrigger value="logs">Logs</TabsTrigger>
          </TabsList>
          {tieneprompt && acciones ? (
            <div className="flex items-center gap-2">
              {acciones.sinPublicar ? (
                <Badge variant="aviso" className="hidden rounded-full sm:inline-flex">
                  Cambios sin publicar
                </Badge>
              ) : null}
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 shrink-0 text-foreground"
                disabled={!acciones.puedePublicar}
                title={tituloPublicar}
                aria-label={acciones.esAdmin ? "Publicar" : "Solicitar publicación"}
                onClick={acciones.publicar}
              >
                <Save className="h-4 w-4" />
              </Button>
            </div>
          ) : null}
        </div>

        {tieneprompt ? (
          <TabsContent value="prompt" className="mt-3">
            {/* Editor completo embebido, SIN su cabecera ni su «Acerca de» (los pinta la subpágina);
                sin alto fijo ni scroll interno: crece y scrollea la página. `onCerrar` es noop. */}
            <DetalleDocumento
              key={fase.doc}
              docId={fase.doc as string}
              maquina={maquinaQuery.data}
              onCerrar={() => {}}
              onIdCambiado={() => {}}
              ocultarCabecera
              onAccionesPublicar={reportarAcciones}
            />
          </TabsContent>
        ) : null}

        {tieneContexto ? (
          <TabsContent value="contexto" className="mt-3">
            <ContextoFase proceso={proceso} marca={marca} onAbrirDoc={setDocContexto} />
          </TabsContent>
        ) : null}

        <TabsContent value="logs" className="mt-3">
          <LogsFase fase={fase} marca={marca} cola={cola} queuePorTipo={queuePorTipo} />
        </TabsContent>
      </Tabs>

      <EditorPromptOverlay
        docId={docContexto}
        abierto={docContexto !== null}
        onCerrar={() => setDocContexto(null)}
      />
    </div>
  );
}
