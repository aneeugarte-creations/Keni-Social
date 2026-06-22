/**
 * Sugerencia de hashtags en línea, estilo autocompletado (VS Code / Copilot).
 *
 * Dos bloques, ambos solo mientras al copy le FALTE algo y la pieza no esté publicada:
 *
 *  - LÍNEA (rojo): el hashtag de la línea editorial de la pieza (`hashtags_linea`). Es la firma
 *    de la sección y SIN él las analíticas no pueden trackear bien por línea, así que se avisa en
 *    rojo. Se ofrece mientras el caption no lo lleve; el gate `falta_hashtags` lo exige.
 *  - SUGERIDOS (gris): los hashtags habituales de la marca + temáticos (`hashtags_sugeridos`),
 *    como texto fantasma. Se siguen ofreciendo mientras falte alguno —aunque el copy ya lleve
 *    otros hashtags distintos— y se pueden descartar de un clic.
 *
 * Cada bloque acepta SOLO lo que aún falta (un clic lo añade al final del copy). La decisión es
 * del humano: nada se inyecta solo. En piezas ya publicadas (solo lectura) no aparece.
 */
import { AlertTriangle, Check, Hash, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { contieneHashtag } from "@/pages/piezas/hashtags";
import type { Pieza } from "@/types";

export interface SugerenciaHashtagsProps {
  /** Copy ACTUAL del editor (no el de la pieza guardada): de él se deriva qué falta. */
  contenido: string;
  /** Pieza en edición (de ella salen `hashtags_sugeridos`, `hashtags_linea` y el estado). */
  pieza: Pieza;
  /** Acepta hashtags: el padre los añade al copy (un solo clic). */
  onAceptar: (hashtags: string[]) => void;
}

export function SugerenciaHashtags({ contenido, pieza, onAceptar }: SugerenciaHashtagsProps) {
  const [descartado, setDescartado] = React.useState(false);

  const publicada = pieza.estado === "publicado";
  const linea = pieza.hashtags_linea ?? [];
  const sugeridos = pieza.hashtags_sugeridos ?? [];

  // Solo lo que el copy AÚN no lleva (así el bloque sigue ofreciendo lo que falta aunque el copy
  // ya tenga otros hashtags distintos a los sugeridos).
  const faltanLinea = linea.filter((t) => !contieneHashtag(contenido, t));
  const faltanSugeridos = descartado
    ? []
    : sugeridos.filter((t) => !contieneHashtag(contenido, t));

  if (publicada || (faltanLinea.length === 0 && faltanSugeridos.length === 0)) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2">
      {faltanLinea.length > 0 && (
        <div className="rounded-md border border-dashed border-red-400/70 bg-red-50/60 p-2.5 dark:bg-red-950/20">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 text-xs font-medium text-red-600 dark:text-red-400">
              <AlertTriangle className="h-3.5 w-3.5" />
              Hashtag de la línea
            </span>
            <p className="min-w-0 flex-1 font-mono text-sm text-red-600 dark:text-red-400">
              {faltanLinea.join(" ")}
            </p>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="ml-auto h-7 w-7 text-red-600 hover:text-red-700"
              aria-label="Aceptar hashtag de la línea"
              title="Añadir el hashtag de la línea"
              onClick={() => onAceptar(faltanLinea)}
            >
              <Check className="h-4 w-4" />
            </Button>
          </div>
          <p className="mt-1 text-xs text-red-600/80 dark:text-red-400/80">
            Sin el hashtag de la línea las analíticas no pueden trackear bien el contenido por
            sección.
          </p>
        </div>
      )}

      {faltanSugeridos.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed border-border bg-muted/20 p-2.5">
          <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Hash className="h-3.5 w-3.5" />
            Sugeridos
          </span>
          {/* Texto fantasma: los hashtags propuestos en gris, como un autocompletado por aceptar. */}
          <p className="min-w-0 flex-1 font-mono text-sm text-muted-foreground/70">
            {faltanSugeridos.join(" ")}
          </p>
          <div className="ml-auto flex items-center gap-1">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-7 w-7 text-emerald-600 hover:text-emerald-700"
              aria-label="Aceptar hashtags sugeridos"
              title="Aceptar"
              onClick={() => onAceptar(faltanSugeridos)}
            >
              <Check className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
              aria-label="Rechazar hashtags sugeridos"
              title="Rechazar"
              onClick={() => setDescartado(true)}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
