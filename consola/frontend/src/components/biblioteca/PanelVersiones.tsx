/**
 * Timeline vertical de versiones (git) de un documento de la Biblioteca.
 *
 * Por versión: autor, fecha relativa, mensaje, y badges "● producción" (el sha publicado)
 * y "borrador actual" (HEAD). Dos columnas de radios eligen el par a comparar (antes /
 * después; por defecto producción ↔ actual) y abajo se pinta el `DiffProsa` del par, con
 * toggle "solo cambios". Acciones por versión: Ver (LectorProsa en un diálogo) y
 * Restaurar (POST revertir, no destructivo: se guarda como cambio nuevo).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, History, RotateCcw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { DiffProsa } from "@/components/biblioteca/DiffProsa";
import { LectorProsa } from "@/components/biblioteca/LectorProsa";
import { confirmar } from "@/components/comunes/confirmar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";

export interface PanelVersionesProps {
  docId: string;
  /** SHA publicado (en producción), si lo hay. */
  produccionSha?: string | null;
  /** SHA del borrador actual (HEAD). Si falta, se asume la versión más reciente. */
  shaActual?: string | null;
  /** Avisa al contenedor tras restaurar una versión (refrescar el doc abierto). */
  onRestaurado?: () => void;
  className?: string;
}

export function PanelVersiones({
  docId,
  produccionSha,
  shaActual,
  onRestaurado,
  className,
}: PanelVersionesProps) {
  const qc = useQueryClient();

  const histQuery = useQuery({
    queryKey: ["texto-historial", docId],
    queryFn: ({ signal }) => api.historialTexto(docId, signal),
  });
  const historial = React.useMemo(
    () => histQuery.data?.historial ?? [],
    [histQuery.data],
  );
  // HEAD: lo que diga el backend o, si no llegó, la entrada más reciente del historial.
  const shaCabeza = shaActual ?? historial[0]?.sha ?? null;

  // ── Par a comparar (radios antes/después). Por defecto: producción ↔ actual. ──
  const [antesSha, setAntesSha] = React.useState<string | null>(null);
  const [despuesSha, setDespuesSha] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (historial.length === 0) return;
    const hay = (sha: string | null | undefined) => !!sha && historial.some((v) => v.sha === sha);
    setDespuesSha((prev) => (hay(prev) ? prev : hay(shaCabeza) ? shaCabeza : historial[0].sha));
    setAntesSha((prev) =>
      hay(prev) ? prev : hay(produccionSha) ? (produccionSha as string) : historial[1]?.sha ?? historial[0].sha,
    );
  }, [historial, produccionSha, shaCabeza]);

  const antesQuery = useQuery({
    queryKey: ["texto-version", docId, antesSha],
    queryFn: ({ signal }) => api.versionTexto(docId, antesSha as string, signal),
    enabled: !!antesSha,
  });
  const despuesQuery = useQuery({
    queryKey: ["texto-version", docId, despuesSha],
    queryFn: ({ signal }) => api.versionTexto(docId, despuesSha as string, signal),
    enabled: !!despuesSha,
  });
  const [soloCambios, setSoloCambios] = React.useState(true);

  // ── Ver una versión (lectura renderizada en diálogo). ──
  const [verSha, setVerSha] = React.useState<string | null>(null);
  const verQuery = useQuery({
    queryKey: ["texto-version", docId, verSha],
    queryFn: ({ signal }) => api.versionTexto(docId, verSha as string, signal),
    enabled: !!verSha,
  });

  // ── Restaurar (no destructivo: el rollback se guarda como cambio nuevo). ──
  const revertirMut = useMutation({
    mutationFn: (sha: string) => api.revertirTexto(docId, sha),
    onSuccess: () => {
      toast.success("Versión restaurada como un cambio nuevo.");
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-historial", docId] });
      onRestaurado?.();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const onRestaurar = async (sha: string) => {
    const ok = await confirmar({
      titulo: "Restaurar esta versión",
      mensaje:
        "El documento volverá a esta versión. Se guarda como un cambio nuevo.",
      textoConfirmar: "Restaurar",
    });
    if (ok) revertirMut.mutate(sha);
  };

  if (histQuery.isPending) {
    return (
      <div className={cn("space-y-2", className)}>
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }
  if (historial.length === 0) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        Sin versiones registradas.
      </p>
    );
  }

  return (
    <div className={cn("flex min-h-0 flex-col gap-3", className)}>
      {/* ───────── Timeline ───────── */}
      <div className="overflow-hidden rounded-md border border-border">
        <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground">
          <History className="h-3.5 w-3.5" /> Versiones
          <span className="ml-auto flex gap-3">
            <span>Antes</span>
            <span>Después</span>
          </span>
        </div>
        <ol className="max-h-72 divide-y divide-border overflow-y-auto">
          {historial.map((v) => {
            const esProduccion = !!produccionSha && v.sha === produccionSha;
            const esActual = v.sha === shaCabeza;
            return (
              <li key={v.sha} className="flex items-start gap-2 px-3 py-2 text-sm">
                <span className="mt-1 block h-2 w-2 shrink-0 rounded-full bg-border" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate font-medium">{v.mensaje || v.sha_corto}</span>
                    {esProduccion ? (
                      <Badge variant="ok" className="shrink-0 gap-1 rounded-full px-2">
                        <span aria-hidden>●</span> producción
                      </Badge>
                    ) : null}
                    {esActual ? (
                      <Badge variant="secondary" className="shrink-0 rounded-full px-2">
                        borrador actual
                      </Badge>
                    ) : null}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                    <span>{v.autor}</span>
                    <span title={v.fecha}>{tiempoRelativo(v.fecha) || v.fecha.slice(0, 16).replace("T", " ")}</span>
                    <span className="font-mono">{v.sha_corto}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 px-1.5 text-xs text-muted-foreground"
                      onClick={() => setVerSha(v.sha)}
                    >
                      <Eye className="mr-1 h-3 w-3" /> Ver
                    </Button>
                    {!esActual ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 px-1.5 text-xs text-muted-foreground"
                        disabled={revertirMut.isPending}
                        onClick={() => void onRestaurar(v.sha)}
                      >
                        <RotateCcw className="mr-1 h-3 w-3" /> Restaurar
                      </Button>
                    ) : null}
                  </div>
                </div>
                {/* Radios del par a comparar (antes / después). */}
                <span className="mt-1 flex shrink-0 gap-5 pr-1">
                  <input
                    type="radio"
                    name={`versiones-antes-${docId}`}
                    checked={antesSha === v.sha}
                    onChange={() => setAntesSha(v.sha)}
                    aria-label={`Comparar desde ${v.sha_corto}`}
                    title="Antes"
                    className="h-3.5 w-3.5 accent-foreground"
                  />
                  <input
                    type="radio"
                    name={`versiones-despues-${docId}`}
                    checked={despuesSha === v.sha}
                    onChange={() => setDespuesSha(v.sha)}
                    aria-label={`Comparar hasta ${v.sha_corto}`}
                    title="Después"
                    className="h-3.5 w-3.5 accent-foreground"
                  />
                </span>
              </li>
            );
          })}
        </ol>
      </div>

      {/* ───────── Diff del par elegido ───────── */}
      <div className="flex min-h-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>
            Cambios de <span className="font-mono">{antesSha?.slice(0, 8) ?? "—"}</span> a{" "}
            <span className="font-mono">{despuesSha?.slice(0, 8) ?? "—"}</span>
          </span>
          <label className="ml-auto flex cursor-pointer items-center gap-1.5">
            Solo cambios
            <Switch checked={soloCambios} onCheckedChange={setSoloCambios} />
          </label>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
          {antesQuery.isPending || despuesQuery.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <DiffProsa
              antes={antesQuery.data?.documento.cuerpo ?? ""}
              despues={despuesQuery.data?.documento.cuerpo ?? ""}
              soloCambios={soloCambios}
            />
          )}
        </div>
      </div>

      {/* ───────── Ver una versión (lectura renderizada) ───────── */}
      <Dialog open={!!verSha} onOpenChange={(v) => !v && setVerSha(null)}>
        <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col gap-3 overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Eye className="h-4 w-4" /> Versión {verSha?.slice(0, 8)}
            </DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-4">
            {verQuery.isPending ? (
              <Skeleton className="h-24 w-full" />
            ) : (
              <LectorProsa cuerpo={verQuery.data?.documento.cuerpo ?? ""} />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
