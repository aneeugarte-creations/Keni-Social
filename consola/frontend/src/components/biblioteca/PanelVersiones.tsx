/**
 * Panel de versiones de un documento de la Biblioteca, pensado para un equipo de redes
 * NO técnico.
 *
 * Jerarquía: cuando hay cambios sin publicar, una zona de acciones con un CTA prominente
 * «Revisar y publicar» (abre el flujo de publicación a pantalla completa) y «Descartar
 * cambios». Debajo, la línea de tiempo: la lista de PUBLICACIONES, cada una con su nota como
 * título, autor + fecha y la que está EN VIVO marcada. No se muestran SHAs (van en `title`).
 *
 * Interacción por versión:
 *  - Clic en la fila → abre ESA versión a pantalla completa, en SOLO LECTURA (LectorProsa).
 *  - «Restaurar» → revierte en un clic: esa versión vuelve a estar EN VIVO al instante (admin)
 *    o se envía la solicitud (editor), con una nota automática «Restauración de «X»». No hay
 *    paso de publicar a mano.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, FileText, Rocket, RotateCcw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { DiffProsa } from "@/components/biblioteca/DiffProsa";
import { LectorProsa } from "@/components/biblioteca/LectorProsa";
import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
  /** Hay cambios en el borrador todavía sin publicar. */
  sinPublicar?: boolean;
  /** Cuerpo (markdown) del borrador en edición: para comparar una versión con «Tu borrador». */
  cuerpoBorrador?: string;
  /** El usuario puede publicar directo (admin); si no, restaurar envía una solicitud. */
  esAdmin?: boolean;
  /** Abre el flujo de publicación a pantalla completa (vive en el contenedor). */
  onPublicar?: () => void;
  /** Avisa al contenedor tras restaurar o descartar (resincronizar el doc abierto). */
  onBorradorActualizado?: () => void;
  className?: string;
}

export function PanelVersiones({
  docId,
  produccionSha,
  sinPublicar = false,
  cuerpoBorrador,
  esAdmin = false,
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

  // ── Ver una versión: su contenido a pantalla completa, en SOLO LECTURA. ──
  const [verSha, setVerSha] = React.useState<string | null>(null);
  const verVersion = historial.find((v) => v.sha === verSha) ?? null;
  const verQuery = useQuery({
    queryKey: ["texto-version", docId, verSha],
    queryFn: ({ signal }) => api.versionTexto(docId, verSha as string, signal),
    enabled: !!verSha,
  });

  // ── Comparar: dentro del visor, contra «Tu borrador», EN VIVO u otra versión. ──
  // `comparaCon`: "" = solo ver contenido · "borrador" = el borrador en edición · un sha.
  const [comparaCon, setComparaCon] = React.useState<string>("");
  const [soloCambios, setSoloCambios] = React.useState(true);
  const abrirVersion = (sha: string) => {
    setComparaCon("");
    setSoloCambios(true);
    setVerSha(sha);
  };
  const comparandoSha = comparaCon && comparaCon !== "borrador" ? comparaCon : null;
  const objetivoQuery = useQuery({
    queryKey: ["texto-version", docId, comparandoSha],
    queryFn: ({ signal }) => api.versionTexto(docId, comparandoSha as string, signal),
    enabled: !!comparandoSha,
  });
  const objetivoVersion = historial.find((v) => v.sha === comparaCon) ?? null;
  const objetivoLabel =
    comparaCon === "borrador"
      ? "Tu borrador"
      : objetivoVersion
        ? objetivoVersion.mensaje || "Publicación"
        : "";
  const cuerpoObjetivo =
    comparaCon === "borrador"
      ? cuerpoBorrador ?? ""
      : objetivoQuery.data?.documento.cuerpo ?? "";
  const cargandoComparacion =
    !!comparandoSha && objetivoQuery.isPending;

  // El diff se lee CRONOLÓGICAMENTE: el lado más ANTIGUO es «antes» y el más nuevo «después»,
  // así borrar una línea sale en ROJO y añadir en VERDE, sin importar cuál de las dos abriste.
  // («Tu borrador» es siempre lo más reciente.) Las fechas son ISO: comparan como string.
  const aperturaLabel = verVersion?.mensaje || "esta versión";
  const aperturaCuerpo = verQuery.data?.documento.cuerpo ?? "";
  const fechaApertura = verVersion?.fecha ?? "";
  const fechaObjetivo =
    comparaCon === "borrador" ? "9999-12-31T23:59:59" : objetivoVersion?.fecha ?? "";
  const aperturaEsAntes = fechaApertura <= fechaObjetivo;
  const diffAntes = aperturaEsAntes ? aperturaCuerpo : cuerpoObjetivo;
  const diffDespues = aperturaEsAntes ? cuerpoObjetivo : aperturaCuerpo;
  const labelAntes = aperturaEsAntes ? aperturaLabel : objetivoLabel;
  const labelDespues = aperturaEsAntes ? objetivoLabel : aperturaLabel;
  // Opciones de comparación: el borrador (si lo tenemos) + el resto de versiones.
  const opcionesCompara = [
    ...(cuerpoBorrador !== undefined ? [{ value: "borrador", label: "Tu borrador" }] : []),
    ...historial
      .filter((v) => v.sha !== verSha)
      .map((v) => ({
        value: v.sha,
        label: `${v.mensaje || "Publicación"}${v.sha === produccionSha ? " (EN VIVO)" : ""}`,
      })),
  ];

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["texto"] });
    qc.invalidateQueries({ queryKey: ["texto-historial", docId] });
    onBorradorActualizado?.();
  };

  // ── Restaurar: revierte en un clic (vuelve EN VIVO admin / solicita editor). ──
  // Carga esa versión en el working copy y la fija como producción (nota automática). Sin
  // paso de publicar a mano; lo que ven los agentes cambia al instante (para un admin).
  const restaurarMut = useMutation({
    mutationFn: async ({ sha, nombre }: { sha: string; nombre: string }) => {
      await api.revertirTexto(docId, sha);
      const nota = `Restauración de «${nombre}»`;
      if (esAdmin) await api.publicarTexto(docId, { nota });
      else await api.solicitarPublicacionTexto(docId, { nota });
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
    mutationFn: () => api.descartarTexto(docId),
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
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
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

      {/* ───────── Línea de tiempo: publicaciones ─────────
          Sin caja propia (la sección ya es «Versiones»): cada versión en UNA sola línea, con el
          nombre truncado y la meta + restaurar a la derecha. */}
      <section className="space-y-2">
        <ol className="max-h-[28rem] divide-y divide-border overflow-y-auto">
          {/* Fila «Tu borrador»: SOLO cuando hay cambios sin publicar (si no, sobra). */}
          {sinPublicar ? (
            <li className="flex items-center gap-2 py-2 whitespace-nowrap">
              <span className="block h-2 w-2 shrink-0 rounded-full bg-keni" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-medium">Tu borrador</span>
              <Badge variant="aviso" className="shrink-0 rounded-full px-2">
                Cambios sin publicar
              </Badge>
            </li>
          ) : null}

          {/* Publicaciones (historial), de más reciente a más antigua. */}
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
            return (
              <FilaConAcciones
                key={v.sha}
                como="li"
                onPrimaria={() => abrirVersion(v.sha)}
                acciones={accionesVersion}
                kebab="hover"
                className="group flex items-center gap-2 py-2 whitespace-nowrap"
              >
                <span
                  className={cn(
                    "block h-2 w-2 shrink-0 rounded-full",
                    esEnVivo ? "bg-emerald-500" : "bg-border",
                  )}
                  aria-hidden
                />
                {/* Contenido: nombre + badge EN VIVO (la fila abre esa versión al clicar). */}
                <span className="flex min-w-0 flex-1 items-center gap-1.5" title={v.sha_corto}>
                  <span className="truncate font-medium">{nombre}</span>
                  {esEnVivo ? (
                    <Badge variant="ok" className="shrink-0 gap-1 rounded-full px-2">
                      <Check className="h-3 w-3" aria-hidden /> EN VIVO
                    </Badge>
                  ) : null}
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
              ? "Aún no hay publicaciones: tu borrador será la primera."
              : "Aún no hay publicaciones."}
          </p>
        ) : null}
      </section>

      {/* ───────── Ver/comparar una versión: a pantalla completa ───────── */}
      <Dialog open={!!verSha} onOpenChange={(o) => !o && setVerSha(null)}>
        <DialogContent className="flex h-screen w-screen max-w-none flex-col gap-0 rounded-none p-0">
          <DialogHeader className="space-y-2 border-b border-border px-4 py-3 text-left sm:text-left">
            <DialogTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-keni" aria-hidden />
              {verVersion?.mensaje || "Versión publicada"}
              {verSha && verSha === produccionSha ? (
                <Badge variant="ok" className="gap-1 rounded-full px-2">
                  <Check className="h-3 w-3" aria-hidden /> EN VIVO
                </Badge>
              ) : null}
            </DialogTitle>
            <DialogDescription>
              {comparaCon
                ? `Cambios desde «${labelAntes}» hasta «${labelDespues}»`
                : verVersion
                  ? `${verVersion.autor} · ${
                      tiempoRelativo(verVersion.fecha) ||
                      verVersion.fecha.slice(0, 16).replace("T", " ")
                    }`
                  : "Versión publicada del documento."}
            </DialogDescription>
            {/* Barra de comparación: contra el borrador, EN VIVO u otra versión. */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-0.5 text-xs">
              <label className="flex items-center gap-1.5">
                <span className="text-muted-foreground">Comparar con</span>
                <select
                  value={comparaCon}
                  onChange={(e) => setComparaCon(e.target.value)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">— Solo ver el contenido</option>
                  {opcionesCompara.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              {comparaCon ? (
                <label className="flex cursor-pointer items-center gap-1.5">
                  <span className="text-muted-foreground">Solo cambios</span>
                  <Switch checked={soloCambios} onCheckedChange={setSoloCambios} />
                </label>
              ) : null}
            </div>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
            <div className="mx-auto max-w-3xl">
              {verQuery.isPending || cargandoComparacion ? (
                <Skeleton className="h-40 w-full" />
              ) : comparaCon ? (
                <DiffProsa antes={diffAntes} despues={diffDespues} soloCambios={soloCambios} />
              ) : (
                <LectorProsa cuerpo={verQuery.data?.documento.cuerpo ?? ""} />
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
