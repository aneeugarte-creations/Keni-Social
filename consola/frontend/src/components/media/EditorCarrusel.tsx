/**
 * Editor de SLIDES de un carrusel: el media EN CRUDO que va detrás de la portada.
 *
 * La portada (slide 1) se edita arriba con la maquinaria de imagen de siempre (foto +
 * placa de marca); aquí se gestionan los slides EXTRA: subir imágenes/videos, quitarlos
 * y reordenarlos. Se publican tal cual (sin placa), en este orden, en el post multi-media.
 * Reusado por el editor de pieza (DialogoEditar) y por el cajón Presidencia.
 */
import {
  ArrowDown,
  ArrowUp,
  Film,
  ImagePlus,
  Loader2,
  Star,
  Trash2,
  Video,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { api, mensajeError, urlMedia } from "@/lib/api";
import type { SlideCarrusel } from "@/lib/carrusel";

export function EditorCarrusel({
  slides,
  onCambio,
  disabled = false,
  idPrefijo = "carrusel",
  base = 2,
  etiqueta,
  marcarPortada = false,
  onPortada,
}: {
  slides: SlideCarrusel[];
  onCambio: (slides: SlideCarrusel[]) => void;
  disabled?: boolean;
  idPrefijo?: string;
  /**
   * Número del PRIMER elemento de la lista en el carrusel publicado. En el editor de
   * pieza los slides van DETRÁS de la portada (base 2, default); en el cajón Presidencia
   * la lista ES el carrusel entero (base 1: la primera imagen será la portada).
   */
  base?: number;
  /** Título de la sección (default: "Slides del carrusel" con su aclaración). */
  etiqueta?: React.ReactNode;
  /**
   * Marca con una insignia "Portada" la PRIMERA imagen de la lista (cajón Presidencia:
   * esa imagen se compondrá con la placa de marca). Default off.
   */
  marcarPortada?: boolean;
  /**
   * "Hacer portada": promueve el slide `i` (solo imágenes) a PORTADA de la pieza. El
   * llamante (DialogoEditar) intercambia la foto del hueco 0 con este slide. Sin
   * callback (p. ej. el cajón Presidencia, donde la portada es la primera imagen de la
   * lista), el botón no se pinta.
   */
  onPortada?: (indice: number) => void;
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

  // Primera IMAGEN de la lista: en el cajón (marcarPortada) será la portada compuesta.
  const idxPortada = marcarPortada ? slides.findIndex((s) => s.tipo === "imagen") : -1;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">
          {etiqueta ?? "Slides del carrusel"}
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
          Sube imágenes y videos
        </p>
      ) : (
        <ul className="space-y-1.5">
          {slides.map((s, i) => {
            const acciones: EntradaMenuContextual[] = [];
            if (onPortada && s.tipo === "imagen") {
              acciones.push({
                etiqueta: "Marcar portada",
                icono: Star,
                onClick: () => onPortada(i),
                deshabilitado: disabled,
              });
            }
            acciones.push({
              etiqueta: "Subir",
              icono: ArrowUp,
              onClick: () => mover(i, -1),
              deshabilitado: disabled || i === 0,
            });
            acciones.push({
              etiqueta: "Bajar",
              icono: ArrowDown,
              onClick: () => mover(i, 1),
              deshabilitado: disabled || i === slides.length - 1,
            });
            acciones.push({
              etiqueta: "Quitar",
              icono: Trash2,
              onClick: () => quitar(i),
              destructivo: true,
              deshabilitado: disabled,
            });

            return (
              <FilaConAcciones
                key={`${s.objeto}-${i}`}
                como="li"
                kebab="nunca"
                realce
                acciones={acciones}
                etiquetaAcciones={`Acciones del slide ${i + base}`}
              >
                <div className="flex items-center gap-2 rounded-md border bg-card p-1.5" data-testid="slide-carrusel">
                  <span className="w-5 shrink-0 text-center text-xs text-muted-foreground">
                    {i + base}
                  </span>
                  {s.tipo === "video" ? (
                    <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-muted">
                      <Film className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                    </span>
                  ) : (
                    <img
                      src={urlMedia(s.objeto)}
                      alt={`Slide ${i + base}`}
                      className="h-12 w-12 shrink-0 rounded object-cover"
                    />
                  )}
                  <span className="flex min-w-0 flex-1 items-center gap-1 text-xs text-muted-foreground">
                    {s.tipo === "video" && <Video className="h-3 w-3 shrink-0" aria-hidden="true" />}
                    <span className="truncate">{s.objeto}</span>
                    {i === idxPortada && (
                      <span className="inline-flex shrink-0 items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-[10px] font-medium text-foreground">
                        <Star className="h-2.5 w-2.5" aria-hidden="true" />
                        Portada
                      </span>
                    )}
                  </span>
                </div>
              </FilaConAcciones>
            );
          })}
        </ul>
      )}
    </div>
  );
}
