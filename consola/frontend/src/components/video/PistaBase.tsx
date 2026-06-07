/**
 * Controles de la PISTA BASE: subir el clip y reencuadrarlo sobre el formato elegido.
 *
 * El reencuadre fino (trim, blur, cortar silencios) NO se hace aquí — eso es Premiere. Aquí
 * solo el "toque RRSS": ajuste cover/contain y punto focal para que el clip caiga bien en el
 * lienzo vertical/cuadrado/horizontal.
 */
import { Crosshair } from "lucide-react";

import { EditorVideo } from "@/components/media/EditorVideo";
import { Label } from "@/components/ui/label";
import { pistaBase, type AjusteVideo, type ComposicionVideo } from "@/lib/video";

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

export function PistaBase({
  doc,
  videoKey,
  videoUrl,
  onCambioVideo,
  onReencuadre,
  disabled,
}: PistaBaseProps) {
  const clip = pistaBase(doc)?.clips[0];

  return (
    <div className="space-y-4">
      <EditorVideo video={videoKey} videoUrl={videoUrl} onCambio={onCambioVideo} disabled={disabled} />

      {clip && (
        <div className="space-y-3 rounded-md border border-border p-3">
          <Label className="flex items-center gap-1.5 text-sm font-semibold">
            <Crosshair className="h-4 w-4 text-muted-foreground" />
            Reencuadre sobre {doc.formato.preset}
          </Label>

          {/* Ajuste cover/contain */}
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
                {a === "cover" ? "Llenar (cover)" : "Caber (contain)"}
              </button>
            ))}
          </div>

          {/* Foco X / Y — solo relevante con cover */}
          <div className="space-y-2" aria-disabled={clip.ajuste === "contain"}>
            <div className="flex items-center gap-2">
              <span className="w-14 text-xs text-muted-foreground">Foco X</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={clip.foco[0]}
                disabled={disabled || clip.ajuste === "contain"}
                onChange={(e) => onReencuadre({ foco: [Number(e.target.value), clip.foco[1]] })}
                className="flex-1 disabled:opacity-40"
                aria-label="Foco horizontal"
              />
              <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">
                {Math.round(clip.foco[0] * 100)}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-14 text-xs text-muted-foreground">Foco Y</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={clip.foco[1]}
                disabled={disabled || clip.ajuste === "contain"}
                onChange={(e) => onReencuadre({ foco: [clip.foco[0], Number(e.target.value)] })}
                className="flex-1 disabled:opacity-40"
                aria-label="Foco vertical"
              />
              <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">
                {Math.round(clip.foco[1] * 100)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
