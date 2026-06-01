/**
 * Punto de montaje ÚNICO del diálogo de confirmación de la app. Va una sola vez
 * cerca de la raíz (junto al `<Toaster />`, en `main.tsx`) y se suscribe al store
 * de `confirmar.ts`. Renderiza el diálogo activo, si lo hay.
 */
import * as React from "react";

import {
  type EstadoConfirmacion,
  suscribirConfirmacion,
} from "@/components/comunes/confirmar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

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
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        // Cerrar por Escape / clic fuera = cancelar.
        if (!v) responder(false);
      }}
    >
      <DialogContent className="max-w-md">
        {estado && (
          <>
            <DialogHeader>
              <DialogTitle>{estado.titulo ?? "Confirmar acción"}</DialogTitle>
              <DialogDescription className="text-foreground/80">
                {estado.mensaje}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="gap-2 sm:gap-2">
              <Button variant="outline" onClick={() => responder(false)}>
                {estado.textoCancelar ?? "Cancelar"}
              </Button>
              <Button
                variant={estado.destructivo ? "destructive" : "default"}
                onClick={() => responder(true)}
                autoFocus
              >
                {estado.textoConfirmar ?? "Confirmar"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
