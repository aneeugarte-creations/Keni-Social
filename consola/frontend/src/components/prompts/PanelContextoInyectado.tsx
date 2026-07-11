/**
 * Lista de los documentos EDITORIALES que un prompt INYECTA, para la pestaña «Acompaña» de la
 * subpágina de una fase.
 *
 * La inyección es por marca + pipeline (el mismo compositor que la generación real). La marca la da
 * el selector GLOBAL (`useMarcaActiva`); esta vista no tiene selector propio. Cada fila es un enlace
 * LÓGICO (soft link) al doc canónico: clicar ABRE SU SUBPÁGINA (`onAbrirDoc`), no un overlay; no se
 * duplica nada. Un prompt que no lleva contexto editorial muestra un estado vacío.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";

export function PanelContextoInyectado({
  docId,
  onAbrirDoc,
}: {
  docId: string;
  /** Abre el documento editorial: su subpágina (`/maquina/contexto/doc/<id>`). */
  onAbrirDoc: (docId: string) => void;
}) {
  // Marca del selector GLOBAL; con "Todas" activa (`marcaActiva == null`) cae a la marca primaria.
  const { marcaActiva, marcaPrimaria } = useMarcaActiva();
  const marca = marcaActiva ?? marcaPrimaria ?? "";

  const contextoQuery = useQuery({
    queryKey: ["prompts-contexto", docId, marca],
    queryFn: ({ signal }) => api.contextoInyectado(docId, marca, signal),
  });
  const datos = contextoQuery.data;

  const adjuntos = datos?.adjuntos ?? [];

  return (
    <div className="space-y-3">
      {contextoQuery.isPending ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : datos && !datos.inyecta ? (
        <p className="rounded-xl border border-dashed bg-muted/30 px-3 py-6 text-center text-xs text-muted-foreground">
          Este prompt no inyecta contexto editorial.
        </p>
      ) : adjuntos.length === 0 ? (
        <p className="rounded-xl border border-dashed bg-muted/30 px-3 py-6 text-center text-xs text-muted-foreground">
          No hay documentos editoriales para esta marca todavía.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {adjuntos.map((a) => (
            <li key={a.id}>
              <Tooltip label={`Abrir ${a.titulo}`} className="block w-full">
                <button
                  type="button"
                  onClick={() => onAbrirDoc(a.id)}
                  className="flex w-full items-center gap-2 rounded-xl border bg-card px-2.5 py-2 text-left text-sm transition-colors hover:border-input hover:bg-accent"
                >
                  <span className="min-w-0 flex-1 truncate">{a.titulo}</span>
                  {a.clase ? (
                    <Badge variant="secondary" className="shrink-0">
                      {a.clase}
                    </Badge>
                  ) : null}
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                </button>
              </Tooltip>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
