import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { iconoRed } from "../publicaciones/meta";

/** id de red usado en `htmlFor`/`id` (sin colisiones con otros campos). */
function idCheck(red: string): string {
  return `red-${red}`;
}

/**
 * Grupo de checkboxes para elegir las redes objetivo de la generación.
 * Las opciones (id + nombre) vienen del backend; el icono lo añade `meta.ts`.
 */
export function SelectorRedes({
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
    <div className="space-y-1.5">
      <Label>Redes</Label>
      <div className="flex flex-wrap gap-x-5 gap-y-2.5">
        {opciones.map((red) => {
          const Icono = iconoRed(red.id);
          const id = idCheck(red.id);
          return (
            <div key={red.id} className="flex items-center gap-2">
              <Checkbox
                id={id}
                checked={seleccionadas.has(red.id)}
                onCheckedChange={(v) => onCambio(red.id, v)}
                disabled={disabled}
                aria-label={red.nombre}
              />
              <Label
                htmlFor={id}
                className="flex cursor-pointer items-center gap-1.5 font-normal"
              >
                <Icono className="h-4 w-4 text-muted-foreground" />
                {red.nombre}
              </Label>
            </div>
          );
        })}
      </div>
    </div>
  );
}
