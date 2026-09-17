/**
 * RielInvestigacion — el PROCESO de Investigación hecho visible (ADR 0011).
 *
 * Una tira horizontal de las cinco etapas del proceso (Ingesta · Fusión · Clasificación ·
 * Ranking · Verificación) con su estado ON/OFF, calcada del riel de «La máquina» de la
 * Biblioteca (`pages/texto/VistaMaquina`): tarjetas `rounded-md border bg-card` con punto
 * verde (ON) / gris (OFF) y conectores chevron. En estrecho, apilan en vertical.
 *
 * Es INFORMATIVO (no toggles inline): el estado se lee del catálogo de ajustes
 * (`GET /api/ajustes`, solo admin) por la `clave` de cada flag físico, con el maestro
 * «Investigación» (`KENI_INVESTIGACION`) como respaldo —el único interruptor que el catálogo
 * expone para el proceso, y que mantiene sincronizadas sus etapas físicas—. Los toggles reales
 * viven en el panel «Ajustes del motor» del menú «⋮» de la página.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import * as React from "react";

import { Tooltip } from "@/components/ui/tooltip";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_AJUSTES } from "@/pages/configuracion/lib";

/** El maestro VIRTUAL de Investigación: único toggle del proceso que expone el catálogo (y que
 *  mantiene sincronizadas sus etapas físicas). Respaldo cuando la etapa no tiene flag propio
 *  en el catálogo. */
const MAESTRO_INVESTIGACION = "KENI_INVESTIGACION";

type EstadoEtapa = "on" | "off" | "desconocido";

interface EtapaProceso {
  /** Nombre legible de la etapa. */
  nombre: string;
  /** Claves del catálogo a consultar EN ORDEN; la primera presente decide el estado. */
  claves: readonly string[];
  /** Qué hace la etapa (tooltip). */
  ayuda: string;
}

// Las cinco etapas del proceso Investigación (ADR 0011), en orden de flujo. Cada una resuelve su
// estado por su flag físico y, si el catálogo no lo expone, cae al maestro `KENI_INVESTIGACION`.
const ETAPAS: readonly EtapaProceso[] = [
  {
    nombre: "Ingesta",
    claves: ["KENI_PIPELINE_SELECCION", MAESTRO_INVESTIGACION],
    ayuda: "Recolecta artículos de las fuentes RSS y los archiva.",
  },
  {
    nombre: "Fusión",
    claves: ["KENI_PIPELINE_FUSION", MAESTRO_INVESTIGACION],
    ayuda: "Agrupa con IA las notas del mismo evento en una sola historia.",
  },
  {
    nombre: "Clasificación",
    claves: ["KENI_CLASIFICAR_MARCA_IA", MAESTRO_INVESTIGACION],
    ayuda: "Asigna marca con IA a una última hora sin marca.",
  },
  {
    nombre: "Ranking",
    claves: ["KENI_RANKING_PERFIL_IA", MAESTRO_INVESTIGACION],
    ayuda: "Ordena el pool por el perfil de relevancia de la marca.",
  },
  {
    nombre: "Verificación",
    claves: ["KENI_PIPELINE_VALIDACION", MAESTRO_INVESTIGACION],
    ayuda: "Criba la fuente (QA) antes de dejarla pasar a copy.",
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

  // Tira SLIM de UNA fila (compacta): la etiqueta del proceso vive INLINE al inicio de la fila
  // —no como bloque/encabezado aparte— para no robarle altura al pool de Cobertura que va debajo.
  // El pie de «Ajustes» (admin) se condensa en el tooltip de la etiqueta, no en un párrafo extra.
  return (
    <section aria-label="Proceso de Investigación" data-testid="riel-investigacion">
      <div className="flex flex-col gap-1.5 sm:flex-row sm:flex-wrap sm:items-center">
        <Tooltip
          label={
            esAdmin
              ? "Enciende o apaga cada etapa en «Ajustes del motor» (menú «⋮» arriba)."
              : "Las cinco etapas por las que pasa una noticia antes de llegar al pool."
          }
          side="top"
        >
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Proceso
          </span>
        </Tooltip>
        {ETAPAS.map((etapa) => {
          const estado = estadoDe(etapa.claves);
          return (
            <React.Fragment key={etapa.nombre}>
              <span className="hidden text-muted-foreground/40 sm:block" aria-hidden>
                <ChevronRight className="h-3.5 w-3.5" />
              </span>
              <Tooltip label={`${etapa.ayuda} (${etiquetaEstado(estado)})`} side="top">
                <div
                  className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1 text-xs shadow-sm"
                  data-testid={`etapa-${etapa.nombre.toLowerCase()}`}
                  data-estado={estado}
                >
                  <Punto estado={estado} />
                  <span className="font-medium leading-none">{etapa.nombre}</span>
                </div>
              </Tooltip>
            </React.Fragment>
          );
        })}
      </div>
    </section>
  );
}
