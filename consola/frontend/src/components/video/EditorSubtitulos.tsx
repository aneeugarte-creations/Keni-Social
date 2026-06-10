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
  /** Clave de media del clip del que extraer el audio (el clip base). */
  baseMediaId: string;
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
  baseMediaId,
  onSubtituloLigado,
  onSegmentos,
}: EditorSubtitulosProps) {
  const qc = useQueryClient();
  const { generacion, ejecutando, iniciar } = useGeneracion();

  // Segmentos en edición (borrador local hasta guardar).
  const [segmentos, setSegmentos] = React.useState<SegmentoSub[]>([]);
  const [sucio, setSucio] = React.useState(false);
  // Las correcciones SIN GUARDAR se respaldan en sessionStorage: si el usuario navega a otra
  // sección/página y vuelve, se restauran (con aviso) en vez de perderse.
  const claveBorrador = composicionId ? `keni:video:subs:${composicionId}` : null;
  const [restaurado, setRestaurado] = React.useState(false);

  // Carga la fila de subtítulos de la composición (puede ser null si aún no se transcribió).
  const subQ = useQuery({
    queryKey: ["video-subtitulos-de", composicionId],
    queryFn: ({ signal }) =>
      api.video.subtitulosDe(composicionId!, signal).then((r) => r.subtitulo),
    enabled: !!composicionId,
  });
  const sub = subQ.data ?? null;
  const subtituloId = sub?.id ?? null;

  // Liga el id de subtítulo al padre en cuanto se conoce (lo escribe en la pista subs).
  React.useEffect(() => {
    if (subtituloId) onSubtituloLigado(subtituloId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subtituloId]);

  // Cuando llega la fila (y no hay edición sin guardar), hidrata el borrador local. Si hay un
  // respaldo en sessionStorage (correcciones que no llegaron a guardarse), gana el respaldo y
  // se marca sucio para que el dato del servidor no lo pise y "Guardar" quede habilitado.
  React.useEffect(() => {
    if (!sub || sucio) return;
    const respaldo = leerRespaldo(claveBorrador);
    if (respaldo) {
      setSegmentos(respaldo);
      setSucio(true);
      setRestaurado(true);
      onSegmentos?.(respaldo);
      return;
    }
    const segs = normalizarSegmentos(sub.segmentos);
    setSegmentos(segs);
    onSegmentos?.(segs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sub]);

  // Respalda cada edición sin guardar (pequeño: texto + tiempos; sobrevive a la navegación
  // dentro de la pestaña, que es donde se perdían las correcciones).
  React.useEffect(() => {
    if (!sucio || !claveBorrador) return;
    try {
      sessionStorage.setItem(claveBorrador, JSON.stringify(segmentos));
    } catch {
      /* sessionStorage lleno o no disponible (modo privado): seguimos sin respaldo */
    }
  }, [segmentos, sucio, claveBorrador]);

  // Al completar la transcripción, el worker ya escribió los segmentos: refrescamos la fila.
  React.useEffect(() => {
    if (generacion?.estado !== "completado") return;
    void qc.invalidateQueries({ queryKey: ["video-subtitulos-de", composicionId] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generacion?.estado]);

  const transcribir = useMutation({
    // El POST devuelve `{gen_id, subtitulo_id}`; pedimos la generación para sondearla en vivo.
    mutationFn: async () => {
      const { gen_id } = await api.video.transcribir(composicionId!, baseMediaId);
      const { generacion: gen } = await api.generacion(gen_id);
      return gen;
    },
    onSuccess: (gen) => {
      iniciar(gen);
      void qc.invalidateQueries({ queryKey: ["video-subtitulos-de", composicionId] });
      toast.info("Transcripción en curso. Aparecerá en Actividad IA.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const guardar = useMutation({
    mutationFn: (estado: EstadoSubtitulos) =>
      api.video.guardarSubtitulo(subtituloId!, { segmentos, estado }),
    onSuccess: (_r, estado) => {
      setSucio(false);
      setRestaurado(false);
      // Guardado en el servidor: el respaldo local ya no aplica.
      if (claveBorrador) {
        try {
          sessionStorage.removeItem(claveBorrador);
        } catch {
          /* sin sessionStorage no había respaldo que limpiar */
        }
      }
      void qc.invalidateQueries({ queryKey: ["video-subtitulos-de", composicionId] });
      onSegmentos?.(segmentos);
      toast.success(estado === "listo" ? "Subtítulos marcados como listos." : "Subtítulos guardados.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function editarTexto(id: string, texto: string) {
    setSegmentos((prev) => prev.map((s) => (s.id === id ? { ...s, texto } : s)));
    setSucio(true);
  }

  const estado = (sub?.estado as EstadoSubtitulos) ?? "pendiente";
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
          disabled={transcribiendo || !baseMediaId}
        >
          {transcribiendo ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="mr-1 h-4 w-4" />
          )}
          {tieneSegmentos ? "Re-transcribir" : "Transcribir"}
        </Button>
        {sub && (
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
          {restaurado && (
            <p
              role="status"
              className="rounded-md border border-amber-300/60 bg-amber-50 px-2 py-1.5 text-[11px] font-medium text-amber-800 dark:border-amber-700/50 dark:bg-amber-950/40 dark:text-amber-300"
            >
              Tienes cambios sin guardar restaurados de tu sesión anterior. Pulsa «Guardar
              correcciones» para conservarlos.
            </p>
          )}
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

/**
 * Lee el respaldo de correcciones sin guardar de sessionStorage (`keni:video:subs:<id>`).
 * Devuelve null si no hay clave, no hay respaldo, está corrupto o quedó vacío.
 */
function leerRespaldo(clave: string | null): SegmentoSub[] | null {
  if (!clave) return null;
  try {
    const crudo = sessionStorage.getItem(clave);
    if (!crudo) return null;
    const segs = normalizarSegmentos(JSON.parse(crudo));
    return segs.length > 0 ? segs : null;
  } catch (e) {
    // Respaldo corrupto o sessionStorage inaccesible: se descarta (gana el dato del servidor),
    // pero se deja rastro — un respaldo que no restaura son correcciones humanas perdidas.
    console.warn(`Respaldo de subtítulos ilegible en sessionStorage (${clave}); se descarta.`, e);
    return null;
  }
}
