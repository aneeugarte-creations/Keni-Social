import { Sprout } from "lucide-react";

import { SelectorRed } from "@/components/comunes/SelectorRed";
import { MARCA_TODAS } from "@/components/comunes/selectores";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { OpcionesPublicaciones } from "@/types";

/**
 * Valor que representa "todos / sin filtrar". Es el mismo centinela único
 * (`MARCA_TODAS`) que usan los selectores compartidos, de modo que marca, red y
 * estado comparten una sola constante.
 */
export const FILTRO_TODOS = MARCA_TODAS;

/**
 * Filtros de red, estado y "solo evergreens". Notifica los cambios hacia arriba.
 *
 * La MARCA NO se filtra aquí: la manda SIEMPRE el switch global de la barra
 * superior (`useMarcaActiva`), así que esta barra no tiene selector de marca.
 */
export function FiltrosPublicaciones({
  opciones,
  red,
  estado,
  soloEvergreens,
  onRed,
  onEstado,
  onSoloEvergreens,
}: {
  opciones: OpcionesPublicaciones;
  red: string;
  estado: string;
  soloEvergreens: boolean;
  onRed: (v: string) => void;
  onEstado: (v: string) => void;
  onSoloEvergreens: (v: boolean) => void;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      <SelectorRed
        redes={opciones.redes}
        valor={red}
        onCambio={onRed}
        ariaLabel="Filtrar por red"
        className="w-full sm:w-[160px]"
      />

      <Select value={estado} onValueChange={onEstado}>
        <SelectTrigger className="w-full sm:w-[160px]" aria-label="Filtrar por estado">
          <SelectValue placeholder="Estado" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={FILTRO_TODOS}>Todos los estados</SelectItem>
          {opciones.estados.map((e) => (
            <SelectItem key={e.id} value={e.id}>
              {e.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Label
        htmlFor="filtro-evergreens"
        className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm font-normal"
      >
        <Checkbox
          id="filtro-evergreens"
          checked={soloEvergreens}
          onCheckedChange={onSoloEvergreens}
          aria-label="Mostrar solo publicaciones evergreens"
        />
        <span className="inline-flex items-center gap-1">
          <Sprout className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          Solo evergreens
        </span>
      </Label>
    </div>
  );
}
