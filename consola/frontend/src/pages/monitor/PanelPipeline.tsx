/**
 * Tipo y fila base de una FASE del pipeline.
 *
 * `FasePipeline` es el ESQUELETO de una fase (la comparten `fases.ts`, `DetalleFase`, `FaseDetalle`,
 * `ServiciosMaquina`, `DocumentoContexto`). `FilaFasePipeline` es la fila visual UNIFORME —icono de
 * tipo (🤖/⚙) + nombre + ayuda a la izquierda, un slot `derecha` a la derecha— que pintan tanto la
 * vista Pipeline (`PipelineUnificado`) como los Servicios no-IA (`ServiciosMaquina`).
 */
import { Bot, Cog } from "lucide-react";
import * as React from "react";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { ItemMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";

export interface FasePipeline {
  /** Nombre legible de la fase. */
  nombre: string;
  /** 🤖 (LLM) si es IA, ⚙ (determinista) si no. */
  es_ia: boolean;
  /** Claves del catálogo que gobierna la fase (vacío si no tiene flag propio). `ServiciosMaquina`
   *  las usa para saber qué daemons ya son una fase del pipeline y no listarlos aparte. */
  claves: readonly string[];
  /** Qué hace la fase. */
  ayuda: string;
  /** Doc de la Prompts cuyo prompt alimenta la fase («Editar prompt»). */
  doc?: string;
  /** Sub-prompts que esta fase INYECTA en su propio prompt (no son etapas ni se lanzan solos):
   *  el detalle de la fase los lista para editarlos. P. ej. los envoltorios de red dentro de
   *  Redactar. Cada uno abre su doc en el overlay. */
  subPrompts?: readonly { nombre: string; doc: string; ayuda: string }[];
  /** Clave de cola de la fase (índice en los conteos): muestra sus en curso/en cola. */
  queue?: string;
  /** `true` si la fase inyecta el CONTEXTO editorial de la marca (voz, líneas, tropicalización,
   *  reglas): la pestaña «Contexto» del detalle muestra la estrategia de marca. */
  contextoMarca?: boolean;
  /** Clave de etapa del feed de runs (`GET /api/pipelines?etapa=`): la pestaña «Logs» del detalle
   *  lista el HISTÓRICO real de runs paradas en esta etapa. Sin ella, Logs solo muestra la cola viva. */
  etapa?: string;
  /** Aviso ROJO junto al nombre de la fase: la marca como acción de RIESGO real (p. ej. Publicar
   *  postea de verdad, no en simulación). Se pinta como Badge destructivo en la fila. */
  precaucion?: string;
  /** Abre una ETAPA distinta del flujo: en vez del conector ↓, la fila lleva encima un divisor con
   *  esta etiqueta. Marca que lo que sigue NO corre en la secuencia automática anterior (p. ej.
   *  «Cadena de aprobación»: la Crítica IA corre tras los OK humanos, no justo tras Ilustrar). */
  seccion?: string;
  /** Daemon de sistema cuyos BARRIDOS son los logs de esta fase
   *  (`GET /api/sistema/daemons/{daemon}/barridos`). Hace la fase navegable: su subpágina muestra el
   *  log por barrido del daemon (p. ej. Google Trends → daemon `trends`). */
  daemon?: string;
  /** Id de GRUPO PARALELO: las fases CONSECUTIVAS con el mismo id son fuentes que alimentan el
   *  mismo pool y se pintan LADO A LADO en una fila, con un solo conector ↓ antes del grupo (p. ej.
   *  Recolectar + Google Trends, ambas de ingesta). */
  paralelo?: string;
  /** Panel PROPIO (no Prompt · Contexto · Logs) que es el contenido de la subpágina de la fase.
   *  Hace la fase navegable: su subpágina monta ese panel (p. ej. Stock → toggles de fuentes). */
  panel?: "stock";
}

/**
 * Fila VISUAL de una entrada del pipeline (alto uniforme): icono de tipo (🤖/⚙) + nombre (línea 1)
 * y ayuda (línea 2) a la izquierda; un slot `derecha` (conteos, switch, chevron…) a la derecha.
 * La comparten las ETAPAS del pipeline y los SERVICIOS no-IA (mismo formato).
 */
export function FilaFasePipeline({
  esIa,
  nombre,
  ayuda,
  precaucion,
  derecha,
  onPrimaria,
  acciones = [],
  etiquetaAcciones,
}: {
  esIa: boolean;
  nombre: string;
  ayuda?: React.ReactNode;
  /** Aviso ROJO junto al nombre: marca la fase como acción de riesgo real (p. ej. Publicar). */
  precaucion?: string;
  derecha?: React.ReactNode;
  onPrimaria?: () => void;
  acciones?: ItemMenuContextual[];
  etiquetaAcciones?: string;
}) {
  return (
    <FilaConAcciones
      como="div"
      acciones={acciones}
      onPrimaria={onPrimaria}
      kebab="nunca"
      realce
      etiquetaAcciones={etiquetaAcciones}
      className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-card px-3.5 py-2.5"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-sm font-medium">
          {esIa ? (
            <Bot className="h-4 w-4 shrink-0" aria-label="IA" />
          ) : (
            <Cog className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="determinista" />
          )}
          <span className="truncate">{nombre}</span>
          {precaucion && (
            <Badge variant="error" className="shrink-0 px-1.5 py-0 text-[10px] font-medium">
              {precaucion}
            </Badge>
          )}
        </div>
        {ayuda != null && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{ayuda}</p>
        )}
      </div>
      {derecha != null && <div className="flex shrink-0 items-center gap-3">{derecha}</div>}
    </FilaConAcciones>
  );
}
