/**
 * Pestaña "Compilado" del editor de documentos: el prompt ENSAMBLADO de un pipeline
 * (lo que verá el modelo) para la marca activa, con sus adjuntos editoriales.
 */
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";

import { LectorProsa } from "@/components/biblioteca/LectorProsa";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";

export function PanelCompilado({ pipelineId }: { pipelineId: string }) {
  const { marcaActiva } = useMarcaActiva();
  const previewQuery = useQuery({
    queryKey: ["texto-preview", pipelineId, marcaActiva],
    queryFn: ({ signal }) =>
      api.previewPipeline(pipelineId, marcaActiva as string, undefined, signal),
    enabled: !!marcaActiva,
  });

  if (!marcaActiva) {
    return (
      <p className="text-sm text-muted-foreground">
        Elige una marca para ver el prompt ensamblado de ese modelo.
      </p>
    );
  }
  if (previewQuery.isPending) return <Skeleton className="h-24 w-full" />;
  if (previewQuery.isError) {
    return <p className="text-sm text-muted-foreground">{mensajeError(previewQuery.error)}</p>;
  }

  const preview = previewQuery.data;
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <FileText className="h-3.5 w-3.5 text-keni" aria-hidden />
        Prompt ensamblado para esta marca
      </p>
      {preview.adjuntos.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {preview.adjuntos.map((a) => (
            <Badge key={a.id} variant="outline" className="rounded-full" title={a.clase}>
              {a.titulo}
            </Badge>
          ))}
        </div>
      ) : null}
      <div className="rounded-md border border-border bg-muted/20 p-3">
        <LectorProsa cuerpo={preview.prompt_efectivo} />
      </div>
    </div>
  );
}
