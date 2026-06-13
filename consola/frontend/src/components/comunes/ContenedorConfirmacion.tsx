/**
 * Punto de montaje ÚNICO del diálogo de confirmación de la app. Va una sola vez
 * cerca de la raíz (junto al `<Toaster />`, en `main.tsx`) y se suscribe al store
 * de `confirmar.ts`. Renderiza el diálogo activo, si lo hay.
 *
 * Usa `AlertDialog` (no el `Dialog` genérico): es el primitivo dedicado a
 * confirmaciones (`role="alertdialog"`, botones `Action`/`Cancel`). A diferencia
 * del `Dialog`, NO se cierra por clic fuera —lo correcto para una confirmación—;
 * Escape sí cancela (→ `false`).
 */
import * as React from "react";

import {
  type EstadoConfirmacion,
  suscribirConfirmacion,
} from "@/components/comunes/confirmar";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { buttonVariants } from "@/components/ui/button";

export function ContenedorConfirmacion() {
  const [estado, setEstado] = React.useState<EstadoConfirmacion | null>(null);
  const pendiente = React.useRef<EstadoConfirmacion | null>(null);

  React.useEffect(() => {
    return suscribirConfirmacion((nuevo) => {
      // Si había una confirmación sin responder, la cerramos en false para no
      // dejar su promesa colgada (no debería pasar: el modal bloquea la UI).
      if (pendiente.current) pendiente.current.resolver(false);
      pendiente.current = nuevo;
      setEstado(nuevo);
    });
  }, []);

  const responder = React.useCallback((valor: boolean) => {
    if (pendiente.current) {
      pendiente.current.resolver(valor);
      pendiente.current = null;
    }
    setEstado(null);
  }, []);

  const abierto = estado != null;

  return (
    <AlertDialog
      open={abierto}
      onOpenChange={(v) => {
        // Cerrar por Escape = cancelar. (AlertDialog no cierra por clic fuera.)
        if (!v) responder(false);
      }}
    >
      <AlertDialogContent className="max-w-md">
        {estado && (
          <>
            <AlertDialogHeader>
              <AlertDialogTitle>{estado.titulo ?? "Confirmar acción"}</AlertDialogTitle>
              <AlertDialogDescription className="text-foreground/80">
                {estado.mensaje}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter className="gap-2 sm:gap-2">
              <AlertDialogCancel onClick={() => responder(false)}>
                {estado.textoCancelar ?? "Cancelar"}
              </AlertDialogCancel>
              <AlertDialogAction
                className={
                  estado.destructivo
                    ? buttonVariants({ variant: "destructive" })
                    : undefined
                }
                onClick={() => responder(true)}
                autoFocus
              >
                {estado.textoConfirmar ?? "Confirmar"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </>
        )}
      </AlertDialogContent>
    </AlertDialog>
  );
}
