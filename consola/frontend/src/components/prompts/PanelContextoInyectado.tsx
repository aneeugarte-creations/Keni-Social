/**
 * Pestaña «Contexto» del editor de un prompt: los documentos EDITORIALES que ese prompt INYECTA.
 *
 * La inyección es por marca + pipeline (el mismo compositor que la generación real), así que se
 * elige una marca y se listan, en orden de ensamblaje, los editoriales que entran. Cada fila es un
 * enlace LÓGICO (soft link) al doc canónico: abre el editorial en un overlay; no se duplica nada.
 * Un prompt que no lleva contexto editorial (envoltorios, asistente, recibir/importar, traducir,
 * fusionar, clasificar, hashtags, ilustrar) muestra un estado vacío.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import * as React from "react";

import { EditorPromptOverlay } from "@/components/prompts/EditorPromptOverlay";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export function PanelContextoInyectado({ docId }: { docId: string }) {
  const marcasQuery = useQuery({
    queryKey: ["prompts-marcas"],
    queryFn: ({ signal }) => api.marcasPrompts(signal),
  });
  const marcas = marcasQuery.data?.marcas ?? [];

  // Marca seleccionada: por defecto la primera del catálogo (la inyección es por marca).
  const [marca, setMarca] = React.useState("");
  React.useEffect(() => {
    if (!marca && marcas.length > 0) setMarca(marcas[0].id);
  }, [marca, marcas]);

  const contextoQuery = useQuery({
    queryKey: ["prompts-contexto", docId, marca],
    queryFn: ({ signal }) => api.contextoInyectado(docId, marca, signal),
    enabled: !!marca,
  });
  const datos = contextoQuery.data;

  // Editorial abierto en overlay (enlace lógico al doc canónico; no se duplica).
  const [editorialAbierto, setEditorialAbierto] = React.useState<string | null>(null);

  const adjuntos = datos?.adjuntos ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">Marca</span>
        <SelectorMarca
          marcas={marcas}
          valor={marca}
          onCambio={setMarca}
          incluirTodas={false}
          ariaLabel="Marca para la previsualización del contexto"
          className="h-8 w-44"
        />
      </div>

      {contextoQuery.isPending && marca ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : datos && !datos.inyecta ? (
        <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-6 text-center text-xs text-muted-foreground">
          Este prompt no inyecta contexto editorial.
        </p>
      ) : adjuntos.length === 0 ? (
        <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-6 text-center text-xs text-muted-foreground">
          No hay documentos editoriales para esta marca todavía.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {adjuntos.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => setEditorialAbierto(a.id)}
                className="flex w-full items-center gap-2 rounded-md border border-border bg-card px-2.5 py-2 text-left text-sm transition-colors hover:border-input hover:bg-accent"
                title={`Abrir ${a.titulo}`}
              >
                <span className="min-w-0 flex-1 truncate">{a.titulo}</span>
                {a.clase ? (
                  <Badge variant="secondary" className="shrink-0 rounded-full text-[10px]">
                    {a.clase}
                  </Badge>
                ) : null}
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      <EditorPromptOverlay
        docId={editorialAbierto}
        abierto={!!editorialAbierto}
        onCerrar={() => setEditorialAbierto(null)}
      />
    </div>
  );
}
