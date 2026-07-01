/**
 * Icono "i" de ayuda contextual: al hacer clic despliega una explicación breve
 * del concepto (qué es una métrica, cómo se calcula, qué significa una gráfica).
 *
 * A diferencia de `Tooltip` (etiqueta corta en una línea, por hover/foco), este
 * componente es para texto de varias frases y se abre con CLIC — funciona igual
 * en pantallas táctiles, donde no hay hover. Se cierra al clicar fuera o con
 * Escape, como `MenuColumnas`. Portal sobre `<body>` (fixed) para no recortarse
 * en contenedores con overflow ni quedar atrapado en un diálogo/popover padre.
 */
import { Info } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

export function AyudaInfo({
  texto,
  etiqueta = "Más información",
  className,
}: {
  /** Explicación a mostrar (puede ser una o varias frases). */
  texto: string;
  /** Nombre accesible del botón (por defecto genérico; especificarlo cuando haya varios en la misma vista). */
  etiqueta?: string;
  className?: string;
}) {
  const [abierto, setAbierto] = React.useState(false);
  const anclaRef = React.useRef<HTMLButtonElement>(null);
  const [pos, setPos] = React.useState<{ x: number; y: number } | null>(null);

  React.useEffect(() => {
    if (!abierto) return;
    const el = anclaRef.current;
    if (el) {
      const r = el.getBoundingClientRect();
      setPos({ x: r.left, y: r.bottom + 6 });
    }
    const alClicFuera = (e: MouseEvent) => {
      if (anclaRef.current && !anclaRef.current.contains(e.target as Node)) setAbierto(false);
    };
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("mousedown", alClicFuera);
    document.addEventListener("keydown", alEscape);
    return () => {
      document.removeEventListener("mousedown", alClicFuera);
      document.removeEventListener("keydown", alEscape);
    };
  }, [abierto]);

  if (!texto) return null;

  return (
    <button
      ref={anclaRef}
      type="button"
      aria-label={etiqueta}
      aria-expanded={abierto}
      onClick={() => setAbierto((v) => !v)}
      className={cn(
        "inline-flex shrink-0 text-muted-foreground/70 hover:text-muted-foreground focus-visible:text-muted-foreground",
        className,
      )}
    >
      <Info className="h-3.5 w-3.5" aria-hidden="true" />
      {abierto &&
        pos &&
        createPortal(
          <p
            role="tooltip"
            style={{ left: pos.x, top: pos.y }}
            className="fixed z-[100] w-64 rounded-md border border-border bg-popover p-3 text-xs text-popover-foreground shadow-md"
          >
            {texto}
          </p>,
          document.body,
        )}
    </button>
  );
}
