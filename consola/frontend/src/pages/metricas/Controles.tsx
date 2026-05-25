/**
 * Controles del dashboard: selector de rango y re-export del selector de marca
 * compartido.
 *
 * El selector de marca vive ahora en `@/components/comunes/SelectorMarca`
 * (un único componente y un único centinela `MARCA_TODAS`). Aquí se re-exporta
 * para no cambiar los imports de Métricas / Comparar periodos. `SelectorRango`
 * es específico de Métricas y se mantiene local.
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { RangoMetrica } from "@/types";

export { SelectorMarca } from "@/components/comunes/SelectorMarca";
export { MARCA_TODAS } from "@/components/comunes/selectores";

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
