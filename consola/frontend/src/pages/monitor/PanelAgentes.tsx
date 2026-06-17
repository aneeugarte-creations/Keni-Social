/**
 * PanelAgentes — el catálogo de agentes INDEPENDIENTES (Importación, Herramientas) como CAJAS por
 * tipo, NO como un pipeline. Cada grupo (`GrupoAgentes`) es una caja con su título y sus agentes
 * dentro; entre agentes NO hay conector (↓): no es una secuencia, son prompts autónomos que se
 * lanzan a mano. Clicar un agente abre su prompt en el overlay (solo admin). Reutiliza la fila de
 * `PanelPipeline` (`FilaFasePipeline`) para que el formato de cada agente sea idéntico al de una fase.
 */
import * as React from "react";

import { EditorPromptOverlay } from "@/components/prompts/EditorPromptOverlay";
import type { GrupoAgentes } from "@/pages/maquina/fases";
import { FilaFasePipeline } from "@/pages/monitor/PanelPipeline";

export function PanelAgentes({
  grupos,
  esAdmin = true,
}: {
  /** Los tipos de agente, cada uno su caja. */
  grupos: readonly GrupoAgentes[];
  /** Admin: clicar un agente abre su prompt. No-admin: cajas informativas (sin click). */
  esAdmin?: boolean;
}) {
  // Doc abierto en el overlay «Editar prompt» (in-place).
  const [docEditando, setDocEditando] = React.useState<string | null>(null);

  return (
    <section data-testid="panel-agentes">
      <div className="grid gap-4 sm:grid-cols-2">
        {grupos.map((g) => (
          <div key={g.titulo} className="rounded-xl border border-border/70 bg-muted/30 p-3">
            <div className="mb-2 px-1">
              <h3 className="text-sm font-semibold">{g.titulo}</h3>
              {g.descripcion && <p className="text-xs text-muted-foreground">{g.descripcion}</p>}
            </div>
            <div className="flex flex-col gap-2">
              {g.fases.map((f) => (
                <FilaFasePipeline
                  key={f.nombre}
                  esIa={f.es_ia}
                  nombre={f.nombre}
                  ayuda={f.ayuda}
                  onPrimaria={esAdmin && f.doc ? () => setDocEditando(f.doc!) : undefined}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <EditorPromptOverlay
        docId={docEditando}
        abierto={docEditando !== null}
        onCerrar={() => setDocEditando(null)}
      />
    </section>
  );
}
