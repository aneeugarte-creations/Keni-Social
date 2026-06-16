/**
 * Zona de video de una pieza (Ola F): el usuario sube un clip de video que se adjunta
 * como asset al post. Espejo de `EditorImagen`, pero para video: sin composición de placa
 * (el video va tal cual) y con sugerencias de límites por red.
 *
 * El componente es controlado: el padre guarda la `clave` del video (nombre de archivo en
 * el almacén, vacío = sin video) y, opcionalmente, la URL ya conocida para previsualizarlo.
 * Notifica cada cambio vía `onCambio(clave, url)`.
 */
import { useMutation } from "@tanstack/react-query";
import { Loader2, Trash2, Upload, Video, VideoOff } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { api, mensajeError, urlMedia } from "@/lib/api";

/** Límites orientativos por red (para el aviso bajo el reproductor). */
const LIMITES_VIDEO: Record<string, string> = {
  instagram: "≤ 60 s, ≤ 100 MB · Reels hasta 90 s",
  x: "≤ 2 min 20 s, ≤ 512 MB",
  facebook: "≤ 240 min, ≤ 10 GB",
  youtube: "≤ 15 min (sin verificar) · vídeos cortos ≤ 60 s",
  tiktok: "≤ 10 min, ≤ 287 MB",
};

export interface EditorVideoProps {
  /** Clave del archivo de video en el almacén ("" si no hay). */
  video: string;
  /** URL ya conocida para previsualizar (opcional; se reconstruye de la clave si falta). */
  videoUrl?: string;
  /** Notifica la nueva clave de video (o "" al quitarlo) y su URL de previsualización. */
  onCambio: (clave: string, url: string) => void;
  disabled?: boolean;
  idPrefijo?: string;
  /** Red de la publicación (para mostrar el límite correspondiente). */
  red?: string;
}

export function EditorVideo({
  video,
  videoUrl,
  onCambio,
  disabled,
  idPrefijo = "vid",
  red,
}: EditorVideoProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  const src = urlMedia(videoUrl || video);

  // --- Subir un archivo de video --- //
  const subir = useMutation({
    mutationFn: (archivo: File) => api.subirVideo(archivo),
    onSuccess: (data) => onCambio(data.id, data.url),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const ocupado = subir.isPending || !!disabled;

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    if (archivo) subir.mutate(archivo);
    if (inputRef.current) inputRef.current.value = "";
  }

  function quitar() {
    onCambio("", "");
  }

  const limiteRed = red ? LIMITES_VIDEO[red] : undefined;

  return (
    <div className="space-y-2.5">
      <Label className="flex items-center gap-1.5">
        <Video className="h-4 w-4 text-muted-foreground" />
        Video
      </Label>

      <input
        ref={inputRef}
        id={`${idPrefijo}-archivo`}
        type="file"
        accept="video/*"
        onChange={onArchivo}
        className="hidden"
        aria-label="Adjuntar video"
      />

      {src ? (
        <div className="space-y-2">
          <FilaConAcciones
            como="div"
            kebab="nunca"
            realce
            acciones={[
              {
                etiqueta: "Reemplazar video",
                icono: subir.isPending ? undefined : Upload,
                onClick: () => inputRef.current?.click(),
                deshabilitado: ocupado,
              } as EntradaMenuContextual,
              {
                etiqueta: "Quitar video",
                icono: Trash2,
                onClick: async () => {
                  if (
                    await confirmar({
                      mensaje: "¿Quitar el video?",
                      destructivo: true,
                      textoConfirmar: "Quitar",
                    })
                  )
                    quitar();
                },
                destructivo: true,
                deshabilitado: ocupado,
              } as EntradaMenuContextual,
            ]}
          >
            <div className="relative inline-block w-full max-w-sm">
              <video
                src={src}
                controls
                muted
                className="w-full rounded-md border border-border transition-colors hover:border-keni-300 focus-within:border-keni-300"
                aria-label="Previsualización del video"
              />
            </div>
          </FilaConAcciones>

          {limiteRed && (
            <p className="text-xs text-muted-foreground">{limiteRed}</p>
          )}
        </div>
      ) : (
        <div className="space-y-2.5 rounded-md border border-dashed border-border bg-muted/20 p-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={ocupado}
          >
            {subir.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            {subir.isPending ? "Subiendo…" : "Subir video"}
          </Button>
          {limiteRed && (
            <p className="text-xs text-muted-foreground">{limiteRed}</p>
          )}
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <VideoOff className="h-3.5 w-3.5" />
            Sin video
          </p>
        </div>
      )}
    </div>
  );
}
