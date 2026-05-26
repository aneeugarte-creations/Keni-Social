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
import { NINGUNA, RED_TODAS } from "./selectores";

/**
 * Forma mínima que el selector necesita de una red. Aceptamos cualquier objeto
 * con `id`/`nombre` (`RedPublicacion`, `RedComercial`, …) para que el componente
 * sea el contrato único sin acoplarse a una sola variante de red.
 */
type RedSeleccionable = { id: string; nombre: string };

export function SelectorRed({
  redes,
  valor,
  onCambio,
  incluirTodas = true,
  etiquetaTodas = "Todas las redes",
  incluirNinguna = false,
  etiquetaNinguna = "Sin red",
  placeholder = "Red",
  ariaLabel = "Red",
  id,
  className = "w-full sm:w-[160px]",
  disabled,
}: {
  redes: RedSeleccionable[];
  valor: string;
  onCambio: (valor: string) => void;
  /** Añade la opción "Todas". Pásalo a `false` cuando la red sea obligatoria. */
  incluirTodas?: boolean;
  etiquetaTodas?: string;
  /**
   * Añade la opción "Sin red" (centinela `NINGUNA`), para campos OPCIONALES
   * donde se puede dejar sin valor. Distinto de `incluirTodas` (no filtrar).
   */
  incluirNinguna?: boolean;
  /** Texto de la opción "Sin red". */
  etiquetaNinguna?: string;
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
        {incluirNinguna && <SelectItem value={NINGUNA}>{etiquetaNinguna}</SelectItem>}
        {redes.map((r) => (
          <SelectItem key={r.id} value={r.id}>
            {r.nombre}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
