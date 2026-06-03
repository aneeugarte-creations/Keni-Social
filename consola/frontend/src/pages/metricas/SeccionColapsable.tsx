/**
 * Sección colapsable compartida del dashboard de Métricas.
 *
 * Envuelve cualquier tabla/gráfica en una `Card` con cabecera clicable (chevron) que
 * pliega/despliega el contenido. Unifica TODAS las secciones de Analíticas: mismo
 * patrón de título, controles (filtros) a la derecha y colapso. Sin dependencias nuevas
 * (estado local); por defecto abierta.
 *
 * Uso:
 *   <SeccionColapsable titulo="Detalle por red" acciones={<SelectRed .../>} contentClassName="p-0">
 *     <Table>…</Table>
 *   </SeccionColapsable>
 *
 * `acciones` (filtros/controles) NO togglea el colapso (clic aislado del trigger).
 */
import { ChevronDown } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function SeccionColapsable({
  titulo,
  descripcion,
  icono: Icono,
  acciones,
  defaultAbierto = true,
  contentClassName,
  children,
}: {
  titulo: React.ReactNode;
  descripcion?: React.ReactNode;
  /** Icono opcional junto al título (lucide). */
  icono?: LucideIcon;
  /** Controles a la derecha de la cabecera (filtros, toggles, descargas…). */
  acciones?: React.ReactNode;
  defaultAbierto?: boolean;
  /** Clase para el `CardContent` (p. ej. "p-0" para tablas a sangre). */
  contentClassName?: string;
  children: React.ReactNode;
}) {
  const [abierto, setAbierto] = React.useState(defaultAbierto);
  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setAbierto((v) => !v)}
            aria-expanded={abierto}
            className="group flex min-w-0 items-center gap-2 text-left focus-visible:outline-none"
          >
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:text-foreground",
                !abierto && "-rotate-90",
              )}
              aria-hidden="true"
            />
            {Icono ? (
              <Icono className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            ) : null}
            <CardTitle className="truncate text-base group-hover:underline">{titulo}</CardTitle>
          </button>
          {acciones ? (
            <div className="flex flex-wrap items-center gap-2">{acciones}</div>
          ) : null}
        </div>
        {descripcion && abierto ? (
          <p className="text-sm text-muted-foreground">{descripcion}</p>
        ) : null}
      </CardHeader>
      {abierto ? (
        <CardContent className={cn("pt-0", contentClassName)}>{children}</CardContent>
      ) : null}
    </Card>
  );
}
