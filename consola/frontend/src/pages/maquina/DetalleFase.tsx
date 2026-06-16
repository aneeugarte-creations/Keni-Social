/**
 * DetalleFase — el panel inline que se despliega bajo una fila del pipeline en la página
 * «Contexto». Reúne, para UNA fase, todo lo suyo en tres pestañas:
 *   · Prompt   — el documento de la Biblioteca que alimenta la fase, en el editor completo
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
import * as React from "react";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import type { FasePipeline } from "@/pages/monitor/PanelPipeline";
import { GestionHashtags } from "@/pages/publicaciones/GestionHashtags";
import { DetalleDocumento } from "@/pages/texto/DetalleDocumento";
import { EstrategiaMarca } from "@/pages/texto/estrategia/EstrategiaMarca";
import { PanelClase } from "@/pages/texto/gestion-lineas/PanelClase";
import type { ColaJob, ColaMonitor } from "@/types";

type Proceso = "investigacion" | "produccion";
type PestanaFase = "prompt" | "contexto" | "logs";

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
    queryKey: ["texto-maquina"],
    queryFn: ({ signal }) => api.maquinaTexto(signal),
    enabled: !!fase.doc,
  });

  const tieneprompt = !!fase.doc;
  const tieneContexto = !!fase.contextoMarca;
  const inicial: PestanaFase = tieneprompt ? "prompt" : tieneContexto ? "contexto" : "logs";
  const [pestana, setPestana] = React.useState<PestanaFase>(inicial);

  return (
    <div>
      <Tabs value={pestana} onValueChange={(v) => setPestana(v as PestanaFase)}>
        <TabsList>
          {tieneprompt ? <TabsTrigger value="prompt">Prompt</TabsTrigger> : null}
          {tieneContexto ? <TabsTrigger value="contexto">Contexto</TabsTrigger> : null}
          <TabsTrigger value="logs">Logs</TabsTrigger>
        </TabsList>

        {tieneprompt ? (
          <TabsContent value="prompt" className="mt-3">
            {/* Editor completo embebido, SIN su cabecera: el atrás y el nombre de la fase los
                pinta la subpágina (FaseDetalle), así no se duplican. `onCerrar` es noop. */}
            <div className="h-[60vh] min-h-0">
              <DetalleDocumento
                key={fase.doc}
                docId={fase.doc as string}
                maquina={maquinaQuery.data}
                onCerrar={() => {}}
                onIdCambiado={() => {}}
                ocultarCabecera
              />
            </div>
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
