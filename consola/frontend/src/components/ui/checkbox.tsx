import { Check } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export interface CheckboxProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
  disabled?: boolean;
  "aria-label"?: string;
  className?: string;
}

/**
 * Checkbox nativo estilado (sin dependencias extra). Botón con `role=checkbox`
 * que sigue la estética del resto de la consola y soporta modo claro/oscuro.
 */
const Checkbox = React.forwardRef<HTMLButtonElement, CheckboxProps>(
  ({ checked, onCheckedChange, id, disabled, className, ...props }, ref) => {
    return (
      <button
        ref={ref}
        type="button"
        role="checkbox"
        id={id}
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
          checked
            ? "border-primary bg-primary text-primary-foreground"
            : "border-input hover:bg-accent",
          className,
        )}
        {...props}
      >
        {checked && <Check className="h-3.5 w-3.5" />}
      </button>
    );
  },
);
Checkbox.displayName = "Checkbox";

export { Checkbox };
