/**
 * BibliotecaDocumentos — la gestión MASIVA de documentos (búsqueda/filtros + papelera), accesible
 * desde el «⋮ → Todos los documentos» de la página Contexto. Antes era la pestaña «Documentos» de
 * la página Texto (retirada): aquí se conserva como un diálogo, sin página propia. La tabla maneja
 * por dentro la papelera y el borrado; abrir un documento usa el editor en overlay.
 */
import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { TablaDocumentos } from "@/pages/texto/TablaDocumentos";

export function BibliotecaDocumentos({
  abierto,
  onCerrar,
}: {
  abierto: boolean;
  onCerrar: () => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const [soloSinPublicar, setSoloSinPublicar] = React.useState(false);
  const [docAbierto, setDocAbierto] = React.useState<string | null>(null);

  const docsQuery = useQuery({
    queryKey: ["texto", "lista", marcaActiva],
    queryFn: ({ signal }) => api.texto({ marca: marcaActiva ?? undefined }, signal),
    enabled: abierto,
  });
  const documentos = docsQuery.data?.documentos ?? [];

  return (
    <>
      <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
        <DialogContent className="flex max-h-[85vh] max-w-5xl flex-col gap-3 overflow-hidden">
          <DialogHeader>
            <DialogTitle>Todos los documentos</DialogTitle>
          </DialogHeader>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <TablaDocumentos
              documentos={documentos}
              cargando={docsQuery.isPending}
              soloSinPublicar={soloSinPublicar}
              onCambioSinPublicar={setSoloSinPublicar}
              onAbrir={setDocAbierto}
            />
          </div>
        </DialogContent>
      </Dialog>

      <EditorPromptOverlay
        docId={docAbierto}
        abierto={docAbierto !== null}
        onCerrar={() => setDocAbierto(null)}
      />
    </>
  );
}
