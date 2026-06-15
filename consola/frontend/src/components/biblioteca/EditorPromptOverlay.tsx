import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { DetalleDocumento } from "@/pages/texto/DetalleDocumento";

export function EditorPromptOverlay({
  docId,
  abierto,
  onCerrar,
}: {
  /** Doc de la Biblioteca a editar (p. ej. `prompt/redactar`). `null` cuando no hay nada abierto. */
  docId: string | null;
  abierto: boolean;
  onCerrar: () => void;
}) {
  // El id puede cambiar al renombrar/mover el doc: lo seguimos en local (no hay URL que
  // actualizar como en la página Texto). Se resincroniza al (re)abrir con otro doc.
  const [idActual, setIdActual] = React.useState<string | null>(docId);
  React.useEffect(() => {
    if (abierto) setIdActual(docId);
  }, [abierto, docId]);

  // El flujo de la máquina alimenta la pestaña «Uso» del editor. Misma queryKey que la página
  // Texto: React Query dedupe (cero peticiones extra si ya está en caché).
  const maquinaQuery = useQuery({
    queryKey: ["texto-maquina"],
    queryFn: ({ signal }) => api.maquinaTexto(signal),
    enabled: abierto,
  });

  return (
    <Dialog
      open={abierto && !!idActual}
      onOpenChange={(v) => {
        if (!v) onCerrar();
      }}
    >
      <DialogContent
        aria-describedby={undefined}
        className="flex h-[calc(100dvh-2rem)] max-w-5xl flex-col gap-0 overflow-hidden p-4 sm:p-6"
      >
        {/* El editor ya pinta su propio título editable; el del diálogo es solo accesible. */}
        <DialogTitle className="sr-only">Editar prompt</DialogTitle>
        {idActual ? (
          <div className="min-h-0 flex-1">
            <DetalleDocumento
              key={idActual}
              docId={idActual}
              maquina={maquinaQuery.data}
              onCerrar={onCerrar}
              onIdCambiado={setIdActual}
            />
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
