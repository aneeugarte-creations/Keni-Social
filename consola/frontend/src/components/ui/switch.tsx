/**
 * Switch (toggle) accesible, sin dependencias externas: un `button role="switch"`.
 *
 * COLOR ÚNICO en toda la plataforma: encendido = gris neutro CLARO (`neutral-300`),
 * apagado = gris aún más claro (`bg-input`). El estado se lee sobre todo por la POSICIÓN
 * del pulgar; ningún switch va en negro ni en color de marca (decisión de diseño: todos
 * los «botones de deslizar» idénticos en cualquier pantalla).
 */
import { cn } from "@/lib/utils";

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  id,
  "aria-label": ariaLabel,
}: {
  checked: boolean;
  onCheckedChange: (valor: boolean) => void;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-label={ariaLabel}
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-neutral-300 dark:bg-neutral-600" : "bg-input",
      )}
    >
      <span
        className={cn(
          "inline-block h-4 w-4 transform rounded-full bg-background shadow transition-transform",
          checked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  );
}
