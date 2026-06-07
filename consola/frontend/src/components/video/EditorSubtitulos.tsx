/**
 * Editor de SUBTÍTULOS (corrección ortográfica humana es-MX).
 *
 * Flujo (contrato G-video-engine §4.2 + §5):
 *   1. "Transcribir" → `POST /api/video/composiciones/{id}/transcribir` encola el ASR
 *      (faster-whisper word-level). Se SONDEA con `useGeneracion` (tipo "transcribir").
 *   2. Al completar, se carga el recurso `video_subtitulos` (`GET /api/video/subtitulos/{id}`)
 *      y se muestran los `segmentos` como cajas de texto editables.
 *   3. El humano corrige la ortografía/erratas; "Guardar" persiste (`estado='editado'`),
 *      "Marcar listo" cierra la revisión (`estado='listo'`).
 *
 * NADA se quema en el video hasta que un humano marca los subtítulos como listos: el render
 * usa la versión corregida. Honesto: la transcripción es un punto de partida, no un final.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Captions, CheckCircle2, Loader2, Save, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, mensajeError } from "@/lib/api";
import {
  formatearTiempo,
  normalizarSegmentos,
  type EstadoSubtitulos,
  type SegmentoSub,
} from "@/lib/video";

export interface EditorSubtitulosProps {
  /** Id de la composición a transcribir (debe existir en el backend). */
  composicionId: string | null;
  /** Id del recurso de subtítulos ya ligado a la composición, si existe. */
  subtituloId: string | null;
  /** Avisa al padre del id de subtítulo (para ligarlo a la pista subs de la composición). */
  onSubtituloLigado: (id: string) => void;
  /** Notifica los segmentos corregidos al padre (para el preview). */
  onSegmentos?: (segmentos: SegmentoSub[]) => void;
}

const ETIQUETA_ESTADO: Record<EstadoSubtitulos, string> = {
  pendiente: "Pendiente",
  transcrito: "Transcrito (sin revisar)",
  editado: "Editado",
  listo: "Listo para quemar",
};

export function EditorSubtitulos({
  composicionId,
  subtituloId,
  onSubtituloLigado,
  onSegmentos,
}: EditorSubtitulosProps) {
  const qc = useQueryClient();
  const { generacion, ejecutando, iniciar } = useGeneracion();

  // Segmentos en edición (borrador local hasta guardar).
  const [segmentos, setSegmentos] = React.useState<SegmentoSub[]>([]);
  const [sucio, setSucio] = React.useState(false);

  // Carga el recurso de subtítulos cuando hay id (tras transcribir o al abrir una composición).
  const subQ = useQuery({
    queryKey: ["video-subtitulo", subtituloId],
    queryFn: ({ signal }) => api.video.subtitulo(subtituloId!, signal).then((r) => r.subtitulo),
    enabled: !!subtituloId,
  });

  // Cuando llega el recurso (y no hay edición sin guardar), hidrata el borrador local.
  React.useEffect(() => {
    if (!subQ.data || sucio) return;
    const segs = normalizarSegmentos(subQ.data.segmentos);
    setSegmentos(segs);
    onSegmentos?.(segs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subQ.data]);

  // Cuando la transcripción completa, su `resultado` trae el id del subtítulo: lo ligamos y
  // refrescamos. El backend ya escribió los segmentos en `video_subtitulos`.
  React.useEffect(() => {
    if (generacion?.estado !== "completado") return;
    const res = generacion.resultado as { subtitulo_id?: string; id?: string } | null;
    const sid = res?.subtitulo_id ?? res?.id;
    if (sid && sid !== subtituloId) {
      onSubtituloLigado(sid);
    }
    void qc.invalidateQueries({ queryKey: ["video-subtitulo"] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generacion?.estado]);

  const transcribir = useMutation({
    mutationFn: () => api.video.transcribir(composicionId!),
    onSuccess: (r) => {
      iniciar(r.generacion);
      toast.info("Transcripción en curso. Aparecerá en Actividad IA.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const guardar = useMutation({
    mutationFn: (estado: EstadoSubtitulos) =>
      api.video.guardarSubtitulo(subtituloId!, { segmentos, estado }),
    onSuccess: (_r, estado) => {
      setSucio(false);
      void qc.invalidateQueries({ queryKey: ["video-subtitulo", subtituloId] });
      onSegmentos?.(segmentos);
      toast.success(estado === "listo" ? "Subtítulos marcados como listos." : "Subtítulos guardados.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function editarTexto(id: string, texto: string) {
    setSegmentos((prev) => prev.map((s) => (s.id === id ? { ...s, texto } : s)));
    setSucio(true);
  }

  const estado = (subQ.data?.estado as EstadoSubtitulos) ?? "pendiente";
  const transcribiendo = transcribir.isPending || ejecutando;
  const tieneSegmentos = segmentos.length > 0;

  if (!composicionId) {
    return (
      <p className="rounded-md border border-dashed border-border bg-muted/20 p-3 text-xs text-muted-foreground">
        Sube primero un video base: la composición se crea al subirlo y entonces podrás transcribir
        los subtítulos.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => transcribir.mutate()}
          disabled={transcribiendo}
        >
          {transcribiendo ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="mr-1 h-4 w-4" />
          )}
          {tieneSegmentos ? "Re-transcribir" : "Transcribir"}
        </Button>
        {subQ.data && (
          <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            <Captions className="h-3 w-3" />
            {ETIQUETA_ESTADO[estado] ?? estado}
          </span>
        )}
      </div>

      {transcribiendo && (
        <p className="text-xs text-muted-foreground">
          {generacion?.fase ? `Transcribiendo (${generacion.fase})…` : "Transcribiendo el audio…"}
        </p>
      )}

      {tieneSegmentos ? (
        <>
          <p className="text-[11px] text-amber-700 dark:text-amber-400">
            Corrige la ortografía y erratas (es-MX). Nada se quema en el video hasta que marques los
            subtítulos como listos.
          </p>
          <ul className="max-h-72 space-y-2 overflow-auto pr-1">
            {segmentos.map((s) => (
              <li key={s.id} className="flex gap-2">
                <span className="w-20 shrink-0 pt-1.5 text-[11px] tabular-nums text-muted-foreground">
                  {formatearTiempo(s.inicio)}
                </span>
                <textarea
                  value={s.texto}
                  onChange={(e) => editarTexto(s.id, e.target.value)}
                  rows={1}
                  className="min-h-[2.25rem] flex-1 resize-y rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
                  aria-label={`Subtítulo en ${formatearTiempo(s.inicio)}`}
                />
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => guardar.mutate("editado")}
              disabled={!sucio || guardar.isPending}
            >
              <Save className="mr-1 h-4 w-4" />
              Guardar correcciones
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => guardar.mutate("listo")}
              disabled={guardar.isPending}
            >
              <CheckCircle2 className="mr-1 h-4 w-4" />
              Marcar listo
            </Button>
          </div>
        </>
      ) : (
        !transcribiendo && (
          <p className="text-xs text-muted-foreground">
            Aún no hay subtítulos. Pulsa «Transcribir» para generarlos con IA y luego corrígelos a
            mano.
          </p>
        )
      )}
    </div>
  );
}
