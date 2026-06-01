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
import { AlertTriangle, ImagePlus, Loader2, Upload, Wand2, X } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError, urlMedia } from "@/lib/api";
import { nombreRed, tamanoRed } from "@/pages/publicaciones/meta";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Convierte una relación tipo "16:9" o "1.91:1" en un número (ancho/alto). */
function ratioDe(txt: string): number | null {
  const [w, h] = txt.split(/[:/]/).map((n) => parseFloat(n));
  return w && h ? w / h : null;
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
  /**
   * Contexto de la pieza, opcional: si se pasa, se muestra un enlace discreto
   * "Abrir en Estudio" que lleva al Estudio de imagen preconfigurado (router state).
   */
  publicacionId?: string;
  marca?: string;
  red?: string;
  copy?: string;
  /** Texto que va DENTRO de la imagen (copy-in); titular al integrar la foto en la plantilla. */
  copyIn?: string;
}

export function EditorImagen({
  imagen,
  imagenUrl,
  onCambio,
  disabled,
  idPrefijo = "img",
  publicacionId,
  marca,
  red,
  copy,
  copyIn,
}: EditorImagenProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [prompt, setPrompt] = React.useState("");
  // Aviso amable cuando la generación no está configurada (400).
  const [avisoGenerar, setAvisoGenerar] = React.useState("");

  const src = urlMedia(imagenUrl || imagen);

  // Aspect-ratio real de la imagen (medido al cargar) frente al recomendado de la red:
  // avisa si se desvía del estándar (la red la recortaría).
  const [ratioReal, setRatioReal] = React.useState<number | null>(null);
  React.useEffect(() => {
    setRatioReal(null);
  }, [src]);
  const tamRed = red ? tamanoRed(red) : null;
  const ratioRec = tamRed ? ratioDe(tamRed.ratio) : null;
  const aspectoFueraDeEstandar =
    ratioReal != null && ratioRec != null && Math.abs(ratioReal - ratioRec) / ratioRec > 0.1;

  const subir = useMutation({
    // Sube la foto y, si pertenece a una publicación, la INTEGRA en la plantilla de marca
    // (logo + copy-in + pleca). Para marcas sin plantilla el backend devuelve la foto tal cual,
    // así que el flujo es uniforme. Sin `publicacionId` (uso suelto), solo adjunta.
    mutationFn: async (archivo: File) => {
      const subida = await api.subirMedia(archivo);
      if (!publicacionId) return { id: subida.id, url: subida.url };
      const integrada = await api.integrarFotoPublicacion(publicacionId, subida.id, copyIn);
      return { id: integrada.imagen, url: integrada.imagen_url };
    },
    onSuccess: (data) => {
      onCambio(data.id, data.url);
      toast.success(publicacionId ? "Foto integrada en la plantilla" : "Imagen adjuntada");
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
      <div className="flex items-center justify-between gap-2">
        <Label className="flex items-center gap-1.5">
          <ImagePlus className="h-4 w-4 text-muted-foreground" />
          Imagen <span className="font-normal text-muted-foreground">(opcional)</span>
        </Label>
        {publicacionId && (
          <Button
            asChild
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            disabled={!!disabled}
          >
            <Link
              to="/estudio"
              state={{ publicacionId, marca, red, copy, imagen: imagen || undefined }}
            >
              <Wand2 className="mr-1 h-3.5 w-3.5" />
              Abrir en Estudio
            </Link>
          </Button>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={onArchivo}
        className="hidden"
        aria-label="Adjuntar imagen"
      />

      {src ? (
        <div className="space-y-2">
          <div className="relative inline-block">
            <img
              src={src}
              alt="Imagen de la publicación"
              onLoad={(e) =>
                setRatioReal(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)
              }
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
          {aspectoFueraDeEstandar && tamRed && red && (
            <p className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                La relación de aspecto no es la {tamRed.ratio} estándar de {nombreRed(red)}: se
                recortará. {publicacionId ? "Adáptala en el Estudio" : "Recórtala"} a {tamRed.px} px.
              </span>
            </p>
          )}
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
              {subir.isPending && publicacionId ? "Integrando…" : "Adjuntar"}
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
                <MarcaIA costo />
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
