/**
 * Control de pie "Ver las N … / Mostrar menos" para las tablas plegables de Métricas.
 * Componente de UI puro (espejo de `CabeceraOrdenable`): va como `TableFooter` a ancho
 * completo, debajo del cuerpo (y de la fila de Total, que se renderiza aparte y NO se
 * recorta). Gesto ghost + ChevronDown que rota.
 */
import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TableCell, TableFooter, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export function PieMostrarMas({
  expandido,
  onAlternar,
  colSpan,
}: {
  expandido: boolean;
  onAlternar: () => void;
  /** Nº de columnas de la tabla, para el `<td colSpan>` del footer. */
  colSpan: number;
}) {
  return (
    <TableFooter className="bg-transparent">
      <TableRow className="hover:bg-transparent">
        <TableCell colSpan={colSpan} className="p-0">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onAlternar}
            aria-expanded={expandido}
            className="w-full justify-center font-normal text-muted-foreground hover:text-foreground"
          >
            {expandido ? "Mostrar menos" : "Mostrar más"}
            <ChevronDown
              className={cn("h-4 w-4 transition-transform", expandido && "rotate-180")}
              aria-hidden="true"
            />
          </Button>
        </TableCell>
      </TableRow>
    </TableFooter>
  );
}
