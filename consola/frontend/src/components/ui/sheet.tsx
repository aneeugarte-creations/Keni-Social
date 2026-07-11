import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Hoja inferior (bottom sheet) sobre el Dialog de Radix: un panel anclado al borde
 * inferior del viewport que sube con un deslizamiento discreto. Pensada para móvil
 * (filtros y controles contextuales); en escritorio se prefiere `Dialog`.
 *
 * Radix aporta el foco atrapado, el cierre con Escape y con tap en el telón. El
 * contenido scrollea dentro (`max-h-[85dvh]`) y el padding inferior respeta la
 * zona segura de iOS (`env(safe-area-inset-bottom)`).
 */
const Sheet = DialogPrimitive.Root;
const SheetTrigger = DialogPrimitive.Trigger;
const SheetPortal = DialogPrimitive.Portal;
const SheetClose = DialogPrimitive.Close;

const SheetOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      // Telón algo más suave que el del Dialog centrado: la hoja convive con la página
      // (se entra y se sale de ella a menudo), no debe sentirse un modal pesado.
      "fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className,
    )}
    {...props}
  />
));
SheetOverlay.displayName = "SheetOverlay";

const SheetContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, onInteractOutside, ...props }, ref) => (
  <SheetPortal>
    <SheetOverlay />
    <DialogPrimitive.Content
      ref={ref}
      // La hoja se rotula con `aria-label` (o un `SheetTitle` sr-only); sin descripción
      // aparte, se anula el aria-describedby que Radix genera por defecto.
      aria-describedby={undefined}
      onInteractOutside={(e) => {
        onInteractOutside?.(e);
        if (e.defaultPrevented) return;
        // Un Select de Radix abierto dentro de la hoja portaliza sus opciones a <body>:
        // tocar una opción cuenta como interacción "fuera" del Dialog y cerraría la hoja
        // entera. Si el toque cae en contenido portalizado de Radix, no es un cierre.
        const objetivo = e.target as HTMLElement | null;
        if (objetivo?.closest("[data-radix-popper-content-wrapper]")) e.preventDefault();
      }}
      className={cn(
        "fixed inset-x-0 bottom-0 z-50 flex max-h-[85dvh] flex-col overflow-y-auto rounded-t-xl border-t border-border bg-background pb-[env(safe-area-inset-bottom)] duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom",
        className,
      )}
      {...props}
    >
      {/* Asa: afordancia visual de hoja; el cierre real es Escape o tap en el telón. */}
      <div
        aria-hidden="true"
        className="mx-auto mb-1 mt-2 h-1 w-9 shrink-0 rounded-full bg-muted-foreground/30"
      />
      {children}
    </DialogPrimitive.Content>
  </SheetPortal>
));
SheetContent.displayName = "SheetContent";

const SheetTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props}
  />
));
SheetTitle.displayName = "SheetTitle";

const SheetDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
));
SheetDescription.displayName = "SheetDescription";

export {
  Sheet,
  SheetPortal,
  SheetOverlay,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetTitle,
  SheetDescription,
};
