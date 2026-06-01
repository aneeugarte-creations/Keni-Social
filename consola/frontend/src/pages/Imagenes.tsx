/**
 * Imágenes — generación de imagen con IA como superficie propia (camino NEUTRO).
 *
 * Usa el camino directo `POST /api/media/generar` (proveedor de imagen vía `media.py`),
 * que NUNCA dependió del sistema de skills (ya retirado). Permite describir una imagen,
 * generarla en segundo plano (sondeo de la generación) y descargarla / copiar su URL.
 *
 * El Estudio de imagen rico (recorte/extensión/composición de marca + revisión legal)
 * está diseñado en `docs/diseno-estudio-imagen.md` (motor ya relocalizado en
 * `keni_consola/motores/estudio_imagen/`); esta página es la generación base mientras
 * ese Estudio se construye. El editor inline por pieza (`EditorImagen`) sigue intacto.
 */
import { useMutation } from "@tanstack/react-query";
import { Download, ImagePlus, Loader2, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError, urlMedia } from "@/lib/api";

const CLAVE_GEN = "keni:generacion-imagenes";

export default function Imagenes() {
  const [prompt, setPrompt] = React.useState("");
  const [aviso, setAviso] = React.useState("");
  const [imagen, setImagen] = React.useState<{ url: string } | null>(null);

  const { generacion, ejecutando, iniciar } = useGeneracion(CLAVE_GEN);

  const generar = useMutation({
    mutationFn: () => api.generarMedia({ prompt: prompt.trim() }),
    onSuccess: (data) => {
      setAviso("");
      setImagen(null);
      iniciar(data.generacion);
    },
    onError: (e) => {
      // 400 = generación no configurada: aviso amable (no error rojo); es síncrono.
      if (e instanceof ApiError && e.status === 400) {
        setAviso(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo generar la imagen.");
    },
  });

  // Al completarse la generación, mostramos la imagen (una vez por id).
  const terminalRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!generacion || generacion.id === terminalRef.current) return;
    if (generacion.estado === "completado") {
      terminalRef.current = generacion.id;
      const r = generacion.resultado as { url?: string } | undefined;
      if (r?.url) setImagen({ url: r.url });
    } else if (generacion.estado === "error") {
      terminalRef.current = generacion.id;
      toast.error(generacion.error || "No se pudo generar la imagen.");
    }
  }, [generacion]);

  const ocupado = generar.isPending || ejecutando;
  const src = imagen ? urlMedia(imagen.url) : "";

  return (
    <>
      <PageHeader
        titulo="Imágenes"
        descripcion="Genera una imagen con IA a partir de una descripción. Adjúntala luego a una pieza desde el editor de cada publicación."
      />

      <div className="grid max-w-3xl gap-4">
        <div className="space-y-2">
          <Label htmlFor="prompt-imagen">Describe la imagen</Label>
          <Textarea
            id="prompt-imagen"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="p. ej. estadio iluminado al atardecer, hinchada al fondo, estilo editorial deportivo…"
            rows={4}
            disabled={ocupado}
          />
        </div>

        <div>
          <Button
            onClick={() => generar.mutate()}
            disabled={ocupado || prompt.trim().length === 0}
          >
            {ocupado ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-1 h-4 w-4" />
            )}
            {ocupado ? "Generando…" : "Generar imagen"}
          </Button>
        </div>

        {aviso && (
          <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
            {aviso}
          </p>
        )}

        {src ? (
          <div className="space-y-2 rounded-md border border-border p-3">
            <img
              src={src}
              alt="Imagen generada"
              className="max-h-[28rem] w-auto rounded-md border border-border object-contain"
            />
            <div className="flex gap-2">
              <Button asChild variant="outline" size="sm">
                <a href={src} download>
                  <Download className="mr-1 h-4 w-4" />
                  Descargar
                </a>
              </Button>
            </div>
          </div>
        ) : ejecutando ? (
          <div className="flex items-center gap-2 rounded-md border border-dashed border-border p-6 text-muted-foreground">
            <ImagePlus className="h-5 w-5" />
            <span className="text-sm">Generando la imagen…</span>
          </div>
        ) : null}
      </div>
    </>
  );
}
