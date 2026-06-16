/**
 * Switch (toggle) accesible, sin dependencias externas: un `button role="switch"`.
 *
 * Dos tonos:
 *   · `"neutro"` (por defecto): pista SIEMPRE `bg-input` (gris claro), encendido o apagado —
 *     el estado se lee por la POSICIÓN del pulgar. Es el color ÚNICO del resto de la plataforma.
 *   · `"estado"`: semáforo SUAVE para un interruptor maestro (p. ej. «Máquina») — verde suave
 *     encendido, rojo suave apagado.
 */
import { cn } from "@/lib/utils";

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  id,
  "aria-label": ariaLabel,
  tono = "neutro",
}: {
  checked: boolean;
  onCheckedChange: (valor: boolean) => void;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  /** `"neutro"` (gris uniforme) o `"estado"` (verde suave on / rojo suave off). */
  tono?: "neutro" | "estado";
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
        tono === "estado"
          ? checked
            ? "bg-emerald-200 dark:bg-emerald-800"
            : "bg-red-200 dark:bg-red-900"
          : "bg-input",
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
