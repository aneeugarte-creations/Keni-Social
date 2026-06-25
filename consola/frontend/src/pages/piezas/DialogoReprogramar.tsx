/**
 * Diálogo para REPROGRAMAR una pieza a una hora CUALQUIERA, fuera de los cajones
 * fijos del plan. La parrilla (vista calendario) solo ofrece arrastrar entre días
 * (conserva la hora) o caer en los slots del plan; esto permite elegir un instante
 * arbitrario con un `datetime-local` en hora CDMX.
 *
 * No tiene mutación propia: el padre (`VistaCalendario`) ya posee la mutación
 * `reprogramar` (con su toast/invalidación) y la pasa como `onConfirmar(iso)`. Aquí
 * solo se convierte el valor del picker (CDMX) a instante UTC con `datetimeLocalAIso`.
 */
import { CalendarClock } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AvisoZonaOperativa } from "@/components/comunes/AvisoZonaOperativa";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import type { Pieza } from "@/types";

import { datetimeLocalAIso, isoADatetimeLocal, nombreRed } from "./meta";

export function DialogoReprogramar({
  pieza,
  ocupado,
  onConfirmar,
  onCerrar,
}: {
  pieza: Pieza | null;
  ocupado: boolean;
  onConfirmar: (iso: string) => void;
  onCerrar: () => void;
}) {
  const [valor, setValor] = React.useState("");

  // Al abrir, prellena el picker con la hora actual de la pieza (CDMX).
  React.useEffect(() => {
    if (!pieza) return;
    setValor(isoADatetimeLocal(pieza.fecha_programada));
  }, [pieza]);

  const iso = datetimeLocalAIso(valor);

  function confirmar() {
    if (!iso) return;
    onConfirmar(iso);
  }

  return (
    <Dialog open={pieza !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarClock className="h-5 w-5" />
            Reprogramar a otra hora
          </DialogTitle>
          <DialogDescription>
            {pieza
              ? `Elige una fecha y hora cualquiera (hora CDMX) para "${pieza.titulo}" en ${nombreRed(pieza.red)}, fuera de los cajones fijos del plan.`
              : null}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="reprog-fecha">Fecha y hora (CDMX)</Label>
          <Input
            id="reprog-fecha"
            type="datetime-local"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
          />
          <AvisoZonaOperativa que="La hora de publicación" />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={ocupado}>
            Cancelar
          </Button>
          <Button onClick={confirmar} disabled={ocupado || !iso}>
            {ocupado ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <CalendarClock className="h-4 w-4" />
            )}
            Reprogramar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
