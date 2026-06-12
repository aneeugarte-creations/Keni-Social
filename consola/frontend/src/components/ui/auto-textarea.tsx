/**
 * Textarea que crece automáticamente con su contenido.
 *
 * Mismo estilo base que `Textarea`, pero ajusta su alto al contenido (sin
 * scroll interno) entre `min-h` y un máximo opcional. Reenvía la ref para que
 * la barra de formato pueda insertar Markdown en la selección.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

export interface AutoTextareaProps extends React.ComponentProps<"textarea"> {
  /** Alto máximo en píxeles antes de mostrar scroll. Sin límite si se omite. */
  maxHeight?: number;
}

const AutoTextarea = React.forwardRef<HTMLTextAreaElement, AutoTextareaProps>(
  ({ className, maxHeight, value, onChange, ...props }, ref) => {
    const interna = React.useRef<HTMLTextAreaElement | null>(null);

    // Combina la ref reenviada con la interna para poder medir/escribir.
    const fijarRef = React.useCallback(
      (nodo: HTMLTextAreaElement | null) => {
        interna.current = nodo;
        if (typeof ref === "function") ref(nodo);
        else if (ref) ref.current = nodo;
      },
      [ref],
    );

    const ajustar = React.useCallback(() => {
      const el = interna.current;
      if (!el) return;
      el.style.height = "auto";
      const alto = maxHeight ? Math.min(el.scrollHeight, maxHeight) : el.scrollHeight;
      el.style.height = `${alto}px`;
      el.style.overflowY = maxHeight && el.scrollHeight > maxHeight ? "auto" : "hidden";
    }, [maxHeight]);

    // Reajusta cuando cambia el valor controlado (incluye inserciones externas).
    React.useLayoutEffect(() => {
      ajustar();
    }, [ajustar, value]);

    return (
      <textarea
        ref={fijarRef}
        value={value}
        onChange={(e) => {
          onChange?.(e);
          ajustar();
        }}
        rows={1}
        className={cn(
          // `text-base md:text-sm`: 16px en móvil (evita el auto-zoom de iOS al enfocar) y 14px en
          // escritorio. Mismo motivo que en `Input`/`Textarea`.
          "flex min-h-[80px] w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        {...props}
      />
    );
  },
);
AutoTextarea.displayName = "AutoTextarea";

export { AutoTextarea };
