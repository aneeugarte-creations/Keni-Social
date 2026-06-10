/**
 * Editor de SLIDES de un carrusel: el media EN CRUDO que va detrás de la portada.
 *
 * La portada (slide 1) se edita arriba con la maquinaria de imagen de siempre (foto +
 * placa de marca); aquí se gestionan los slides EXTRA: subir imágenes/videos, quitarlos
 * y reordenarlos. Se publican tal cual (sin placa), en este orden, en el post multi-media.
 * Reusado por el editor de pieza (DialogoEditar) y por el cajón Presidencia.
 */
import { ArrowDown, ArrowUp, Film, ImagePlus, Loader2, Trash2, Video } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, mensajeError, urlMedia } from "@/lib/api";
import type { SlideCarrusel } from "@/lib/carrusel";

export function EditorCarrusel({
  slides,
  onCambio,
  disabled = false,
  idPrefijo = "carrusel",
}: {
  slides: SlideCarrusel[];
  onCambio: (slides: SlideCarrusel[]) => void;
  disabled?: boolean;
  idPrefijo?: string;
}) {
  const [subiendo, setSubiendo] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Sube cada archivo elegido por su endpoint (imagen o video) y AÑADE los slides en el
  // orden de selección. Best-effort por archivo: uno que falle no tira el resto.
  const subir = async (archivos: FileList | null) => {
    if (!archivos || archivos.length === 0) return;
    setSubiendo(true);
    const nuevos: SlideCarrusel[] = [];
    try {
      for (const archivo of Array.from(archivos)) {
        const esVideo = archivo.type.startsWith("video/");
        try {
          const resp = esVideo
            ? await api.subirVideo(archivo)
            : await api.subirMedia(archivo, "fotos");
          nuevos.push({ tipo: esVideo ? "video" : "imagen", objeto: resp.id });
        } catch (e) {
          toast.error(`${archivo.name}: ${mensajeError(e)}`);
        }
      }
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
    if (nuevos.length) onCambio([...slides, ...nuevos]);
  };

  const mover = (i: number, delta: -1 | 1) => {
    const j = i + delta;
    if (j < 0 || j >= slides.length) return;
    const copia = [...slides];
    [copia[i], copia[j]] = [copia[j], copia[i]];
    onCambio(copia);
  };

  const quitar = (i: number) => onCambio(slides.filter((_, k) => k !== i));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">
          Slides del carrusel
          <span className="ml-1 text-xs font-normal text-muted-foreground">
            (van EN CRUDO detrás de la portada, en este orden)
          </span>
        </p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="gap-1"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || subiendo}
          aria-label="Añadir slides"
        >
          {subiendo ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ImagePlus className="h-4 w-4" />
          )}
          Añadir media
        </Button>
        <input
          ref={inputRef}
          id={`${idPrefijo}-slides-input`}
          type="file"
          accept="image/*,video/*"
          multiple
          className="hidden"
          onChange={(e) => void subir(e.target.files)}
          aria-label="Archivos del carrusel"
        />
      </div>

      {slides.length === 0 ? (
        <p className="rounded-md border border-dashed p-3 text-center text-xs text-muted-foreground">
          Sin slides extra: el carrusel saldría solo con la portada. Sube aquí el resto del
          media de la nota (imágenes y videos).
        </p>
      ) : (
        <ul className="space-y-1.5">
          {slides.map((s, i) => (
            <li
              key={`${s.objeto}-${i}`}
              className="flex items-center gap-2 rounded-md border bg-card p-1.5"
              data-testid="slide-carrusel"
            >
              <span className="w-5 shrink-0 text-center text-xs text-muted-foreground">
                {/* La portada es el slide 1; estos van detrás. */}
                {i + 2}
              </span>
              {s.tipo === "video" ? (
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-muted">
                  <Film className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                </span>
              ) : (
                <img
                  src={urlMedia(s.objeto)}
                  alt={`Slide ${i + 2}`}
                  className="h-12 w-12 shrink-0 rounded object-cover"
                />
              )}
              <span className="flex min-w-0 flex-1 items-center gap-1 text-xs text-muted-foreground">
                {s.tipo === "video" && <Video className="h-3 w-3 shrink-0" aria-hidden="true" />}
                <span className="truncate">{s.objeto}</span>
              </span>
              <div className="flex shrink-0 items-center gap-0.5">
                <Button
                  type="button" size="sm" variant="ghost" className="h-7 w-7 p-0"
                  onClick={() => mover(i, -1)} disabled={disabled || i === 0}
                  aria-label={`Subir slide ${i + 2}`}
                >
                  <ArrowUp className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button" size="sm" variant="ghost" className="h-7 w-7 p-0"
                  onClick={() => mover(i, 1)} disabled={disabled || i === slides.length - 1}
                  aria-label={`Bajar slide ${i + 2}`}
                >
                  <ArrowDown className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button" size="sm" variant="ghost"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  onClick={() => quitar(i)} disabled={disabled}
                  aria-label={`Quitar slide ${i + 2}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
