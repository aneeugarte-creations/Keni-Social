/**
 * Sugerencia de hashtags en línea, estilo autocompletado (VS Code / Copilot).
 *
 * UN SOLO bloque mientras al copy le FALTE algo y la pieza no esté publicada. Dentro conviven los
 * dos sistemas, no en dos mensajes separados:
 *
 *  - LÍNEA (rojo): el hashtag de la categoría de la pieza (`hashtags_linea`). Es la firma de
 *    la sección y SIN él las analíticas no trackean bien por línea, así que se pinta en ROJO. Es
 *    OBLIGATORIO: se recalcula del copy en cada render, así que si se borra a mano REAPARECE; no se
 *    puede descartar.
 *  - SUGERIDOS (gris): los hashtags habituales de la marca + temáticos (`hashtags_sugeridos`), como
 *    texto fantasma. Son OPCIONALES: se ofrecen mientras falte alguno y se pueden descartar de un
 *    clic; descartarlos NO oculta el de la línea.
 *
 * El ✓ añade de una sola vez todo lo que aún falta (el de la línea PRIMERO), en la misma línea de
 * hashtags del copy. La decisión es del humano: nada se inyecta solo. En piezas publicadas no aparece.
 */
import { AlertTriangle, Check, Hash, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { contieneHashtag, normalizarHashtag } from "@/pages/piezas/hashtags";
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

  // El de la LÍNEA es obligatorio (no se descarta) y reaparece si se borra: se recalcula del copy
  // en cada render. Los SUGERIDOS son opcionales: el ✗ los oculta (sin tocar el de la línea), y nunca
  // duplican el de la línea.
  const faltanLinea = linea.filter((t) => !contieneHashtag(contenido, t));
  const cuerposLinea = new Set(faltanLinea.map((t) => normalizarHashtag(t).toLowerCase()));
  const faltanSugeridos = descartado
    ? []
    : sugeridos.filter(
        (t) =>
          !contieneHashtag(contenido, t) &&
          !cuerposLinea.has(normalizarHashtag(t).toLowerCase()),
      );

  if (publicada || (faltanLinea.length === 0 && faltanSugeridos.length === 0)) {
    return null;
  }

  const hayLinea = faltanLinea.length > 0;
  // El de la línea PRIMERO: al aceptar todo, se añade el obligatorio antes que los sugeridos.
  const faltantes = [...faltanLinea, ...faltanSugeridos];

  return (
    <div
      className={cn(
        "rounded-md border border-dashed p-2.5",
        hayLinea
          ? "border-red-400/70 bg-red-50/60 dark:bg-red-950/20"
          : "border-border bg-muted/20",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "flex items-center gap-1.5 text-xs font-medium",
            hayLinea ? "text-red-600 dark:text-red-400" : "text-muted-foreground",
          )}
        >
          {hayLinea ? (
            <AlertTriangle className="h-3.5 w-3.5" />
          ) : (
            <Hash className="h-3.5 w-3.5" />
          )}
          {hayLinea ? "Falta hashtag de la línea" : "Sugeridos"}
        </span>
        {/* Una sola línea de hashtags: el de la línea en ROJO (obligatorio) junto a los sugeridos
            en gris, no en dos mensajes separados. */}
        <p className="min-w-0 flex-1 font-mono text-sm">
          {faltanLinea.map((t) => (
            <span key={`l-${t}`} className="text-red-600 dark:text-red-400">
              {t}{" "}
            </span>
          ))}
          {faltanSugeridos.map((t) => (
            <span key={`s-${t}`} className="text-muted-foreground/70">
              {t}{" "}
            </span>
          ))}
        </p>
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className={cn(
              "h-7 w-7",
              hayLinea
                ? "text-red-600 hover:text-red-700"
                : "text-emerald-600 hover:text-emerald-700",
            )}
            aria-label="Aceptar hashtags"
            title="Añadir los hashtags que faltan"
            onClick={() => onAceptar(faltantes)}
          >
            <Check className="h-4 w-4" />
          </Button>
          {/* Descartar solo aplica a los OPCIONALES: el de la línea no se puede ocultar. */}
          {faltanSugeridos.length > 0 && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
              aria-label="Rechazar hashtags sugeridos"
              title="Rechazar sugeridos"
              onClick={() => setDescartado(true)}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {hayLinea && (
        <p className="mt-1 text-xs text-red-600/80 dark:text-red-400/80">
          Sin el hashtag de la línea las analíticas no pueden trackear bien el contenido por
          sección.
        </p>
      )}
    </div>
  );
}
