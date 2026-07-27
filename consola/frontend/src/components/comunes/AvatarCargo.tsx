import { degradadoCargo, metaCargo } from "@/lib/cargo-colores";
import { cn } from "@/lib/utils";
import type { CargoUsuario } from "@/types";

/**
 * Avatar de degradado de una persona (mismo estilo que el de la cuenta en la barra lateral),
 * teñido por la FAMILIA de su cargo: dirección, coordinación, contenido, editorial, creativo
 * o foto. El tooltip nombra la familia; el cargo exacto lo dice la fila, así que para el
 * lector de pantalla el punto es decorativo.
 */
export function AvatarCargo({
  cargo,
  className,
}: {
  cargo: CargoUsuario | null | undefined;
  className?: string;
}) {
  return (
    <span
      title={metaCargo(cargo).etiqueta}
      aria-hidden="true"
      className={cn("h-7 w-7 shrink-0 rounded-full ring-1 ring-border", className)}
      style={{ backgroundImage: degradadoCargo(cargo) }}
    />
  );
}
