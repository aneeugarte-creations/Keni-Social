import { Sprout } from "lucide-react";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
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

/** Filtros de marca, red, estado y "solo perennes". Notifica los cambios hacia arriba. */
export function FiltrosPublicaciones({
  opciones,
  marca,
  red,
  estado,
  soloPerennes,
  onMarca,
  onRed,
  onEstado,
  onSoloPerennes,
}: {
  opciones: OpcionesPublicaciones;
  marca: string;
  red: string;
  estado: string;
  soloPerennes: boolean;
  onMarca: (v: string) => void;
  onRed: (v: string) => void;
  onEstado: (v: string) => void;
  onSoloPerennes: (v: boolean) => void;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <SelectorMarca
        marcas={opciones.marcas}
        valor={marca}
        onCambio={onMarca}
        ariaLabel="Filtrar por marca"
        className="w-full sm:w-[180px]"
      />

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
        htmlFor="filtro-perennes"
        className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm font-normal"
      >
        <Checkbox
          id="filtro-perennes"
          checked={soloPerennes}
          onCheckedChange={onSoloPerennes}
          aria-label="Mostrar solo publicaciones perennes"
        />
        <span className="inline-flex items-center gap-1">
          <Sprout className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          Solo perennes
        </span>
      </Label>
    </div>
  );
}
