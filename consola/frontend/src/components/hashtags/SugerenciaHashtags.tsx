/**
 * Sugerencia de hashtags en línea, estilo autocompletado (VS Code / Copilot).
 *
 * Al revisar una pieza para ponerle la foto, si el copy NO lleva hashtags la máquina ya
 * dejó preparados los más habituales de la marca (etapa `sugerir_hashtags`, sacados del
 * historial). Aquí se ofrecen en GRIS, como texto fantasma, con un ✓ para aceptarlos de
 * un clic (se añaden al final del copy) y una ✗ para descartarlos. La decisión es del
 * humano: nada se inyecta solo.
 *
 * Solo aparece cuando FALTAN hashtags en el copy ACTUAL: en cuanto el copy lleva alguno
 * (porque se aceptó la sugerencia o se escribió a mano) desaparece. Tampoco aparece en
 * piezas ya publicadas (solo lectura).
 */
import { Check, Hash, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { textoTieneHashtags } from "@/pages/feed/etapa";
import type { Pieza } from "@/types";

export interface SugerenciaHashtagsProps {
  /** Copy ACTUAL del editor (no el de la pieza guardada): si ya lleva hashtags, no se sugiere. */
  contenido: string;
  /** Pieza en edición (de ella salen `hashtags_sugeridos` y el estado de publicación). */
  pieza: Pieza;
  /** Acepta la sugerencia: el padre añade los hashtags al copy (un solo clic). */
  onAceptar: (hashtags: string[]) => void;
}

export function SugerenciaHashtags({ contenido, pieza, onAceptar }: SugerenciaHashtagsProps) {
  const [descartado, setDescartado] = React.useState(false);

  const sugeridos = pieza.hashtags_sugeridos ?? [];
  const publicada = pieza.estado === "publicado";

  // Nada que ofrecer si: no hay sugerencias, ya se descartó, la pieza está publicada o el
  // copy YA lleva hashtags (los puso la sugerencia o el equipo a mano).
  if (descartado || publicada || sugeridos.length === 0 || textoTieneHashtags(contenido)) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed border-border bg-muted/20 p-2.5">
      <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Hash className="h-3.5 w-3.5" />
        Sugeridos
      </span>
      {/* Texto fantasma: los hashtags propuestos en gris, como un autocompletado por aceptar. */}
      <p className="min-w-0 flex-1 font-mono text-sm text-muted-foreground/70">
        {sugeridos.join(" ")}
      </p>
      <div className="ml-auto flex items-center gap-1">
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-7 w-7 text-emerald-600 hover:text-emerald-700"
          aria-label="Aceptar hashtags sugeridos"
          title="Aceptar"
          onClick={() => onAceptar(sugeridos)}
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
  );
}
