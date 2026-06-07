/**
 * Página del Estudio de Video — SHELL (sin motor de edición).
 *
 * Muestra una previsualización del video (subida + preview, reutilizando EditorVideo)
 * y un área reservada para el motor de edición que se añadirá en una iteración futura.
 * El equipo puede navegar aquí, subir un clip y previsualizar; la edición avanzada
 * (cortes, títulos, efectos) se marcará como «próximamente» hasta que el motor esté listo.
 */

import { useState } from "react";
import { Clapperboard } from "lucide-react";

import { EditorVideo } from "@/components/media/EditorVideo";

export default function EstudioVideo() {
  // Estado del video: clave en el almacén + URL de previsualización.
  const [videoKey, setVideoKey] = useState("");
  const [videoUrl, setVideoUrl] = useState("");

  function onCambioVideo(clave: string, url: string) {
    setVideoKey(clave);
    setVideoUrl(url);
  }

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col">
      {/* Cabecera de página */}
      <div className="flex items-center gap-2 border-b border-border p-3">
        <Clapperboard className="h-4 w-4 text-muted-foreground" />
        <h1 className="text-base font-semibold">Editor de video</h1>
        <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          Próximamente
        </span>
      </div>

      {/* Cuerpo principal: dos columnas en escritorio */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto grid max-w-5xl gap-6 p-4 sm:p-6 lg:grid-cols-2">
          {/* Columna izquierda: previsualización del clip */}
          <section className="space-y-4">
            <h2 className="text-sm font-semibold text-foreground">Clip de video</h2>
            <EditorVideo
              video={videoKey}
              videoUrl={videoUrl}
              onCambio={onCambioVideo}
            />
          </section>

          {/* Columna derecha: motor de edición (reservado) */}
          <section className="space-y-4" aria-label="Motor de edición de video — próximamente">
            <h2 className="text-sm font-semibold text-foreground">Edición</h2>
            <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-muted/20 p-6 text-center">
              <Clapperboard className="h-8 w-8 text-muted-foreground/50" aria-hidden />
              <p className="text-sm font-medium text-muted-foreground">
                Motor de edición de video
              </p>
              <p className="max-w-xs text-xs text-muted-foreground/70">
                Recorte, títulos y efectos — próximamente. Por ahora puedes subir tu clip
                y previsualizar cómo quedará en la publicación.
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
