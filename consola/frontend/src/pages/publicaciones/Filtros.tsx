import { Sprout } from "lucide-react";

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

/** Valor que representa "todos" en cada filtro (sin filtrar). */
export const FILTRO_TODOS = "__todos__";

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
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      <Select value={marca} onValueChange={onMarca}>
        <SelectTrigger className="w-full sm:w-[180px]" aria-label="Filtrar por marca">
          <SelectValue placeholder="Marca" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={FILTRO_TODOS}>Todas las marcas</SelectItem>
          {opciones.marcas.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              {m.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={red} onValueChange={onRed}>
        <SelectTrigger className="w-full sm:w-[160px]" aria-label="Filtrar por red">
          <SelectValue placeholder="Red" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={FILTRO_TODOS}>Todas las redes</SelectItem>
          {opciones.redes.map((r) => (
            <SelectItem key={r.id} value={r.id}>
              {r.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

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
