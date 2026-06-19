import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        outline: "text-foreground",
        // Variantes SEMÁNTICAS de estado (vocabulario único: ok=verde, info=cielo,
        // aviso=ámbar, error=rojo). Pares 700/300 para claro/oscuro. Las consumen el
        // doctor de Sistema y `ChipEstado` (badge único de estados de trabajo).
        ok: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
        info: "border-transparent bg-sky-500/15 text-sky-700 dark:text-sky-300",
        aviso: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300",
        error: "border-transparent bg-red-500/15 text-red-700 dark:text-red-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

// `badgeVariants` queda como const local (lo usa Badge); no se exporta para que
// el archivo exporte solo el componente y porque nadie mas lo consume.
export { Badge };
