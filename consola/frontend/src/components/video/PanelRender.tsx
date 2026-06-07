/**
 * Panel de RENDER: encola el render server-side (FFmpeg) de la composición y sondea el
 * progreso con `useGeneracion` (tipo "render-video"). Al completar muestra el mp4 resultante.
 *
 * El render es la fuente FIEL (el preview del navegador es solo aproximado). El job puede
 * tardar; corre en el worker y sobrevive a recargas (el sondeo lo reanuda).
 */
import { useMutation } from "@tanstack/react-query";
import { Film, Loader2, Play } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, mensajeError, urlMedia } from "@/lib/api";

export interface PanelRenderProps {
  /** Id de la composición a renderizar (debe existir y estar guardada). */
  composicionId: string | null;
  /** Hay que guardar antes de renderizar. */
  onAntesDeRenderizar?: () => Promise<void> | void;
  disabled?: boolean;
}

export function PanelRender({ composicionId, onAntesDeRenderizar, disabled }: PanelRenderProps) {
  const { generacion, ejecutando, iniciar } = useGeneracion("keni.video.render");
  const [url, setUrl] = React.useState("");

  React.useEffect(() => {
    if (generacion?.estado !== "completado") return;
    const res = generacion.resultado as { url?: string; media_id?: string } | null;
    const u = res?.url ?? (res?.media_id ? urlMedia(res.media_id) : "");
    if (u) setUrl(u);
  }, [generacion?.estado, generacion?.resultado]);

  const render = useMutation({
    mutationFn: async () => {
      await onAntesDeRenderizar?.();
      return api.video.render(composicionId!);
    },
    onSuccess: (r) => {
      setUrl("");
      iniciar(r.generacion);
      toast.info("Render encolado. Sigue su avance en Actividad IA.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const renderizando = render.isPending || ejecutando;
  const fallo = generacion?.estado === "error";

  return (
    <div className="space-y-3">
      <Button
        type="button"
        onClick={() => render.mutate()}
        disabled={!composicionId || renderizando || disabled}
      >
        {renderizando ? (
          <Loader2 className="mr-1 h-4 w-4 animate-spin" />
        ) : (
          <Film className="mr-1 h-4 w-4" />
        )}
        {renderizando ? "Renderizando…" : "Renderizar video"}
      </Button>

      {renderizando && (
        <p className="text-xs text-muted-foreground">
          {generacion?.fase ? `Render en curso (${generacion.fase})…` : "Componiendo con FFmpeg…"}
        </p>
      )}

      {fallo && (
        <p className="text-xs text-destructive">{generacion?.error || "El render falló."}</p>
      )}

      {url && (
        <div className="space-y-2">
          <video
            src={urlMedia(url)}
            controls
            playsInline
            className="w-full rounded-md border border-border"
            aria-label="Video renderizado"
          />
          <a
            href={urlMedia(url)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <Play className="h-3 w-3" />
            Abrir el mp4 en una pestaña nueva
          </a>
        </div>
      )}
    </div>
  );
}
