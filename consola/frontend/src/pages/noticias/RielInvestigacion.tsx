/**
 * RielInvestigacion — la fase de ANTES (en el flujo) del proceso de Investigación, hecho visible.
 *
 * Es la mitad AUTOMÁTICA e INFORMATIVA del flujo: una tira horizontal del flujo COMPLETO que
 * la máquina corre sola (Recolectar · Agrupar · Fusionar · Traducir · Clasificar · Priorizar ·
 * Admitir · Verificar) con su estado ON/OFF y su tipo (🤖 LLM / ⚙ determinista). NO es la tira de
 * control (esa es «Pipeline en vivo», con switches por etapa); aquí solo se LEE qué hace el motor
 * y si está encendido. El nombre evita chocar con el «riel de la máquina» de la Biblioteca
 * (`pages/texto/RielMaquina`, que son etapas de PROMPT, no de noticias): este es el riel de
 * recolección de noticias.
 *
 * El estado se lee del catálogo de ajustes (`GET /api/ajustes`, solo admin) por la `clave` de
 * cada flag físico, con el maestro VIRTUAL «Investigación» (`KENI_INVESTIGACION`) como respaldo
 * para las etapas sin flag propio (Agrupar/Traducir/Admitir). Los toggles reales viven en
 * «Pipeline en vivo» (control) y en el drawer de ajustes del motor. El lápiz de cada etapa con
 * prompt abre su documento de la Biblioteca en un OVERLAY (in-place, sin salir del cockpit).
 */
import { useQuery } from "@tanstack/react-query";
import { Bot, ChevronDown, ChevronRight, Cog } from "lucide-react";
import * as React from "react";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { Tooltip } from "@/components/ui/tooltip";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_AJUSTES } from "@/pages/configuracion/lib";
import { ChipInvestigacion } from "@/pages/noticias/ChipInvestigacion";

/** El maestro VIRTUAL de Investigación: único toggle del proceso que expone el catálogo (y que
 *  mantiene sincronizadas sus etapas físicas). Respaldo cuando la etapa no tiene flag propio
 *  en el catálogo. */
const MAESTRO_INVESTIGACION = "KENI_INVESTIGACION";

type EstadoEtapa = "on" | "off" | "desconocido";

interface EtapaProceso {
  /** Nombre legible de la etapa. */
  nombre: string;
  /** Tipo de la etapa: 🤖 (LLM) si es IA, ⚙ (determinista) si no. */
  es_ia: boolean;
  /** Claves del catálogo a consultar EN ORDEN; la primera presente decide el estado. */
  claves: readonly string[];
  /** Qué hace la etapa (tooltip). */
  ayuda: string;
  /** Doc de la Biblioteca cuyo prompt alimenta la etapa (lápiz «Editar prompt»). */
  doc?: string;
}

// El flujo COMPLETO del tramo aguas arriba (ADR 0011), en orden. Cada etapa resuelve su estado
// por su flag físico y, si el catálogo no lo expone, cae al maestro `KENI_INVESTIGACION`.
const ETAPAS: readonly EtapaProceso[] = [
  {
    nombre: "Recolectar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR", MAESTRO_INVESTIGACION],
    ayuda: "Recolecta artículos de las fuentes",
  },
  {
    nombre: "Agrupar",
    es_ia: false,
    claves: ["KENI_PIPELINE_RECOLECTAR", MAESTRO_INVESTIGACION],
    ayuda: "Agrupa las notas parecidas del mismo evento",
  },
  {
    nombre: "Fusionar",
    es_ia: true,
    claves: ["KENI_PIPELINE_FUSIONAR", MAESTRO_INVESTIGACION],
    ayuda: "Funde las notas agrupadas en una sola historia",
    doc: "prompt/fusionar",
  },
  {
    nombre: "Traducir",
    es_ia: true,
    claves: [MAESTRO_INVESTIGACION],
    ayuda: "Adapta el texto al español de México",
    doc: "prompt/traducir",
  },
  {
    nombre: "Clasificar",
    es_ia: true,
    claves: ["KENI_CLASIFICAR_MARCA_IA", MAESTRO_INVESTIGACION],
    ayuda: "Asigna marca a las notas de últimas horas",
    doc: "prompt/clasificar-marca",
  },
  {
    nombre: "Priorizar",
    es_ia: true,
    claves: ["KENI_PRIORIZAR_PERFIL_IA", MAESTRO_INVESTIGACION],
    ayuda: "Ordena por relevancia para tu marca",
    doc: "prompt/priorizar",
  },
  {
    nombre: "Admitir",
    es_ia: false,
    claves: [MAESTRO_INVESTIGACION],
    ayuda: "Crea el tema admitido en la mesa de redacción",
  },
  {
    nombre: "Verificar",
    es_ia: true,
    claves: ["KENI_PIPELINE_VERIFICAR", MAESTRO_INVESTIGACION],
    ayuda: "Contrasta las fuentes antes de pasar a la mesa",
    doc: "prompt/verificar",
  },
] as const;

function Punto({ estado }: { estado: EstadoEtapa }) {
  return (
    <span
      className={cn(
        "h-2 w-2 shrink-0 rounded-full",
        estado === "on" && "bg-emerald-500",
        estado === "off" && "bg-muted-foreground/40",
        estado === "desconocido" && "bg-muted-foreground/20 ring-1 ring-muted-foreground/30",
      )}
      aria-hidden="true"
    />
  );
}

export function RielInvestigacion() {
  const { usuario } = useSesion();
  const esAdmin = usuario === null || usuario.rol === "admin";

  // Prompt abierto en el overlay «Editar prompt» (in-place, sin sacarte del cockpit).
  const [docAbierto, setDocAbierto] = React.useState<string | null>(null);

  // El estado ON/OFF solo es legible por admin (el endpoint /api/ajustes lo exige). Para el
  // resto la tira sigue siendo informativa (los nombres del proceso), con estado «desconocido».
  const { data } = useQuery({
    queryKey: CLAVE_AJUSTES,
    queryFn: ({ signal }) => api.ajustes(signal),
    enabled: esAdmin,
  });

  const valores = React.useMemo(() => {
    const mapa = new Map<string, boolean>();
    for (const grupo of data?.grupos ?? [])
      for (const ajuste of grupo.ajustes) mapa.set(ajuste.clave, Boolean(ajuste.valor));
    return mapa;
  }, [data]);

  const estadoDe = React.useCallback(
    (claves: readonly string[]): EstadoEtapa => {
      if (!esAdmin) return "desconocido";
      for (const clave of claves) {
        const valor = valores.get(clave);
        if (valor !== undefined) return valor ? "on" : "off";
      }
      return "desconocido";
    },
    [esAdmin, valores],
  );

  const etiquetaEstado = (estado: EstadoEtapa) =>
    estado === "on" ? "activa" : estado === "off" ? "apagada" : "estado no disponible";

  return (
    <section aria-label="Aguas arriba: recolección automática de noticias" data-testid="riel-investigacion">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Aguas arriba · recolección automática
        </h3>
        {/* El estado del loop (jobs en curso/cola) cabe aquí, como indicador de la fase —no como
            una «vista» aparte—; enlaza a Agentes prefiltrado. */}
        <ChipInvestigacion />
      </div>
      <div className="flex flex-col gap-1.5 sm:flex-row sm:flex-wrap sm:items-center">
        {ETAPAS.map((etapa, i) => {
          const estado = estadoDe(etapa.claves);
          return (
            <React.Fragment key={etapa.nombre}>
              {i > 0 ? (
                <span className="flex justify-center text-muted-foreground/40 sm:justify-start" aria-hidden>
                  <ChevronDown className="h-4 w-4 sm:hidden" />
                  <ChevronRight className="hidden h-4 w-4 sm:block" />
                </span>
              ) : null}
              <Tooltip label={`${etapa.ayuda} (${etiquetaEstado(estado)})`} side="top">
                {/* La BURBUJA es el botón: si la etapa tiene prompt (y eres admin), tocarla edita
                    su documento IN-PLACE (overlay), sin lápiz suelto. El borde vira a naranja al
                    hover como pista. Las etapas mecánicas (Recolectar) no son clicables. */}
                {esAdmin && etapa.doc ? (
                  <button
                    type="button"
                    onClick={() => setDocAbierto(etapa.doc!)}
                    aria-label={`Editar el prompt de ${etapa.nombre}`}
                    data-testid={`etapa-${etapa.nombre.toLowerCase()}`}
                    data-estado={estado}
                    className="flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-card px-3 py-2 text-sm shadow-sm transition-colors hover:border-keni-300 focus-visible:border-keni-300 focus-visible:outline-none"
                  >
                    <Punto estado={estado} />
                    {etapa.es_ia ? (
                      <Bot className="h-3.5 w-3.5 shrink-0" aria-label="IA" />
                    ) : (
                      <Cog className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="determinista" />
                    )}
                    <span className="font-medium leading-none">{etapa.nombre}</span>
                  </button>
                ) : (
                  <div
                    className="flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-2 text-sm shadow-sm"
                    data-testid={`etapa-${etapa.nombre.toLowerCase()}`}
                    data-estado={estado}
                  >
                    <Punto estado={estado} />
                    {etapa.es_ia ? (
                      <Bot className="h-3.5 w-3.5 shrink-0" aria-label="IA" />
                    ) : (
                      <Cog className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="determinista" />
                    )}
                    <span className="font-medium leading-none">{etapa.nombre}</span>
                  </div>
                )}
              </Tooltip>
            </React.Fragment>
          );
        })}
      </div>
      {esAdmin && (
        <p className="mt-1.5 text-xs text-muted-foreground">
          Informativo. Enciende o apaga cada etapa en «Pipeline en vivo» o en los ajustes del motor.
        </p>
      )}

      <EditorPromptOverlay
        docId={docAbierto}
        abierto={docAbierto !== null}
        onCerrar={() => setDocAbierto(null)}
      />
    </section>
  );
}
