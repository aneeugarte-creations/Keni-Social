/**
 * Selectores GLOBALES de RED y LÍNEA editorial en la barra superior, hermanos del
 * switch de MARCA (`SwitchMarca`). Filtran toda la superficie de contenido/feed: el
 * Feed de ideación, la Lista de contenido y la Programación leen su valor del contexto
 * global (`useFiltrosContenido`) en vez de tener dropdowns propios.
 *
 * VISIBILIDAD CONTEXTUAL: el provider es global, pero estos selectores solo se pintan
 * en las rutas donde aplican (`rutaUsaFiltrosContenido`). En métricas, ajustes, usuarios,
 * etc. NO aparecen, para no añadir ruido a la topbar.
 */
import { Filter } from "lucide-react";
import { useLocation } from "react-router-dom";

import { SelectorRed } from "@/components/comunes/SelectorRed";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  FILTRO_TODOS,
  rutaUsaFiltrosContenido,
  useFiltrosContenido,
} from "@/hooks/filtros-contenido-contexto";

export function SwitchFiltrosContenido() {
  const { pathname } = useLocation();
  const { red, linea, redes, lineasElegibles, cambiarRed, cambiarLinea } = useFiltrosContenido();

  // Solo en las rutas de contenido/feed que usan estos filtros (Feed, Lista, Programación).
  if (!rutaUsaFiltrosContenido(pathname)) return null;

  return (
    <div className="hidden items-center gap-1.5 sm:flex">
      <SelectorRed
        redes={redes}
        valor={red}
        onCambio={cambiarRed}
        ariaLabel="Filtrar por red"
        className="h-8 w-[150px]"
      />
      <Select value={linea} onValueChange={cambiarLinea}>
        <SelectTrigger aria-label="Filtrar por línea editorial" className="h-8 w-[170px] gap-1.5">
          <Filter className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden="true" />
          <SelectValue placeholder="Línea editorial" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={FILTRO_TODOS}>Todas las líneas</SelectItem>
          {lineasElegibles.map((l) => (
            <SelectItem key={l.id} value={l.id}>
              {l.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
