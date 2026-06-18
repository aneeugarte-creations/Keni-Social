/**
 * ContextoDesarrollo — la pestaña «Desarrollo» de la página Contexto. Lista los documentos de la
 * clase editorial `desarrollo` (los prompts del motor de auto-desarrollo: analyze / plan / build /
 * review / ralph) y deja editarlos con el mismo editor de prompts (overlay), igual que el resto del
 * contexto editorial. No es un pipeline ni un motor con interruptor: es el contexto que gobierna
 * cómo trabajan los agentes de desarrollo, en cajas por documento.
 */
import { useQuery } from "@tanstack/react-query";
import { Code2, FileText } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { EditorPromptOverlay } from "@/components/prompts/EditorPromptOverlay";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import type { DocumentoTexto } from "@/types";

/** Orden canónico del pipeline de desarrollo; los documentos se ordenan por su posición aquí. */
const ORDEN_FASES = ["analyze", "plan", "build", "review", "ralph"];

/** Posición de un documento en el pipeline (por palabra clave en id/título); al final si no casa. */
function ordenDoc(doc: DocumentoTexto): number {
  const heno = `${doc.id} ${doc.titulo}`.toLowerCase();
  const idx = ORDEN_FASES.findIndex((fase) => heno.includes(fase));
  return idx === -1 ? ORDEN_FASES.length : idx;
}

/** Tarjeta clicable de un documento de desarrollo: abre el editor de prompt en overlay. */
function TarjetaDoc({ doc, onAbrir }: { doc: DocumentoTexto; onAbrir: () => void }) {
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onAbrir}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onAbrir();
        }
      }}
      className="cursor-pointer transition-colors hover:border-primary/50"
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <FileText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          {doc.titulo}
        </CardTitle>
        {doc.sin_publicar ? (
          <Badge variant="aviso" className="rounded-full text-[11px]">
            Cambios sin publicar
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <p className="line-clamp-2 text-sm text-muted-foreground">
          {doc.descripcion?.trim() || "Sin descripción."}
        </p>
      </CardContent>
    </Card>
  );
}

/** Pestaña «Desarrollo» del Contexto: los prompts del motor de auto-desarrollo (clase `desarrollo`). */
export function ContextoDesarrollo() {
  const query = useQuery({
    queryKey: ["prompts", { clase: "desarrollo" }],
    queryFn: ({ signal }) => api.prompts({ clase: "desarrollo" }, signal),
  });

  // Documento abierto en el editor (overlay); `null` cuando no hay ninguno.
  const [docAbierto, setDocAbierto] = React.useState<string | null>(null);

  const documentos = React.useMemo(() => {
    const docs = query.data?.documentos ?? [];
    return [...docs].sort((a, b) => ordenDoc(a) - ordenDoc(b) || a.titulo.localeCompare(b.titulo));
  }, [query.data]);

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2">
        <Code2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Los prompts que gobiernan los agentes de auto-desarrollo (análisis, plan, construcción,
          revisión y Ralph). Edítalos como cualquier contexto editorial; los cambios se aplican al
          publicar.
        </p>
      </div>

      {query.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudieron cargar los prompts de desarrollo"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : documentos.length === 0 ? (
        <EstadoVacioTexto
          texto="Aún no hay documentos de desarrollo. Se crean al sembrar la biblioteca de prompts."
          className="py-6"
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {documentos.map((doc) => (
            <TarjetaDoc key={doc.id} doc={doc} onAbrir={() => setDocAbierto(doc.id)} />
          ))}
        </div>
      )}

      <EditorPromptOverlay
        docId={docAbierto}
        abierto={docAbierto !== null}
        onCerrar={() => setDocAbierto(null)}
      />
    </div>
  );
}
