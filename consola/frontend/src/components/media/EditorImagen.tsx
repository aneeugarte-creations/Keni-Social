/**
 * Zona de imagen reutilizable para componer/editar publicaciones.
 *
 * Permite **adjuntar** un archivo (`POST /api/media`) o **generar con IA**
 * (`POST /api/media/generar`). Previsualiza la imagen (`imagen_url`) y permite
 * quitarla. Si la generación devuelve 400 ("no configurada"), se muestra un
 * aviso amable en ámbar (no un error rojo) y la zona sigue funcionando.
 *
 * El componente es controlado: el padre guarda el `nombre` de la imagen (vacío
 * = sin imagen) y lo incluye al guardar la publicación.
 */
import { useMutation } from "@tanstack/react-query";
import { ImagePlus, Loader2, Sparkles, Upload, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError, urlMedia } from "@/lib/api";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

export interface EditorImagenProps {
  /** Nombre del archivo de imagen actual (`""` si no hay). */
  imagen: string;
  /** URL conocida para servir la imagen (de la publicación); opcional. */
  imagenUrl?: string;
  /** Notifica el nuevo nombre de imagen (o `""` al quitarla). */
  onCambio: (nombre: string, url: string) => void;
  /** Marca (para anteponer en el prompt de generación si se desea). */
  disabled?: boolean;
  idPrefijo?: string;
}

export function EditorImagen({
  imagen,
  imagenUrl,
  onCambio,
  disabled,
  idPrefijo = "img",
}: EditorImagenProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [prompt, setPrompt] = React.useState("");
  // Aviso amable cuando la generación no está configurada (400).
  const [avisoGenerar, setAvisoGenerar] = React.useState("");

  const src = urlMedia(imagenUrl || imagen);

  const subir = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (data) => {
      onCambio(data.id, data.url);
      toast.success("Imagen adjuntada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // La imagen se genera como trabajo de IA en background; seguimos su progreso.
  const { generacion, ejecutando, iniciar } = useGeneracion();

  const generar = useMutation({
    mutationFn: () => api.generarMedia({ prompt: prompt.trim() }),
    onSuccess: (data) => {
      setAvisoGenerar("");
      iniciar(data.generacion);
    },
    onError: (e) => {
      // 400 = generación no configurada: aviso amable, no error rojo (es síncrono).
      if (e instanceof ApiError && e.status === 400) {
        setAvisoGenerar(e.message);
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  // Al completarse la generación, adjuntamos la imagen (una vez por id).
  const terminalRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!generacion || generacion.id === terminalRef.current) return;
    if (generacion.estado === "completado") {
      terminalRef.current = generacion.id;
      const r = generacion.resultado;
      if (r?.id && r?.url) {
        onCambio(r.id, r.url);
        setPrompt("");
        toast.success("Imagen generada");
      }
    } else if (generacion.estado === "error") {
      terminalRef.current = generacion.id;
      toast.error(generacion.error || "No se pudo generar la imagen.");
    }
  }, [generacion, onCambio]);

  const generando = generar.isPending || ejecutando;

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    if (archivo) subir.mutate(archivo);
    // Permite re-subir el mismo archivo más tarde.
    if (inputRef.current) inputRef.current.value = "";
  }

  function quitar() {
    onCambio("", "");
    setAvisoGenerar("");
  }

  const ocupado = subir.isPending || generando || !!disabled;

  return (
    <div className="space-y-2.5">
      <Label className="flex items-center gap-1.5">
        <ImagePlus className="h-4 w-4 text-muted-foreground" />
        Imagen <span className="font-normal text-muted-foreground">(opcional)</span>
      </Label>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={onArchivo}
        className="hidden"
        aria-label="Adjuntar imagen"
      />

      {src ? (
        <div className="relative inline-block">
          <img
            src={src}
            alt="Imagen de la publicación"
            className="max-h-56 w-auto rounded-md border border-border object-contain"
          />
          <Button
            type="button"
            variant="destructive"
            size="icon"
            className="absolute right-1.5 top-1.5 h-7 w-7"
            onClick={quitar}
            disabled={ocupado}
            aria-label="Quitar imagen"
            title="Quitar imagen"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <div className="space-y-2.5 rounded-md border border-dashed border-border bg-muted/20 p-3">
          <div className="flex flex-wrap items-center gap-2">
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
              Adjuntar
            </Button>
            <span className="text-xs text-muted-foreground">o genera una con IA:</span>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Label htmlFor={`${idPrefijo}-prompt`} className="sr-only">
              Describe la imagen a generar
            </Label>
            <Input
              id={`${idPrefijo}-prompt`}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe la imagen: p. ej. estadio iluminado al atardecer…"
              disabled={ocupado}
              onKeyDown={(e) => {
                if (e.key === "Enter" && prompt.trim() && !ocupado) {
                  e.preventDefault();
                  generar.mutate();
                }
              }}
            />
            <Button
              type="button"
              size="sm"
              onClick={() => generar.mutate()}
              disabled={ocupado || prompt.trim().length === 0}
              className="shrink-0"
            >
              {generando ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              {generando ? "Generando…" : "Generar con IA"}
            </Button>
          </div>
          {avisoGenerar && (
            <p className="rounded-md bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-300">
              {avisoGenerar}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
