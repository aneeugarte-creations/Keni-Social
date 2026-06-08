/**
 * Historial de versiones (git) de un documento de la Texto: lista de commits y, al elegir
 * uno, su contenido renderizado con opción de restaurarlo (se guarda como cambio nuevo).
 * Extraído del contenedor `pages/Texto.tsx` sin cambio de comportamiento.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { History, RotateCcw } from "lucide-react";
import * as React from "react";

import { confirmar } from "@/components/comunes/confirmar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Markdown } from "@/components/ui/Markdown";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export function DialogHistorial({
  docId,
  open,
  onOpenChange,
  onRevertido,
}: {
  docId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onRevertido: () => void;
}) {
  const [verSha, setVerSha] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!open) setVerSha(null);
  }, [open]);

  const histQuery = useQuery({
    queryKey: ["texto-historial", docId],
    queryFn: ({ signal }) => api.historialTexto(docId, signal),
    enabled: open,
  });
  const versionQuery = useQuery({
    queryKey: ["texto-version", docId, verSha],
    queryFn: ({ signal }) => api.versionTexto(docId, verSha as string, signal),
    enabled: open && !!verSha,
  });
  const revertirMut = useMutation({
    mutationFn: (sha: string) => api.revertirTexto(docId, sha),
    onSuccess: onRevertido,
  });

  const historial = histQuery.data?.historial ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] max-w-3xl flex-col gap-3 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="h-4 w-4" /> Historial de versiones
          </DialogTitle>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 gap-3">
          <div className="w-64 shrink-0 overflow-y-auto rounded-md border border-border">
            {histQuery.isPending ? (
              <div className="p-3"><Skeleton className="h-8 w-full" /></div>
            ) : historial.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">
                Sin versiones registradas. (El versionado git puede estar desactivado.)
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {historial.map((v) => (
                  <li key={v.sha}>
                    <button
                      onClick={() => setVerSha(v.sha)}
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-muted ${
                        v.sha === verSha ? "bg-muted" : ""
                      }`}
                    >
                      <span className="block font-medium">{v.mensaje}</span>
                      <span className="mt-0.5 block text-muted-foreground">
                        {v.autor} · {v.fecha.slice(0, 16).replace("T", " ")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-2">
            {!verSha ? (
              <p className="text-sm text-muted-foreground">
                Elige una versión para verla y, si quieres, restaurarla.
              </p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Versión {verSha.slice(0, 8)}</span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="ml-auto"
                    disabled={revertirMut.isPending}
                    onClick={async () => {
                      if (
                        await confirmar({
                          mensaje: "¿Restaurar esta versión? Se guarda como un cambio nuevo (no se pierde el historial).",
                          textoConfirmar: "Restaurar",
                        })
                      )
                        revertirMut.mutate(verSha);
                    }}
                  >
                    <RotateCcw className="mr-1 h-3.5 w-3.5" /> Restaurar
                  </Button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
                  {versionQuery.isPending ? (
                    <Skeleton className="h-24 w-full" />
                  ) : (
                    <Markdown>{versionQuery.data?.documento.cuerpo || "_Sin contenido_"}</Markdown>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
