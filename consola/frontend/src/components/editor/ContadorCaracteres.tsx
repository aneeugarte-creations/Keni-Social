/**
 * Contador de caracteres por red con su límite.
 *
 * Muestra `123 / 280`; el conteo se pone en rojo si excede el límite (p. ej.
 * X=280). Para redes sin límite duro (Facebook, YouTube) solo muestra el conteo.
 * Reutilizado por `ResultadoRedes` y `DialogoEditar`.
 */
import { cn } from "@/lib/utils";

export interface ContadorCaracteresProps {
  /** Número de caracteres actuales. */
  caracteres: number;
  /** Límite duro de la red, o `null` si no tiene. */
  limite: number | null;
  className?: string;
}

export function ContadorCaracteres({ caracteres, limite, className }: ContadorCaracteresProps) {
  const excede = limite !== null && caracteres > limite;
  return (
    <span
      className={cn(
        "text-xs tabular-nums",
        excede ? "font-medium text-red-600 dark:text-red-400" : "text-muted-foreground",
        className,
      )}
      aria-live="polite"
    >
      {caracteres.toLocaleString("es-MX")}
      {limite !== null && ` / ${limite.toLocaleString("es-MX")}`}
    </span>
  );
}
