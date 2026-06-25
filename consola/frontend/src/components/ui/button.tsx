import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // Estilo de boton Geist (Vercel): rectangulo de esquina suave (rounded-md),
  // peso medio, sin sombras. Monocromo: por defecto `outline` (gris); el boton
  // principal se distingue por posicion, no por color.
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/85",
        // Naranja Keni: CTA de marca (Lanzar, Generar). Texto blanco fijo (el naranja es
        // oscuro), válido en claro y oscuro. Foco con anillo de marca.
        brand:
          "bg-keni text-white hover:bg-keni-500 focus-visible:ring-keni dark:hover:bg-keni-300",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-border bg-background hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-foreground underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "outline",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

// `buttonVariants` se exporta para componentes que estilan elementos que NO son
// `<Button>` pero deben verse como tal (p.ej. `AlertDialogAction`/`Cancel` de
// `alert-dialog.tsx`, que son primitivos de Radix). Es la convención canónica de
// shadcn. react-refresh solo avisa (warn) por mezclar export de const+componente;
// no rompe el build.
export { Button, buttonVariants };
