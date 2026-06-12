import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    // `text-base md:text-sm`: campos a 16px en MÓVIL y 14px en escritorio. Con menos de 16px,
    // iOS Safari hace AUTO-ZOOM al enfocar un input y deja la página AMPLIADA (hay que pellizcar
    // para minimizar) — justo lo que se veía al entrar al login en el móvil. 16px lo evita sin
    // tocar el look de escritorio.
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
