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
import { cn } from "@/lib/utils";

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
            {estado.opciones ? (
              // Modo ELECCIÓN: filas seleccionables (título + sub-etiqueta gris) en el cuerpo, y
              // SOLO «Cancelar» abajo. Así cada opción se lee como opción y el descarte como descarte,
              // en vez de tres botones iguales en fila.
              <>
                <div className="flex flex-col gap-2 py-1">
                  {estado.opciones.map((op) => (
                    <button
                      key={op.valor}
                      type="button"
                      onClick={() => responder(op.valor)}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 rounded-lg border px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                        op.destructivo
                          ? "border-destructive/40 text-destructive hover:bg-destructive/10"
                          : "border-border bg-background hover:bg-accent hover:text-accent-foreground",
                      )}
                    >
                      <span className="text-sm font-medium">{op.etiqueta}</span>
                      {op.descripcion ? (
                        <span className="text-xs text-muted-foreground">{op.descripcion}</span>
                      ) : null}
                    </button>
                  ))}
                </div>
                <AlertDialogFooter>
                  <AlertDialogCancel onClick={() => responder(valorCancelar)}>
                    {estado.textoCancelar ?? "Cancelar"}
                  </AlertDialogCancel>
                </AlertDialogFooter>
              </>
            ) : (
              <AlertDialogFooter className="gap-2 sm:gap-2">
                <AlertDialogCancel onClick={() => responder(valorCancelar)}>
                  {estado.textoCancelar ?? "Cancelar"}
                </AlertDialogCancel>
                <AlertDialogAction
                  className={
                    estado.destructivo
                      ? buttonVariants({ variant: "destructive" })
                      : undefined
                  }
                  onClick={() => responder(true)}
                >
                  {estado.textoConfirmar ?? "Confirmar"}
                </AlertDialogAction>
              </AlertDialogFooter>
            )}
          </>
        )}
      </AlertDialogContent>
    </AlertDialog>
  );
}
