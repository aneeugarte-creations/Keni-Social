/**
 * Controles de la PISTA BASE: subir el clip y elegir su ajuste (cover/contain) sobre el formato.
 * El POSICIONAMIENTO del foco del reencuadre se hace INLINE arrastrando sobre el lienzo central
 * (PreviewComposicion con `reframeEditable`), no con sliders. El clip se previsualiza en el
 * lienzo único, no aquí (sin doble vídeo).
 */
import { Clock, Crosshair } from "lucide-react";

import { EditorVideo } from "@/components/media/EditorVideo";
import { Label } from "@/components/ui/label";
import { formatearDuracionMs, pistaBase, type AjusteVideo, type ComposicionVideo } from "@/lib/video";

export interface PistaBaseProps {
  doc: ComposicionVideo;
  /** Clave del clip base en el almacén. */
  videoKey: string;
  /** URL servible del clip base. */
  videoUrl: string;
  /** Notifica subida/cambio del clip (clave + url) — el padre fija el clip en la composición. */
  onCambioVideo: (clave: string, url: string) => void;
  onReencuadre: (cambios: { ajuste?: AjusteVideo; foco?: [number, number] }) => void;
  disabled?: boolean;
}

export function PistaBase({ doc, videoKey, videoUrl, onCambioVideo, onReencuadre, disabled }: PistaBaseProps) {
  const clip = pistaBase(doc)?.clips[0];
  const durClipMs = clip ? clip.fin_ms - clip.inicio_ms : 0;

  return (
    <div className="space-y-4">
      <EditorVideo
        video={videoKey}
        videoUrl={videoUrl}
        onCambio={onCambioVideo}
        disabled={disabled}
        etiqueta="Vídeo base"
        compacto
      />

      {clip && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="h-3.5 w-3.5" />
          <span>
            Clip: <span className="tabular-nums">{durClipMs > 0 ? formatearDuracionMs(durClipMs) : "—"}</span>
            {" · "}
            Composición: <span className="tabular-nums">{doc.duracion_ms > 0 ? formatearDuracionMs(doc.duracion_ms) : "—"}</span>
          </span>
        </p>
      )}

      {clip && (
        <div className="space-y-3 rounded-md border border-border p-3">
          <Label className="flex items-center gap-1.5 text-sm font-semibold">
            <Crosshair className="h-4 w-4 text-muted-foreground" />
            Reencuadre sobre {doc.formato.preset}
          </Label>

          {/* Ajuste cover/contain. El foco se mueve arrastrando sobre el lienzo. */}
          <div className="flex gap-2">
            {(["cover", "contain"] as AjusteVideo[]).map((a) => (
              <button
                key={a}
                type="button"
                disabled={disabled}
                onClick={() => onReencuadre({ ajuste: a })}
                className={`flex-1 rounded-md border px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                  clip.ajuste === a
                    ? "border-primary bg-primary/5 text-foreground"
                    : "border-border text-muted-foreground hover:bg-accent/50"
                }`}
              >
                {a === "cover" ? "Llenar" : "Caber"}
              </button>
            ))}
          </div>
          {clip.ajuste === "cover" && (
            <p className="text-[11px] text-muted-foreground">
              Arrastra sobre el vídeo en el lienzo para mover el punto focal.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
