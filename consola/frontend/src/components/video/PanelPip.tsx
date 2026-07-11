/**
 * Panel de DOBLE PISTA / Picture-in-Picture: sube un segundo video. El POSICIONAMIENTO (mover/
 * redimensionar) se hace INLINE sobre el lienzo central (PreviewComposicion con `pipEditable`),
 * no con campos numéricos: aquí solo se sube/quita el clip. El render compone con `overlay`.
 */
import { Trash2 } from "lucide-react";

import { EditorVideo } from "@/components/media/EditorVideo";
import { Button } from "@/components/ui/button";
import { pistaPip, type ComposicionVideo } from "@/lib/video";

export interface PanelPipProps {
  doc: ComposicionVideo;
  videoKey: string;
  videoUrl: string;
  onCambioVideo: (clave: string, url: string) => void;
  onQuitar: () => void;
  disabled?: boolean;
}

export function PanelPip({ doc, videoKey, videoUrl, onCambioVideo, onQuitar, disabled }: PanelPipProps) {
  const clip = pistaPip(doc)?.clips[0];

  return (
    <div className="space-y-4">
      <EditorVideo
        video={videoKey}
        videoUrl={videoUrl}
        onCambio={onCambioVideo}
        disabled={disabled}
        idPrefijo="pip"
        etiqueta="Vídeo PiP"
        compacto
      />

      {clip && (
        <div className="space-y-2">
          <p className="text-[11px] text-muted-foreground">
            Arrastra y redimensiona la ventana PiP directamente sobre el lienzo.
          </p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onQuitar}
            disabled={disabled}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="mr-1 h-3.5 w-3.5" />
            Quitar PiP
          </Button>
        </div>
      )}
    </div>
  );
}
