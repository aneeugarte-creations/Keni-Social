import { ChevronDown } from "lucide-react";
import * as React from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Tarjeta COLAPSABLE de configuración: cabecera clicable (título + descripción + chevron) que
 *  pliega/despliega el contenido. Reduce el ruido de una página muy llena; cada tarjeta recuerda
 *  su estado mientras la página está montada. `abiertaInicial` deja abierta la(s) más importante(s). */
export function TarjetaColapsable({
  titulo,
  descripcion,
  abiertaInicial = false,
  contentClassName = "pt-0",
  children,
}: {
  titulo: string;
  descripcion?: React.ReactNode;
  abiertaInicial?: boolean;
  contentClassName?: string;
  children: React.ReactNode;
}) {
  const [abierta, setAbierta] = React.useState(abiertaInicial);
  const alternar = () => setAbierta((v) => !v);
  return (
    <Card>
      <CardHeader
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
        className="cursor-pointer select-none pb-3"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">{titulo}</CardTitle>
            {descripcion && <CardDescription className="mt-1">{descripcion}</CardDescription>}
          </div>
          <ChevronDown
            aria-hidden
            className={cn(
              "mt-0.5 h-5 w-5 shrink-0 text-muted-foreground transition-transform",
              abierta && "rotate-180",
            )}
          />
        </div>
      </CardHeader>
      {abierta && <CardContent className={contentClassName}>{children}</CardContent>}
    </Card>
  );
}
