/**
 * PanelAgentes — el catálogo de agentes INDEPENDIENTES (pestaña Herramientas) como CAJAS por tipo,
 * NO como un pipeline. Cada grupo (`GrupoAgentes`) es una caja en su propia línea: su título y
 * subtítulo (qué cubre el tipo) y, debajo, sus agentes como RECTÁNGULOS del MISMO tamaño (idéntico en
 * todas las cajas), que se envuelven a la siguiente fila si no caben. Entre agentes NO hay conector
 * (↓): no es una secuencia, son prompts autónomos que se lanzan a mano. La descripción de cada agente
 * vive en su subpágina. Clicar un agente abre su prompt en el overlay (solo admin).
 */
import { Bot, Cog } from "lucide-react";
import * as React from "react";

import { EditorPromptOverlay } from "@/components/prompts/EditorPromptOverlay";
import { cn } from "@/lib/utils";
import type { GrupoAgentes } from "@/pages/maquina/fases";

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
      <div className="flex flex-col gap-3">
        {grupos.map((g) => (
          <div key={g.titulo} className="rounded-xl border border-border/70 bg-muted/30 p-3">
            <div className="mb-2 px-1">
              <h3 className="text-sm font-semibold">{g.titulo}</h3>
              <p className="text-xs text-muted-foreground">{g.descripcion}</p>
            </div>
            {/* Agentes como rectángulos del MISMO tamaño (fijo), envolviendo a la siguiente fila. */}
            <div className="flex flex-wrap gap-2">
              {g.fases.map((f) => {
                const abrir = esAdmin && f.doc ? () => setDocEditando(f.doc!) : undefined;
                return (
                  <button
                    key={f.nombre}
                    type="button"
                    disabled={!abrir}
                    onClick={abrir}
                    title={f.nombre}
                    className={cn(
                      "flex h-20 w-32 flex-col items-center justify-center gap-1.5 rounded-lg border border-border/70 bg-card px-2 text-center text-sm font-medium leading-tight",
                      abrir ? "hover:bg-accent" : "cursor-default",
                    )}
                  >
                    {f.es_ia ? (
                      <Bot className="h-5 w-5 shrink-0" aria-label="IA" />
                    ) : (
                      <Cog className="h-5 w-5 shrink-0 text-muted-foreground" aria-label="determinista" />
                    )}
                    <span className="line-clamp-2 break-words">{f.nombre}</span>
                  </button>
                );
              })}
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
