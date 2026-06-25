/**
 * Panel de DOBLE PISTA / Picture-in-Picture: sube un segundo video y lo posiciona (x/y/w/h)
 * como ventana sobre el preview. La ventana también se ARRASTRA/REDIMENSIONA directamente
 * sobre la vista previa (PreviewComposicion con `pipEditable`); estos inputs numéricos y el
 * gesto editan el MISMO documento, así que quedan siempre sincronizados. El render server-side
 * compone con `overlay` en FFmpeg.
 */
import { Trash2 } from "lucide-react";

import { EditorVideo } from "@/components/media/EditorVideo";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { pistaPip, type ComposicionVideo } from "@/lib/video";

export interface PanelPipProps {
  doc: ComposicionVideo;
  videoKey: string;
  videoUrl: string;
  onCambioVideo: (clave: string, url: string) => void;
  onCaja: (caja: { x?: number; y?: number; w?: number; h?: number }) => void;
  onQuitar: () => void;
  disabled?: boolean;
}

export function PanelPip({
  doc,
  videoKey,
  videoUrl,
  onCambioVideo,
  onCaja,
  onQuitar,
  disabled,
}: PanelPipProps) {
  const clip = pistaPip(doc)?.clips[0];
  const { w: lienzoW, h: lienzoH } = doc.formato;

  return (
    <div className="space-y-4">
      <EditorVideo
        video={videoKey}
        videoUrl={videoUrl}
        onCambio={onCambioVideo}
        disabled={disabled}
        idPrefijo="pip"
      />

      {clip && (
        <div className="space-y-3 rounded-md border border-border p-3">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-semibold">Posición</Label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onQuitar}
              disabled={disabled}
              className="h-7 text-destructive hover:text-destructive"
            >
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              Quitar PiP
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <CampoNum etiqueta="X" valor={clip.x} max={lienzoW} onCambio={(x) => onCaja({ x })} disabled={disabled} />
            <CampoNum etiqueta="Y" valor={clip.y} max={lienzoH} onCambio={(y) => onCaja({ y })} disabled={disabled} />
            <CampoNum etiqueta="Ancho" valor={clip.w} max={lienzoW} onCambio={(w) => onCaja({ w })} disabled={disabled} />
            <CampoNum etiqueta="Alto" valor={clip.h} max={lienzoH} onCambio={(h) => onCaja({ h })} disabled={disabled} />
          </div>
          <p className="text-[11px] text-muted-foreground">
            Arrastra en el preview o ajusta los valores.
          </p>
        </div>
      )}
    </div>
  );
}

function CampoNum({
  etiqueta,
  valor,
  max,
  onCambio,
  disabled,
}: {
  etiqueta: string;
  valor: number;
  max: number;
  onCambio: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <Label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {etiqueta}
      <input
        type="number"
        min={0}
        max={max}
        value={valor}
        disabled={disabled}
        onChange={(e) => onCambio(Number(e.target.value))}
        className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground disabled:opacity-50"
        aria-label={`PiP ${etiqueta}`}
      />
    </Label>
  );
}
