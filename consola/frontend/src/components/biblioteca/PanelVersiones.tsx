/**
 * Panel de versiones de un documento de la Biblioteca, pensado para un equipo de redes
 * NO técnico.
 *
 * La comparación por defecto es SIEMPRE «lo Publicado ↔ Tu borrador» (el caso del 90%).
 * Arriba, una fila sintética «Tu borrador» (lo que se está editando ahora); debajo, la
 * lista de PUBLICACIONES (historial), cada una con su nota como título, autor + fecha, y
 * la que está EN VIVO marcada. No se muestran SHAs (van en `title`). El diff NO vive
 * embutido en la columna: se LEE en grande en el diálogo «Revisar cambios».
 *
 * Acciones: «Revisar y publicar» y «Descartar cambios» cuando hay borrador sin publicar;
 * por publicación, «Ver» (lector) y «Traer al borrador» (carga esa versión en el borrador
 * SIN publicar).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Eye, FileText, Rocket, RotateCcw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { DiffProsa } from "@/components/biblioteca/DiffProsa";
import { LectorProsa } from "@/components/biblioteca/LectorProsa";
import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
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
  /** SHA publicado (lo que está EN VIVO), si lo hay. */
  produccionSha?: string | null;
  /** Cuerpo (markdown) del borrador en edición: lado derecho del diff («Tu borrador»). */
  cuerpoBorrador: string;
  /** Hay cambios en el borrador todavía sin publicar. */
  sinPublicar?: boolean;
  /** Abre el flujo de publicación (vive en el contenedor). */
  onPublicar?: () => void;
  /** Avisa al contenedor tras traer al borrador o descartar (resincronizar el doc abierto). */
  onBorradorActualizado?: () => void;
  className?: string;
}

export function PanelVersiones({
  docId,
  produccionSha,
  cuerpoBorrador,
  sinPublicar = false,
  onPublicar,
  onBorradorActualizado,
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

  // ── Versión publicada elegida en el selector del sidebar (lado izquierdo del diff).
  //    Por defecto: la que está EN VIVO. Es solo la preferencia del selector. ──
  const [comparaSha, setComparaSha] = React.useState<string | null>(null);
  React.useEffect(() => {
    const hay = (sha?: string | null) => !!sha && historial.some((v) => v.sha === sha);
    setComparaSha((prev) =>
      hay(prev) ? prev : hay(produccionSha) ? (produccionSha as string) : historial[0]?.sha ?? null,
    );
  }, [historial, produccionSha]);

  // ── Diff «Revisar cambios» en diálogo ancho: versión elegida ↔ tu borrador.
  //    `diffSha` es el sha que se está mostrando AHORA en el diálogo: vive aparte de
  //    `comparaSha` para que abrir el diff de una fila no cambie el selector del sidebar. ──
  const [diffAbierto, setDiffAbierto] = React.useState(false);
  const [diffSha, setDiffSha] = React.useState<string | null>(null);
  const [soloCambios, setSoloCambios] = React.useState(true);
  const comparaQuery = useQuery({
    queryKey: ["texto-version", docId, diffSha],
    queryFn: ({ signal }) => api.versionTexto(docId, diffSha as string, signal),
    enabled: !!diffSha,
  });
  const abrirDiff = (sha: string | null) => {
    setDiffSha(sha);
    setSoloCambios(true);
    setDiffAbierto(true);
  };

  // ── Ver una versión publicada (lectura renderizada en diálogo). ──
  const [verSha, setVerSha] = React.useState<string | null>(null);
  const verVersion = historial.find((v) => v.sha === verSha) ?? null;
  const verQuery = useQuery({
    queryKey: ["texto-version", docId, verSha],
    queryFn: ({ signal }) => api.versionTexto(docId, verSha as string, signal),
    enabled: !!verSha,
  });

  // ── Traer al borrador: carga esa versión en el borrador SIN publicar (no crea commit). ──
  const traerMut = useMutation({
    mutationFn: (sha: string) => api.revertirTexto(docId, sha),
    onSuccess: () => {
      toast.success("Versión traída al borrador. Revísala y publica cuando quieras.");
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-historial", docId] });
      onBorradorActualizado?.();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const onTraer = async (sha: string) => {
    const ok = await confirmar({
      titulo: "Traer al borrador",
      mensaje:
        "Cargaremos esta versión en tu borrador y se sobrescribirá tu borrador actual sin publicar. No se publica: revísala y publica cuando quieras.",
      textoConfirmar: "Traer al borrador",
    });
    if (ok) traerMut.mutate(sha);
  };

  // ── Descartar cambios: el borrador vuelve a lo publicado. ──
  const descartarMut = useMutation({
    mutationFn: () => api.descartarTexto(docId),
    onSuccess: () => {
      toast.success("Borrador descartado: vuelve a la versión publicada.");
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-historial", docId] });
      onBorradorActualizado?.();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const onDescartar = async () => {
    const ok = await confirmar({
      titulo: "Descartar cambios",
      mensaje:
        "Tu borrador volverá a la versión publicada. Perderás los cambios no publicados.",
      destructivo: true,
      textoConfirmar: "Descartar cambios",
    });
    if (ok) descartarMut.mutate();
  };

  if (histQuery.isPending) {
    return (
      <div className={cn("space-y-2", className)}>
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  const antesDiff = diffSha ? comparaQuery.data?.documento.cuerpo ?? "" : "";
  const etiquetaDiff = !diffSha
    ? "Todo es nuevo: aún no hay nada publicado."
    : diffSha === produccionSha
      ? "Cambios desde lo publicado hasta tu borrador"
      : "Cambios desde esta versión hasta tu borrador";

  return (
    <div className={cn("flex min-h-0 flex-col gap-3", className)}>
      {/* ───────── Acciones del borrador ───────── */}
      {sinPublicar ? (
        <div className="flex flex-wrap items-center gap-2">
          {onPublicar ? (
            <Button variant="brand" size="sm" onClick={onPublicar}>
              <Rocket className="mr-1 h-3.5 w-3.5" /> Revisar y publicar
              <ArrowRight className="ml-1 h-3.5 w-3.5" />
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            disabled={descartarMut.isPending}
            onClick={() => void onDescartar()}
          >
            <RotateCcw className="mr-1 h-3.5 w-3.5" /> Descartar cambios
          </Button>
        </div>
      ) : null}

      {/* ───────── Comparador: dirección fija «tu borrador ↔ versión elegida» ─────────
          La comparación SIEMPRE enfrenta tu borrador (lado derecho) contra una versión
          publicada (lado izquierdo, este selector). No se ofrece comparar dos versiones
          publicadas entre sí: el lado derecho está clavado al borrador en edición y el
          90% de los casos es «¿qué he cambiado respecto a lo publicado?». */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="flex items-center gap-1.5 text-muted-foreground">
          Comparar <span className="font-medium text-foreground">tu borrador</span> con:
          <select
            value={comparaSha ?? ""}
            onChange={(e) => setComparaSha(e.target.value || null)}
            className="h-7 rounded-md border border-input bg-background px-2 text-xs text-foreground"
            aria-label="Versión publicada a comparar con tu borrador"
          >
            {!produccionSha ? <option value="">Nada publicado aún</option> : null}
            {historial.map((v) => (
              <option key={v.sha} value={v.sha}>
                {v.sha === produccionSha ? "Publicado (en vivo)" : v.mensaje || "Publicación"}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          disabled={!sinPublicar}
          title={!sinPublicar ? "No hay cambios sin publicar" : undefined}
          onClick={() => abrirDiff(comparaSha)}
        >
          <Eye className="mr-1 h-3.5 w-3.5" /> Ver qué cambió
        </Button>
      </div>

      {/* ───────── Lista: tu borrador + publicaciones ───────── */}
      <div className="overflow-hidden rounded-md border border-border">
        <ol className="max-h-80 divide-y divide-border overflow-y-auto">
          {/* Fila sintética: tu borrador (lo que se edita ahora). */}
          <li className="flex items-start gap-2 px-3 py-2">
            <span
              className={cn(
                "mt-1 block h-2 w-2 shrink-0 rounded-full",
                sinPublicar ? "bg-keni" : "bg-border",
              )}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">Tu borrador</span>
                {sinPublicar ? (
                  <Badge variant="aviso" className="shrink-0 rounded-full px-2">
                    Cambios sin publicar
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="shrink-0 rounded-full px-2">
                    Al día
                  </Badge>
                )}
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {sinPublicar
                  ? "Lo que estás editando ahora, todavía sin publicar."
                  : "Igual que lo publicado."}
              </p>
            </div>
          </li>

          {/* Publicaciones (historial). Las acciones por fila son botones VISIBLES
              («Abrir versión», «Restaurar»); el cuerpo de la fila abre el diff. */}
          {historial.map((v) => {
            const esEnVivo = !!produccionSha && v.sha === produccionSha;
            return (
              <FilaConAcciones
                key={v.sha}
                como="li"
                realce
                className="flex items-start gap-2 py-2 pl-3 pr-3"
                onPrimaria={() => abrirDiff(v.sha)}
                acciones={[]}
              >
                <span className="mt-1 block h-2 w-2 shrink-0 rounded-full bg-border" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate font-medium" title={v.sha_corto}>
                      {v.mensaje || "Publicación"}
                    </span>
                    {esEnVivo ? (
                      <Badge variant="ok" className="shrink-0 gap-1 rounded-full px-2">
                        <Check className="h-3 w-3" aria-hidden /> EN VIVO
                      </Badge>
                    ) : null}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                    <span>{v.autor}</span>
                    <span title={v.fecha}>
                      {tiempoRelativo(v.fecha) || v.fecha.slice(0, 16).replace("T", " ")}
                    </span>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => setVerSha(v.sha)}
                  >
                    <FileText className="mr-1 h-3.5 w-3.5" /> Abrir versión
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    disabled={traerMut.isPending}
                    onClick={() => void onTraer(v.sha)}
                  >
                    <RotateCcw className="mr-1 h-3.5 w-3.5" /> Restaurar
                  </Button>
                </div>
              </FilaConAcciones>
            );
          })}
        </ol>
      </div>

      {historial.length === 0 && !sinPublicar ? (
        <p className="text-sm text-muted-foreground">Aún no hay publicaciones.</p>
      ) : null}

      {/* ───────── Revisar cambios (diff ancho) ───────── */}
      <Dialog open={diffAbierto} onOpenChange={(v) => !v && setDiffAbierto(false)}>
        <DialogContent className="flex max-h-[85vh] max-w-4xl flex-col gap-3 overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Eye className="h-4 w-4" /> Revisar cambios
            </DialogTitle>
          </DialogHeader>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{etiquetaDiff}</span>
            <label className="flex cursor-pointer items-center gap-1.5">
              Solo cambios
              <Switch checked={soloCambios} onCheckedChange={setSoloCambios} />
            </label>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-4">
            {comparaSha && comparaQuery.isPending ? (
              <Skeleton className="h-24 w-full" />
            ) : (
              <DiffProsa antes={antesDiff} despues={cuerpoBorrador} soloCambios={soloCambios} />
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* ───────── Ver una versión publicada (lectura renderizada) ───────── */}
      <Dialog open={!!verSha} onOpenChange={(v) => !v && setVerSha(null)}>
        <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col gap-3 overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-4 w-4" /> {verVersion?.mensaje || "Versión publicada"}
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
