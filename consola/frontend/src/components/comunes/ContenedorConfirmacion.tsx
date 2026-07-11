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
import { Minus, Plus } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function ContenedorConfirmacion() {
  const [estado, setEstado] = React.useState<EstadoConfirmacion | null>(null);
  const pendiente = React.useRef<EstadoConfirmacion | null>(null);
  // Valor en edición de la fila numérica ("a tu gusto"); se resetea a `valorInicial` con
  // cada diálogo nuevo (id cambia tanto al reabrir como al pasar de una elección a otra).
  const [valorNumero, setValorNumero] = React.useState(0);

  React.useEffect(() => {
    return suscribirConfirmacion((nuevo) => {
      // Si había uno sin responder, lo cerramos en su valor de cancelación (null en
      // modo elección, false en confirmación) para no dejar su promesa colgada (no
      // debería pasar: el modal bloquea la UI).
      if (pendiente.current) pendiente.current.resolver(pendiente.current.opciones ? null : false);
      pendiente.current = nuevo;
      setEstado(nuevo);
      if (nuevo.numero) setValorNumero(nuevo.numero.valorInicial);
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
                        "border-border bg-background hover:bg-accent hover:text-accent-foreground",
                      )}
                    >
                      <span className="text-sm font-medium">{op.etiqueta}</span>
                      {op.descripcion ? (
                        <span className="text-xs text-muted-foreground">{op.descripcion}</span>
                      ) : null}
                    </button>
                  ))}
                  {estado.numero && (
                    <div className="flex w-full items-center justify-between gap-3 rounded-lg border border-border bg-background px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <Button
                          type="button"
                          size="icon"
                          variant="outline"
                          className="shrink-0"
                          onClick={() =>
                            setValorNumero((v) => Math.max(estado.numero!.minimo, v - 1))
                          }
                          aria-label="Restar"
                        >
                          <Minus className="h-3.5 w-3.5" />
                        </Button>
                        <Input
                          type="number"
                          min={estado.numero.minimo}
                          max={estado.numero.maximo}
                          value={valorNumero}
                          onChange={(e) => setValorNumero(Number(e.target.value) || 0)}
                          className="h-7 w-14 text-center"
                          aria-label="Cantidad a tu gusto"
                        />
                        <Button
                          type="button"
                          size="icon"
                          variant="outline"
                          className="shrink-0"
                          onClick={() =>
                            setValorNumero((v) => Math.min(estado.numero!.maximo, v + 1))
                          }
                          aria-label="Sumar"
                        >
                          <Plus className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          responder(
                            `numero:${Math.min(estado.numero!.maximo, Math.max(estado.numero!.minimo, valorNumero))}`,
                          )
                        }
                      >
                        {estado.numero.etiqueta}
                      </Button>
                    </div>
                  )}
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
                <AlertDialogAction onClick={() => responder(true)}>
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
