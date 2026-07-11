/**
 * PanelAgentes — el catálogo de agentes INDEPENDIENTES (pestañas Herramientas y Desarrollo) como
 * CAJAS por tipo, NO como un pipeline. Cada grupo (`GrupoAgentes`) es una caja en su propia línea:
 * su título y subtítulo (qué cubre el tipo) y, debajo, sus agentes como RECTÁNGULOS del MISMO tamaño
 * (idéntico en todas las cajas), que se envuelven a la siguiente fila si no caben. Entre agentes NO
 * hay conector (↓): no es una secuencia, son prompts autónomos que se lanzan a mano. La descripción
 * de cada agente vive en su subpágina. Clicar un agente ABRE SU SUBPÁGINA (Prompt · Acerca), nunca un
 * pop-up (solo admin).
 */
import { Bot, Cog } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { cn } from "@/lib/utils";
import { Tooltip } from "@/components/ui/tooltip";
import { type GrupoAgentes, slugFase } from "@/pages/maquina/fases";

export function PanelAgentes({
  grupos,
  proceso,
  esAdmin = true,
}: {
  /** Los tipos de agente, cada uno su caja. */
  grupos: readonly GrupoAgentes[];
  /** La pestaña-catálogo a la que pertenecen: gobierna la URL de la subpágina de cada agente. */
  proceso: "herramientas" | "desarrollo";
  /** Admin: clicar un agente abre su subpágina. No-admin: cajas informativas (sin click). */
  esAdmin?: boolean;
}) {
  const navigate = useNavigate();

  return (
    <section data-testid="panel-agentes">
      <div className="flex flex-col gap-3">
        {grupos.map((g) => (
          <div key={g.titulo} className="rounded-xl border bg-card p-3">
            <div className="mb-2 px-1">
              <h3 className="text-sm font-semibold">{g.titulo}</h3>
              <p className="text-xs text-muted-foreground">{g.descripcion}</p>
            </div>
            {/* Agentes como rectángulos del MISMO tamaño (fijo), envolviendo a la siguiente fila. */}
            <div className="flex flex-wrap gap-2">
              {g.fases.map((f) => {
                const abrir =
                  esAdmin && f.doc
                    ? () => navigate(`/maquina/contexto/${proceso}/${slugFase(f.nombre)}`)
                    : undefined;
                return (
                  <Tooltip key={f.nombre} label={f.nombre}>
                    <button
                      type="button"
                      disabled={!abrir}
                      onClick={abrir}
                      className={cn(
                        "flex h-20 w-32 flex-col items-center justify-center gap-1.5 rounded-xl border bg-card px-2 text-center text-sm font-medium leading-tight",
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
                  </Tooltip>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
