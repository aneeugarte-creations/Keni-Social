/**
 * Controles del dashboard: selectores reutilizables de marca y de rango.
 *
 * Se alimentan de `metricasOpciones()` y notifican el cambio hacia arriba para
 * que la página dispare el refetch del reporte / comparativa correspondiente.
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { MarcaDisponible, RangoMetrica } from "@/types";

/** Valor especial que representa "todas las marcas" en el selector. */
export const MARCA_TODAS = "todas";

interface SelectorMarcaProps {
  marcas: MarcaDisponible[];
  valor: string;
  onCambio: (valor: string) => void;
  id?: string;
}

export function SelectorMarca({ marcas, valor, onCambio, id }: SelectorMarcaProps) {
  return (
    <Select value={valor} onValueChange={onCambio}>
      <SelectTrigger id={id} className="w-full sm:w-[200px]" aria-label="Marca">
        <SelectValue placeholder="Marca" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={MARCA_TODAS}>Todas las marcas</SelectItem>
        {marcas.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.nombre}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

interface SelectorRangoProps {
  rangos: RangoMetrica[];
  valor: string;
  onCambio: (valor: string) => void;
  id?: string;
  ariaLabel?: string;
}

export function SelectorRango({ rangos, valor, onCambio, id, ariaLabel }: SelectorRangoProps) {
  return (
    <Select value={valor} onValueChange={onCambio}>
      <SelectTrigger id={id} className="w-full sm:w-[200px]" aria-label={ariaLabel ?? "Rango"}>
        <SelectValue placeholder="Rango" />
      </SelectTrigger>
      <SelectContent>
        {rangos.map((r) => (
          <SelectItem key={r.id} value={r.id}>
            {r.etiqueta}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
