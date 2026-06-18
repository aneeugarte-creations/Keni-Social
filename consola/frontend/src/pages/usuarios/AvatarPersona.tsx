import { hexAlpha, iniciales, metaZona, nombreVisible } from "@/lib/organigrama";
import { cn } from "@/lib/utils";
import { type UsuarioAdmin } from "@/types";

/**
 * Avatar de una persona tintado con el color de su ZONA (marca/transversal/dirección). Es el
 * único elemento con color en las filas de la tabla y la cabecera del detalle; muestra las
 * iniciales del nombre visible como fallback.
 */
export function AvatarPersona({
  usuario,
  zona,
  className,
}: {
  usuario: UsuarioAdmin;
  /** Zona de la persona (de aquí sale el color); se calcula con `zonaDe`. */
  zona: string;
  className?: string;
}) {
  const color = metaZona(zona).color;
  return (
    <span
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
        className,
      )}
      style={{ color, backgroundColor: hexAlpha(color, 0.14) }}
      aria-hidden
    >
      {iniciales(nombreVisible(usuario))}
    </span>
  );
}
