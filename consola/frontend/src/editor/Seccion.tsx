// Acordeón simple reutilizable para el Inspector: título + chevron + contenido colapsable.
// Estado local (useState) para no remontar los inputs hijos en cada render del panel (eso
// perdería el foco al teclear; mismo motivo que la "fila como función" del panel de capas).
// El contenido se MONTA siempre y se oculta con `hidden` cuando está cerrado, de modo que los
// inputs no se desmontan/remontan al plegar (no se pierde foco ni estado interno).

import { ChevronDown } from "lucide-react";
import { useState } from "react";

export function Seccion({
  titulo,
  defaultAbierta = false,
  children,
}: {
  titulo: string;
  defaultAbierta?: boolean;
  children: React.ReactNode;
}) {
  const [abierta, setAbierta] = useState(defaultAbierta);
  return (
    <div className="border-t border-border pt-3">
      <button
        type="button"
        onClick={() => setAbierta((v) => !v)}
        className="flex w-full items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
        aria-expanded={abierta}
      >
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${abierta ? "" : "-rotate-90"}`}
        />
        <span>{titulo}</span>
      </button>
      <div className={`mt-2 flex flex-col gap-2 ${abierta ? "" : "hidden"}`}>{children}</div>
    </div>
  );
}
