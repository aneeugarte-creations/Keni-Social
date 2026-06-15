/**
 * Panel de versiones de un documento de la Biblioteca, pensado para un equipo de redes
 * NO técnico.
 *
 * Jerarquía: cuando hay cambios sin publicar, una zona de acciones con un CTA prominente
 * «Revisar y publicar» (abre el flujo de publicación a pantalla completa) y «Descartar
 * cambios». Debajo, la línea de tiempo: una fila «Tu borrador» (lo que se edita ahora) y la
 * lista de PUBLICACIONES, cada una con su nota como título, autor + fecha y la que está EN
 * VIVO marcada. No se muestran SHAs (van en `title`).
 *
 * El diff se LEE en grande: «Ver» abre `VistaRevisarCambios` a pantalla completa comparando
 * ESA versión contra tu borrador (un único punto de diff en toda la app). «Restaurar» trae
 * esa versión al borrador SIN publicar.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Eye, History, Rocket, RotateCcw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { DiffProsa } from "@/components/biblioteca/DiffProsa";
import { VistaRevisarCambios } from "@/components/biblioteca/VistaRevisarCambios";
import { confirmar } from "@/components/comunes/confirmar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
  /** Abre el flujo de publicación a pantalla completa (vive en el contenedor). */
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

  // ── «Ver»: diff a pantalla completa de una versión ↔ tu borrador. ──
  // `verSha` es la versión cuyo cuerpo cargamos como lado «antes»; el «después» es siempre
  // el borrador en edición. Único punto de diff de la app (VistaRevisarCambios).
  const [verSha, setVerSha] = React.useState<string | null>(null);
  const verVersion = historial.find((v) => v.sha === verSha) ?? null;
  const verQuery = useQuery({
    queryKey: ["texto-version", docId, verSha],
    queryFn: ({ signal }) => api.versionTexto(docId, verSha as string, signal),
    enabled: !!verSha,
  });

  // ── Restaurar: trae esa versión al borrador SIN publicar (no crea commit). ──
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
  const onRestaurar = async (sha: string) => {
    const ok = await confirmar({
      titulo: "Restaurar al borrador",
      mensaje:
        "Cargaremos esta versión en tu borrador y se sobrescribirá tu borrador actual sin publicar. No se publica: revísala y publica cuando quieras.",
      textoConfirmar: "Restaurar",
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

  const subtituloVer =
    verSha === produccionSha
      ? "Cambios desde lo publicado hasta tu borrador"
      : "Cambios desde esta versión hasta tu borrador";

  return (
    <div className={cn("flex min-h-0 flex-col gap-4", className)}>
      {/* ───────── Acciones del borrador (CTA prominente) ───────── */}
      {sinPublicar ? (
        <div className="space-y-2 rounded-lg border border-keni/30 bg-keni/5 p-3">
          <p className="text-sm font-medium">Tienes cambios sin publicar</p>
          <p className="text-xs text-muted-foreground">
            Revísalos en grande y publícalos para que los usen los agentes.
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-0.5">
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
        </div>
      ) : null}

      {/* ───────── Línea de tiempo: tu borrador + publicaciones ───────── */}
      <section className="space-y-2">
        <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <History className="h-3.5 w-3.5 text-keni" aria-hidden /> Historial
        </h4>
        <div className="overflow-hidden rounded-md border border-border">
          <ol className="max-h-[28rem] divide-y divide-border overflow-y-auto">
            {/* Fila: tu borrador (lo que se edita ahora). */}
            <li className="flex items-start gap-2.5 px-3 py-2.5">
              <span
                className={cn(
                  "mt-1.5 block h-2 w-2 shrink-0 rounded-full",
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

            {/* Publicaciones (historial), de más reciente a más antigua. */}
            {historial.map((v) => {
              const esEnVivo = !!produccionSha && v.sha === produccionSha;
              return (
                <li
                  key={v.sha}
                  className="group flex items-start gap-2.5 px-3 py-2.5 transition-colors hover:bg-muted/40"
                >
                  <span
                    className={cn(
                      "mt-1.5 block h-2 w-2 shrink-0 rounded-full",
                      esEnVivo ? "bg-emerald-500" : "bg-border",
                    )}
                    aria-hidden
                  />
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
                      <span aria-hidden>·</span>
                      <span title={v.fecha}>
                        {tiempoRelativo(v.fecha) || v.fecha.slice(0, 16).replace("T", " ")}
                      </span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => setVerSha(v.sha)}
                      >
                        <Eye className="mr-1 h-3.5 w-3.5" /> Ver
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        disabled={traerMut.isPending}
                        onClick={() => void onRestaurar(v.sha)}
                      >
                        <RotateCcw className="mr-1 h-3.5 w-3.5" /> Restaurar
                      </Button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>

        {historial.length === 0 ? (
          <p className="px-1 text-sm text-muted-foreground">
            {sinPublicar
              ? "Aún no hay publicaciones: tu borrador será la primera."
              : "Aún no hay publicaciones."}
          </p>
        ) : null}
      </section>

      {/* ───────── Ver: diff a pantalla completa (versión ↔ tu borrador) ───────── */}
      <VistaRevisarCambios
        abierto={!!verSha}
        onCerrar={() => setVerSha(null)}
        titulo={verVersion?.mensaje || "Versión publicada"}
        subtitulo={subtituloVer}
        renderDiff={(soloCambios) =>
          verQuery.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <DiffProsa
              antes={verQuery.data?.documento.cuerpo ?? ""}
              despues={cuerpoBorrador}
              soloCambios={soloCambios}
            />
          )
        }
      />
    </div>
  );
}
