/**
 * Cabecera de columna ordenable para las tablas de Métricas.
 *
 * Envuelve `<TableHead>` en un botón accesible: clic alterna asc/desc, muestra un
 * indicador visual (flecha) de la columna activa y refleja `aria-sort` para
 * lectores de pantalla. Reutilizable por TablaCuentas, TablaRedes, Crosstab y
 * DesgloseInteracciones sin añadir dependencias nuevas.
 */
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";

import type { DireccionOrden } from "./useOrdenTabla";

export function CabeceraOrdenable({
  children,
  activa,
  direccion,
  onClick,
  alinear = "left",
  className,
}: {
  children: React.ReactNode;
  /** True si esta columna es la que ordena ahora mismo. */
  activa: boolean;
  direccion: DireccionOrden;
  onClick: () => void;
  /** Alineación del contenido (numéricas a la derecha). */
  alinear?: "left" | "right";
  className?: string;
}) {
  const ariaSort = activa ? (direccion === "asc" ? "ascending" : "descending") : "none";
  const Icono = !activa ? ChevronsUpDown : direccion === "asc" ? ArrowUp : ArrowDown;

  return (
    <TableHead aria-sort={ariaSort} className={className}>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "group inline-flex w-full items-center gap-1 rounded-sm text-sm font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
          alinear === "right" ? "justify-end" : "justify-start",
        )}
      >
        <span className={cn(alinear === "right" && "order-2")}>{children}</span>
        <Icono
          className={cn(
            "h-3.5 w-3.5 shrink-0 transition-opacity",
            activa ? "opacity-100" : "opacity-40 group-hover:opacity-70 group-focus-visible:opacity-70",
            alinear === "right" && "order-1",
          )}
          aria-hidden="true"
        />
      </button>
    </TableHead>
  );
}
