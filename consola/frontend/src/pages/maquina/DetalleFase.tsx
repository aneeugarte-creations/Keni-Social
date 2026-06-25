/**
 * DetalleFase — el detalle de UNA fase del pipeline (o de un prompt suelto), en pestañas:
 *   · Prompt   — el documento maestro que alimenta la fase, en el editor completo
 *     (Versiones / Compilado / Publicar). Solo si la fase tiene prompt.
 *   · Acompaña — TODO lo que el prompt maestro arrastra: sus sub-prompts (fragmentos que inyecta,
 *     p. ej. los envoltorios de red) y el editorial por marca que inyecta. Cada elemento ABRE SU
 *     PROPIA SUBPÁGINA (`/maquina/contexto/doc/<id>`), con el mismo control que el maestro; sin
 *     pop-ups. En Investigación el editorial son las líneas/orígenes (CRUD inline, sin subpágina).
 *   · Logs     — el log por barrido del daemon de la fase (`daemon`), o el HISTÓRICO real de runs
 *     paradas en esta etapa (`GET /api/pipelines?etapa=`) cuando la fase tiene `etapa`; si no, los
 *     trabajos en vivo de su cola.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Save } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { ChipEstado } from "@/components/comunes/ChipEstado";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { PanelAcerca } from "@/components/prompts/PanelAcerca";
import { PanelContextoInyectado } from "@/components/prompts/PanelContextoInyectado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import { LogBarridos } from "@/pages/maquina/LogBarridos";
import type { FasePipeline } from "@/pages/monitor/PanelPipeline";
import {
  type AccionesPublicarSubpagina,
  DetalleDocumento,
} from "@/pages/prompts/DetalleDocumento";
import { EstrategiaMarca } from "@/pages/prompts/estrategia/EstrategiaMarca";
import type { ColaJob, ColaMonitor } from "@/types";

/** Motores con contexto editorial por marca; las pestañas-catálogo (Herramientas / Desarrollo) son
 *  prompts sueltos sin contexto ni logs propios. */
type Proceso = "investigacion" | "produccion";
type ProcesoFase = Proceso | "herramientas" | "desarrollo";
type PestanaFase = "prompt" | "acompana" | "logs";

/** Ruta de la subpágina de UN documento (editorial o sub-prompt) que acompaña al maestro. */
function rutaDoc(docId: string): string {
  return `/maquina/contexto/doc/${docId}`;
}

/** Estado abierto/colapsado de la tarjeta «Acerca de» (recordado entre sesiones). */
const CLAVE_ACERCA = "keni.fase.acerca-abierto";

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

/** Logs de la fase: barridos de su daemon (`LogBarridos`), histórico real por etapa
 *  (`api.pipelines`) o, sin nada de eso, la cola viva. */
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

  // Fases respaldadas por un daemon (p. ej. Google Trends): sus logs son el log por barrido.
  if (fase.daemon) {
    return <LogBarridos daemon={fase.daemon} />;
  }

  if (fase.etapa) {
    if (historico.isPending) return <Skeleton className="h-24 w-full" />;
    const runs = historico.data?.pipelines ?? [];
    if (runs.length === 0) {
      return <EstadoVacioTexto texto="Sin runs recientes en esta etapa." />;
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
              <ChipEstado estado={r.estado_global} className="text-[11px]" />
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
    return <EstadoVacioTexto texto="Sin trabajos en curso ni en cola." />;
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

/** El editorial por marca que inyecta la fase, según el motor. Cada documento abre su subpágina. */
function EditorialFase({
  fase,
  proceso,
  marca,
  inyectaEditorial,
  onAbrirDoc,
}: {
  fase: FasePipeline;
  proceso: ProcesoFase;
  marca: string | null;
  /** El prompt inyecta editorial (lo dice `contextoInyectado`); habilita la lista para fases sin
   *  vista de marca propia. */
  inyectaEditorial: boolean;
  onAbrirDoc: (docId: string) => void;
}) {
  if (proceso === "produccion" && fase.contextoMarca) {
    // Producción: la estrategia de marca (orden de inyección + pilares); cada pilar → su subpágina.
    return marca ? (
      <EstrategiaMarca marca={marca} onAbrirDoc={onAbrirDoc} />
    ) : (
      <p className="text-sm text-muted-foreground">
        Elige una marca en la barra superior para ver el editorial que inyecta esta fase.
      </p>
    );
  }

  // Cualquier otro prompt que inyecte editorial: la lista de adjuntos para la marca activa; cada
  // uno abre su subpágina (no overlay).
  if (inyectaEditorial && fase.doc) {
    return <PanelContextoInyectado docId={fase.doc} onAbrirDoc={onAbrirDoc} />;
  }

  return null;
}

/** Pestaña «Acompaña»: el prompt maestro y todo lo que arrastra — sus sub-prompts y su editorial
 *  por marca — en secciones por tipo; cada elemento abre su propia subpágina. */
function AcompanaFase({
  fase,
  proceso,
  marca,
  inyectaEditorial,
  onAbrirDoc,
}: {
  fase: FasePipeline;
  proceso: ProcesoFase;
  marca: string | null;
  inyectaEditorial: boolean;
  onAbrirDoc: (docId: string) => void;
}) {
  const subPrompts = fase.subPrompts ?? [];
  const mostrarEditorial = !!fase.contextoMarca || inyectaEditorial;

  return (
    <div className="space-y-6">
      {subPrompts.length > 0 ? (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Sub-prompts
          </h4>
          <p className="mb-2 text-xs text-muted-foreground">
            Fragmentos que este prompt compone dentro del suyo según el caso (p. ej. los envoltorios
            de red). No se lanzan por separado; cada uno se edita en su subpágina.
          </p>
          <div className="flex flex-wrap gap-2">
            {subPrompts.map((sp) => (
              <Button
                key={sp.doc}
                type="button"
                variant="outline"
                size="sm"
                title={sp.ayuda}
                onClick={() => onAbrirDoc(sp.doc)}
              >
                {sp.nombre}
              </Button>
            ))}
          </div>
        </section>
      ) : null}

      {mostrarEditorial ? (
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Editorial
          </h4>
          <EditorialFase
            fase={fase}
            proceso={proceso}
            marca={marca}
            inyectaEditorial={inyectaEditorial}
            onAbrirDoc={onAbrirDoc}
          />
        </section>
      ) : null}
    </div>
  );
}

export function DetalleFase({
  fase,
  proceso,
  marca,
  cola,
  queuePorTipo = {},
  mostrarLogs = true,
}: {
  fase: FasePipeline;
  /** Proceso de la fase: en los motores decide qué contexto editorial se muestra; en las
   *  pestañas-catálogo (Herramientas / Desarrollo) la fase es un prompt suelto sin contexto. */
  proceso: ProcesoFase;
  /** Marca activa (la del switch global); el contexto editorial es por marca. */
  marca: string | null;
  /** Snapshot de cola para los logs en vivo de las fases sin etapa propia. */
  cola?: ColaMonitor;
  /** Mapa tipo-de-job → clave de cola, para filtrar los logs en vivo de esta fase. */
  queuePorTipo?: Record<string, string>;
  /** Pinta la pestaña Logs (pipeline/cola). Los agentes sueltos (Herramientas / Desarrollo) no
   *  encolan ni dejan histórico propio, así que la ocultan: solo Prompt. */
  mostrarLogs?: boolean;
}) {
  const navigate = useNavigate();
  // Abrir un sub-prompt o editorial NAVEGA a su subpágina (con el mismo control que el maestro);
  // ya no hay overlay.
  const abrirDoc = React.useCallback(
    (docId: string) => navigate(rutaDoc(docId)),
    [navigate],
  );

  // El flujo de la máquina alimenta la pestaña «Uso» del editor de prompt.
  const maquinaQuery = useQuery({
    queryKey: ["prompts-maquina"],
    queryFn: ({ signal }) => api.maquinaPrompts(signal),
    enabled: !!fase.doc,
  });

  const tieneprompt = !!fase.doc;
  // ¿El prompt inyecta editorial? (independiente de marca; decide la pestaña «Acompaña» y su lista
  // para fases sin vista de marca propia). Misma queryKey que el editor → React Query dedupe.
  const inyectaQuery = useQuery({
    queryKey: ["prompts-contexto-inyecta", fase.doc],
    queryFn: ({ signal }) => api.contextoInyectado(fase.doc as string, undefined, signal),
    enabled: tieneprompt && !fase.contextoMarca,
  });
  const inyectaEditorial = inyectaQuery.data?.inyecta === true;
  const tieneAcompana =
    (fase.subPrompts?.length ?? 0) > 0 || !!fase.contextoMarca || inyectaEditorial;
  const inicial: PestanaFase = tieneprompt ? "prompt" : tieneAcompana ? "acompana" : "logs";
  // Sin pestaña Logs (agentes sueltos) el estado nunca debe quedar en "logs".
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
            {tieneAcompana ? <TabsTrigger value="acompana">Acompaña</TabsTrigger> : null}
            {mostrarLogs ? <TabsTrigger value="logs">Logs</TabsTrigger> : null}
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

        {tieneAcompana ? (
          <TabsContent value="acompana" className="mt-3">
            <AcompanaFase
              fase={fase}
              proceso={proceso}
              marca={marca}
              inyectaEditorial={inyectaEditorial}
              onAbrirDoc={abrirDoc}
            />
          </TabsContent>
        ) : null}

        {mostrarLogs ? (
          <TabsContent value="logs" className="mt-3">
            <LogsFase fase={fase} marca={marca} cola={cola} queuePorTipo={queuePorTipo} />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}
