/**
 * Panel de versiones de un documento de la Prompts, pensado para un equipo de redes
 * NO técnico.
 *
 * Jerarquía: cuando hay cambios sin publicar, una zona de acciones con un CTA prominente
 * «Revisar y publicar» (abre el flujo de publicación a pantalla completa) y «Descartar
 * cambios». Debajo, la línea de tiempo: la lista de PIEZAS, cada una con su nota como
 * título, autor + fecha y la que está EN VIVO marcada. No se muestran SHAs (van en `title`).
 *
 * Interacción por versión:
 *  - Clic en la fila → carga ESA versión en la caja de texto de la derecha (preview en SOLO
 *    LECTURA, vía `onVerVersion`); el contenedor pinta el lector y la forma de volver al borrador.
 *    No se abre ningún popup.
 *  - «Restaurar» → revierte en un clic: esa versión vuelve a estar EN VIVO al instante (admin)
 *    o se envía la solicitud (editor), con una nota automática «Restauración de «X»». No hay
 *    paso de publicar a mano.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, FileText, Rocket, RotateCcw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
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
  /** Hay cambios en el borrador todavía sin publicar. */
  sinPublicar?: boolean;
  /** El usuario puede publicar directo (admin); si no, restaurar envía una solicitud. */
  esAdmin?: boolean;
  /** Abre el flujo de publicación a pantalla completa (vive en el contenedor). */
  onPublicar?: () => void;
  /** Avisa al contenedor tras restaurar o descartar (resincronizar el doc abierto). */
  onBorradorActualizado?: () => void;
  /** Pide al contenedor que cargue ESA versión en la caja de texto de la derecha (preview en
   *  solo lectura); `null` = volver al borrador actual. Sin él, la fila no es seleccionable. */
  onVerVersion?: (sha: string | null) => void;
  /** SHA de la versión que el contenedor está previsualizando (resalta su fila). `null`/ausente
   *  = se está editando el borrador (resalta «Tu borrador»). */
  versionActiva?: string | null;
  /** Modo RAÍL: en vez de la lista completa, una columna estrecha con un icono de documento por
   *  versión (el EN VIVO en verde), clicable/navegable igual que la fila. Lo usa el contenedor al
   *  colapsar el panel: colapsar NO oculta, deja este raíl. */
  colapsado?: boolean;
  className?: string;
}

export function PanelVersiones({
  docId,
  produccionSha,
  sinPublicar = false,
  esAdmin = false,
  onPublicar,
  onBorradorActualizado,
  onVerVersion,
  versionActiva,
  colapsado = false,
  className,
}: PanelVersionesProps) {
  const qc = useQueryClient();

  const histQuery = useQuery({
    queryKey: ["prompts-historial", docId],
    queryFn: ({ signal }) => api.historialPrompts(docId, signal),
  });
  const historial = React.useMemo(
    () => histQuery.data?.historial ?? [],
    [histQuery.data],
  );

  // Ver una versión: NO abre popup; pide al contenedor cargarla en la caja de texto de la derecha.
  const seleccionable = typeof onVerVersion === "function";
  // Clicar la versión EN VIVO equivale a «volver al documento actual»: si esa versión ya ES lo que
  // edita el borrador (no hay cambios sin publicar), no tiene sentido un preview read-only de lo
  // mismo. Mandamos `null` para que el editor quede EDITABLE y sin banner. Una versión EN VIVO con
  // cambios sin publicar SÍ difiere del borrador, así que se previsualiza como cualquier otra.
  const esVivoSinCambios = (sha: string) =>
    !sinPublicar && !!produccionSha && sha === produccionSha;
  const verVersion = (sha: string | null) =>
    onVerVersion?.(sha != null && esVivoSinCambios(sha) ? null : sha);

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["prompts"] });
    qc.invalidateQueries({ queryKey: ["prompts-historial", docId] });
    onBorradorActualizado?.();
  };

  // ── Restaurar: revierte en un clic (vuelve EN VIVO admin / solicita editor). ──
  // Carga esa versión en el working copy y la fija como producción (nota automática). Sin
  // paso de publicar a mano; lo que ven los agentes cambia al instante (para un admin).
  const restaurarMut = useMutation({
    mutationFn: async ({ sha, nombre }: { sha: string; nombre: string }) => {
      await api.revertirPrompts(docId, sha);
      const nota = `Restauración de «${nombre}»`;
      if (esAdmin) await api.publicarPrompts(docId, { nota });
      else await api.solicitarPublicacionPrompts(docId, { nota });
    },
    onSuccess: (_d, { nombre }) => {
      toast.success(
        esAdmin
          ? `Restaurado: «${nombre}» vuelve a estar EN VIVO.`
          : `Solicitud enviada para restaurar «${nombre}».`,
      );
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const onRestaurar = async (sha: string, nombre: string) => {
    const ok = await confirmar({
      titulo: `Restaurar «${nombre}»`,
      mensaje: esAdmin
        ? "Esta versión volverá a estar EN VIVO ahora mismo: es lo que verán los agentes en todas las generaciones."
        : "Se enviará una solicitud para volver a esta versión. Un admin debe aprobarla antes de que vuelva a estar EN VIVO.",
      textoConfirmar: esAdmin ? "Restaurar y publicar" : "Solicitar restauración",
    });
    if (ok) restaurarMut.mutate({ sha, nombre });
  };

  // ── Descartar cambios: el borrador vuelve a lo publicado. ──
  const descartarMut = useMutation({
    mutationFn: () => api.descartarPrompts(docId),
    onSuccess: () => {
      toast.success("Borrador descartado: vuelve a la versión publicada.");
      invalidar();
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
        <Skeleton className={colapsado ? "h-8 w-8" : "h-10 w-full"} />
        <Skeleton className={colapsado ? "h-8 w-8" : "h-10 w-full"} />
      </div>
    );
  }

  // ── Modo RAÍL (panel colapsado): solo iconos de documento, uno por versión, el EN VIVO en
  //    verde. Sigue clicable/navegable: clicar carga esa versión en el editor (como la fila). ──
  if (colapsado) {
    return (
      <div className={cn("flex flex-col items-center gap-1", className)}>
        {sinPublicar ? (
          <button
            type="button"
            onClick={seleccionable ? () => verVersion(null) : undefined}
            disabled={!seleccionable}
            title="Tu borrador (cambios sin publicar)"
            aria-label="Tu borrador"
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-md",
              seleccionable && "hover:bg-accent",
              versionActiva == null && "bg-accent",
            )}
          >
            <FileText className="h-4 w-4 text-keni" />
          </button>
        ) : null}
        {historial.map((v) => {
          const esEnVivo = !!produccionSha && v.sha === produccionSha;
          // Sin cambios sin publicar, el borrador ES la versión EN VIVO: resáltala cuando no se
          // previsualiza nada (`versionActiva == null`), igual que «Tu borrador» cuando los hay.
          const activa = versionActiva === v.sha || (versionActiva == null && esVivoSinCambios(v.sha));
          const nombre = v.mensaje || "Publicación";
          return (
            <button
              key={v.sha}
              type="button"
              onClick={seleccionable ? () => verVersion(v.sha) : undefined}
              disabled={!seleccionable}
              title={`${nombre} · ${v.autor} · ${tiempoRelativo(v.fecha) || v.fecha.slice(0, 10)}${esEnVivo ? " · en vivo" : ""}`}
              aria-label={`${nombre}${esEnVivo ? " (en vivo)" : ""}`}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-md",
                seleccionable && "hover:bg-accent",
                activa && "bg-accent",
              )}
            >
              <FileText
                className={cn(
                  "h-4 w-4",
                  esEnVivo ? "text-emerald-500" : "text-muted-foreground",
                )}
              />
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className={cn("flex min-h-0 flex-col gap-4", className)}>
      {/* ───────── Acciones del borrador (CTA prominente, solo si hay cambios) ───────── */}
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

      {/* ───────── Línea de tiempo: piezas ─────────
          Sin caja propia (la sección ya es «Versiones»): cada versión en UNA sola línea, con el
          nombre truncado y la meta + restaurar a la derecha. */}
      <section className="space-y-2">
        <ol className="max-h-[28rem] divide-y divide-border overflow-y-auto">
          {/* Fila «Tu borrador»: SOLO cuando hay cambios sin publicar (si no, sobra). Clicarla
              vuelve a editar el borrador (sale del preview de una versión). */}
          {sinPublicar ? (
            <li>
              <button
                type="button"
                onClick={seleccionable ? () => verVersion(null) : undefined}
                disabled={!seleccionable}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md py-2 pl-1 pr-2 text-left whitespace-nowrap",
                  seleccionable && "hover:bg-accent",
                  seleccionable && versionActiva == null && "bg-accent",
                )}
              >
                <span className="block h-2 w-2 shrink-0 rounded-full bg-keni" aria-hidden />
                <span className="min-w-0 flex-1 truncate font-medium">Tu borrador</span>
                <Badge variant="aviso" className="shrink-0 rounded-full px-2">
                  Cambios sin publicar
                </Badge>
              </button>
            </li>
          ) : null}

          {/* Piezas (historial), de más reciente a más antigua. */}
          {historial.map((v) => {
            const esEnVivo = !!produccionSha && v.sha === produccionSha;
            const nombre = v.mensaje || "Publicación";
            // Restaurar: no tiene sentido sobre la versión que ya está EN VIVO.
            // `onRestaurar` ya confirma internamente; no añadimos otro diálogo.
            const accionesVersion: EntradaMenuContextual[] = esEnVivo
              ? []
              : [
                  {
                    etiqueta: "Restaurar",
                    icono: RotateCcw,
                    deshabilitado: restaurarMut.isPending,
                    onClick: () => void onRestaurar(v.sha, nombre),
                  },
                ];
            const activa =
              versionActiva === v.sha || (versionActiva == null && esVivoSinCambios(v.sha));
            return (
              <FilaConAcciones
                key={v.sha}
                como="li"
                onPrimaria={seleccionable ? () => verVersion(v.sha) : undefined}
                acciones={accionesVersion}
                kebab="hover"
                className={cn(
                  "group flex items-center gap-2 rounded-md py-2 pl-1 pr-2 whitespace-nowrap",
                  seleccionable && "hover:bg-accent",
                  activa && "bg-accent",
                )}
              >
                {/* El punto verde (●) marca la versión EN VIVO; ya no hace falta el texto. */}
                <span
                  className={cn(
                    "block h-2 w-2 shrink-0 rounded-full",
                    esEnVivo ? "bg-emerald-500" : "bg-border",
                  )}
                  aria-label={esEnVivo ? "En vivo" : undefined}
                />
                <span className="min-w-0 flex-1 truncate font-medium" title={v.sha_corto}>
                  {nombre}
                </span>
                <span
                  className="shrink-0 text-xs tabular-nums text-muted-foreground"
                  title={`${v.autor} · ${v.fecha}`}
                >
                  {tiempoRelativo(v.fecha) || v.fecha.slice(0, 10)}
                </span>
              </FilaConAcciones>
            );
          })}
        </ol>

        {historial.length === 0 ? (
          <p className="px-1 text-sm text-muted-foreground">
            {sinPublicar
              ? "Aún no hay piezas: tu borrador será la primera."
              : "Aún no hay piezas."}
          </p>
        ) : null}
      </section>
    </div>
  );
}
