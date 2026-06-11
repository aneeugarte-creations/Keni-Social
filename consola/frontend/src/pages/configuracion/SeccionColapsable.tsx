import { ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/** Sección COLAPSABLE de ajustes, en la CAPA BASE del panel (sin tarjeta ni caja anidada): una
 *  cabecera clicable (título + descripción + chevron) separada de la anterior por una línea fina,
 *  que pliega/despliega su contenido. Es la unidad de «área» de los paneles de ajustes: varias
 *  secciones se apilan planas dentro del panel lateral, cada una recuerda su estado mientras la
 *  página está montada. `abiertaInicial` deja abierta la más importante; `acento="amber"` tiñe la
 *  cabecera de las áreas peligrosas (publicación real). */
export function SeccionColapsable({
  titulo,
  descripcion,
  abiertaInicial = false,
  acento,
  contentClassName,
  children,
}: {
  titulo: string;
  descripcion?: React.ReactNode;
  abiertaInicial?: boolean;
  /** Acento de la cabecera para áreas que merecen señal visual (p. ej. publicación real). */
  acento?: "amber";
  contentClassName?: string;
  children: React.ReactNode;
}) {
  const [abierta, setAbierta] = React.useState(abiertaInicial);
  const alternar = () => setAbierta((v) => !v);
  return (
    <section className="border-t border-border first:border-t-0">
      <div
        role="button"
        tabIndex={0}
        aria-expanded={abierta}
        onClick={alternar}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            alternar();
          }
        }}
        className="flex cursor-pointer select-none items-start justify-between gap-3 py-3"
      >
        <div className="min-w-0">
          <h3
            className={cn(
              "text-sm font-semibold tracking-tight",
              acento === "amber" && "text-amber-700 dark:text-amber-400",
            )}
          >
            {titulo}
          </h3>
          {descripcion && <p className="mt-0.5 text-xs text-muted-foreground">{descripcion}</p>}
        </div>
        <ChevronDown
          aria-hidden
          className={cn(
            "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            abierta && "rotate-180",
          )}
        />
      </div>
      {abierta && <div className={cn("pb-4", contentClassName)}>{children}</div>}
    </section>
  );
}
