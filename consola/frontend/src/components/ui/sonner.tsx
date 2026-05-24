import { Toaster as Sonner, type ToasterProps } from "sonner";

import { useTema } from "@/hooks/use-tema";

/**
 * Contenedor de notificaciones (toasts). Usa el tema actual (claro/oscuro) para
 * que las notificaciones combinen con la consola.
 */
function Toaster(props: ToasterProps) {
  const { tema } = useTema();

  return (
    <Sonner
      theme={tema}
      className="toaster group"
      position="bottom-right"
      richColors
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
          description: "group-[.toast]:text-muted-foreground",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
