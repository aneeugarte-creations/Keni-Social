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
      // Si había uno sin responder, lo cerramos en su valor de cancelación (null en
      // modo elección, false en confirmación) para no dejar su promesa colgada (no
      // debería pasar: el modal bloquea la UI).
      if (pendiente.current) pendiente.current.resolver(pendiente.current.opciones ? null : false);
      pendiente.current = nuevo;
      setEstado(nuevo);
    });
  }, []);

  const responder = React.useCallback((valor: boolean | string | null) => {
    if (pendiente.current) {
      pendiente.current.resolver(valor);
      pendiente.current = null;
    }
    setEstado(null);
  }, []);

  const abierto = estado != null;
  // Valor con el que se cancela este diálogo: null en modo elección, false en confirmación.
  const valorCancelar = estado?.opciones ? null : false;

  return (
    <AlertDialog
      open={abierto}
      onOpenChange={(v) => {
        // Cerrar por Escape = cancelar. (AlertDialog no cierra por clic fuera.)
        if (!v) responder(valorCancelar);
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
              <AlertDialogCancel onClick={() => responder(valorCancelar)}>
                {estado.textoCancelar ?? "Cancelar"}
              </AlertDialogCancel>
              {estado.opciones ? (
                // Modo ELECCIÓN: un botón por opción (outline gris salvo destructivo).
                estado.opciones.map((op) => (
                  <AlertDialogAction
                    key={op.valor}
                    className={buttonVariants({
                      variant: op.destructivo ? "destructive" : "outline",
                    })}
                    onClick={() => responder(op.valor)}
                  >
                    {op.etiqueta}
                  </AlertDialogAction>
                ))
              ) : (
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
              )}
            </AlertDialogFooter>
          </>
        )}
      </AlertDialogContent>
    </AlertDialog>
  );
}
