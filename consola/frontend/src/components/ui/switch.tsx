/**
 * Switch (toggle) accesible, sin dependencias externas: un `button role="switch"`.
 * Suficiente para los toggles de funcionalidad de la página de Configuración.
 */
import { cn } from "@/lib/utils";

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  id,
  "aria-label": ariaLabel,
  tono = "primary",
}: {
  checked: boolean;
  onCheckedChange: (valor: boolean) => void;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  /**
   * Color de la pista ENCENDIDA: `"primary"` (negro Geist, por defecto) o `"neutral"`
   * (gris `muted-foreground`, para encajar con el cromo gris de la plataforma — p. ej. el
   * pipeline). Apagado siempre es `bg-input`.
   */
  tono?: "primary" | "neutral";
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
        checked
          ? tono === "neutral"
            ? "bg-muted-foreground"
            : "bg-primary"
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
