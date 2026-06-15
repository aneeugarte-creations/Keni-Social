import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

import { iconoRed } from "@/pages/publicaciones/meta";

/**
 * Selector de redes objetivo como chips (pastillas) de selección MÚLTIPLE.
 *
 * Convive con `SelectorRed` (dropdown de selección ÚNICA): el sufijo `Multiple`
 * los distingue para evitar confundir los imports. Este es el de chips.
 *
 * Sobrio, sin casillas: seleccionada = relleno gris sutil + texto en foreground;
 * sin seleccionar = solo contorno + gris. Las opciones vienen del backend.
 */
export function SelectorRedMultiple({
  opciones,
  seleccionadas,
  onCambio,
  disabled,
}: {
  opciones: { id: string; nombre: string }[];
  seleccionadas: Set<string>;
  onCambio: (red: string, marcada: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-2">
      <Label>Redes</Label>
      <div className="flex flex-wrap gap-2">
        {opciones.map((red) => {
          const Icono = iconoRed(red.id);
          const activa = seleccionadas.has(red.id);
          return (
            <button
              key={red.id}
              type="button"
              role="checkbox"
              aria-checked={activa}
              aria-label={red.nombre}
              disabled={disabled}
              onClick={() => onCambio(red.id, !activa)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
                activa
                  ? "border-foreground/20 bg-accent font-medium text-foreground"
                  : "border-border font-normal text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Icono
                className={cn("h-4 w-4", activa ? "text-foreground" : "text-muted-foreground")}
              />
              {red.nombre}
            </button>
          );
        })}
      </div>
    </div>
  );
}
