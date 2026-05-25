/**
 * Selector de red compartido, análogo a `SelectorMarca`. Un único centinela
 * (`RED_TODAS`, definido en `./selectores`) para "todas las redes" / "cualquier
 * red".
 *
 * El catálogo de redes SIEMPRE llega de la API (`/api/publicaciones/opciones`);
 * aquí solo se renderiza, sin hardcodear ids.
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { RedPublicacion } from "@/types";

import { RED_TODAS } from "./selectores";

export function SelectorRed({
  redes,
  valor,
  onCambio,
  incluirTodas = true,
  etiquetaTodas = "Todas las redes",
  placeholder = "Red",
  ariaLabel = "Red",
  id,
  className = "w-full sm:w-[160px]",
  disabled,
}: {
  redes: RedPublicacion[];
  valor: string;
  onCambio: (valor: string) => void;
  /** Añade la opción "Todas". Pásalo a `false` cuando la red sea obligatoria. */
  incluirTodas?: boolean;
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
        {incluirTodas && <SelectItem value={RED_TODAS}>{etiquetaTodas}</SelectItem>}
        {redes.map((r) => (
          <SelectItem key={r.id} value={r.id}>
            {r.nombre}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
