/**
 * Panel de RENDER: encola el render server-side (FFmpeg) de la composición y sondea el
 * progreso con `useGeneracion` (tipo "render-video"). Al completar muestra el mp4 resultante.
 *
 * El render es la fuente FIEL (el preview del navegador es solo aproximado). El job puede
 * tardar; corre en el worker y sobrevive a recargas (el sondeo lo reanuda).
 */
import { useMutation } from "@tanstack/react-query";
import { Download, Film, Loader2, Play } from "lucide-react";
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
    // El POST devuelve `{gen_id}`; pedimos la generación para sondear su progreso en vivo.
    mutationFn: async () => {
      await onAntesDeRenderizar?.();
      const { gen_id } = await api.video.render(composicionId!);
      const { generacion: gen } = await api.generacion(gen_id);
      return gen;
    },
    onSuccess: (gen) => {
      setUrl("");
      iniciar(gen);
      toast.info("Render encolado. Sigue su avance en Producción.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const renderizando = render.isPending || ejecutando;
  const fallo = generacion?.estado === "error";

  // Descarga DIRECTA del mp4 (fetch blob + <a download>): "abrir en pestaña nueva" obliga a
  // descargar desde el player del navegador; esto baja el archivo en un clic. Si falla, el error
  // queda VISIBLE en línea (un toast desaparece a los segundos) junto al enlace de fallback.
  const [descargando, setDescargando] = React.useState(false);
  const [errorDescarga, setErrorDescarga] = React.useState("");
  async function descargarMp4() {
    if (!url || descargando) return;
    setDescargando(true);
    setErrorDescarga("");
    try {
      const r = await fetch(urlMedia(url), { credentials: "same-origin" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const objUrl = URL.createObjectURL(blob);
      const enlace = document.createElement("a");
      enlace.href = objUrl;
      enlace.download = nombreMp4(url);
      document.body.appendChild(enlace);
      enlace.click();
      enlace.remove();
      URL.revokeObjectURL(objUrl);
    } catch {
      setErrorDescarga(
        "No se pudo descargar el MP4. Reinténtalo o ábrelo en una pestaña nueva y descárgalo desde ahí.",
      );
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="space-y-3">
      <Button
        type="button"
        onClick={() => render.mutate()}
        disabled={!composicionId || renderizando || disabled}
        title={!composicionId ? "Sube un clip base en la sección Base" : undefined}
      >
        {renderizando ? (
          <Loader2 className="mr-1 h-4 w-4 animate-spin" />
        ) : (
          <Film className="mr-1 h-4 w-4" />
        )}
        {renderizando ? "Renderizando…" : "Renderizar video"}
      </Button>

      {/* Razón VISIBLE del disabled: sin composición guardada no hay nada que renderizar. */}
      {!composicionId && (
        <p className="text-xs text-muted-foreground">
          Sube un clip base en la sección Base
        </p>
      )}

      {renderizando && generacion?.fase && (
        <p className="text-xs text-muted-foreground">
          {generacion.fase}
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
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => void descargarMp4()}
              disabled={descargando}
              aria-busy={descargando}
              title="Descarga el MP4 renderizado a tu equipo"
            >
              {descargando ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-1 h-4 w-4" />
              )}
              {descargando ? "Descargando…" : "Descargar MP4"}
            </Button>
            <a
              href={urlMedia(url)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              <Play className="h-3 w-3" />
              Abrir en pestaña nueva
            </a>
          </div>
          {/* Error de descarga EN LÍNEA y persistente (con el fallback al lado, no solo un toast). */}
          {errorDescarga && (
            <p role="alert" className="text-xs text-destructive">
              {errorDescarga}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Nombre de archivo para la descarga, derivado de la clave/URL del media (fallback `render.mp4`). */
function nombreMp4(u: string): string {
  const ultimo = u.split("?")[0].split("/").filter(Boolean).pop() ?? "";
  const limpio = decodeURIComponent(ultimo);
  return limpio.toLowerCase().endsWith(".mp4") ? limpio : "render.mp4";
}
