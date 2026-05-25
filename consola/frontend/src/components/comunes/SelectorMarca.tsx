/**
 * Selector de marca compartido. Un único componente y un único centinela
 * (`MARCA_TODAS`, definido en `./selectores`) para representar "todas las
 * marcas" / "sin marca concreta".
 *
 * Reemplaza los selectores de marca dispersos que usaban tres centinelas
 * distintos. El catálogo de marcas SIEMPRE llega de la API; aquí solo se
 * renderiza, sin hardcodear ids.
 *
 * - `incluirTodas` (por defecto `true`): añade la opción "Todas". Cuando el
 *   campo es obligatorio (p. ej. Generar copy) se pasa `false`.
 *
 * Los centinelas/helpers (`MARCA_TODAS`, `marcaParam`, `desdeMarca`) viven en
 * `./selectores` para no romper el fast-refresh de este componente.
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { MarcaDisponible } from "@/types";

import { MARCA_TODAS } from "./selectores";

export function SelectorMarca({
  marcas,
  valor,
  onCambio,
  incluirTodas = true,
  etiquetaTodas = "Todas las marcas",
  placeholder = "Marca",
  ariaLabel = "Marca",
  id,
  className = "w-full sm:w-[200px]",
  disabled,
}: {
  marcas: MarcaDisponible[];
  valor: string;
  onCambio: (valor: string) => void;
  /** Añade la opción "Todas". Pásalo a `false` cuando la marca sea obligatoria. */
  incluirTodas?: boolean;
  /** Texto de la opción "Todas" (p. ej. "Todas las marcas"). */
  etiquetaTodas?: string;
  placeholder?: string;
  ariaLabel?: string;
  id?: string;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <Select value={valor} onValueChange={onCambio} disabled={disabled}>
      <SelectTrigger id={id} className={className} aria-label={ariaLabel}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {incluirTodas && <SelectItem value={MARCA_TODAS}>{etiquetaTodas}</SelectItem>}
        {marcas.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.nombre}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
