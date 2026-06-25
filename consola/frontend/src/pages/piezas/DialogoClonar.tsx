/**
 * Diálogo para CLONAR el contenido de una pieza a OTRA RED de la misma idea (no crea otra
 * idea: la pieza destino cuelga del mismo `contenido` padre). Copia copy, copy-in y
 * foto/collage+plantilla; si la idea no salía en esa red, la pieza nace ahí como borrador;
 * si ya salía, se SOBRESCRIBE (con el mismo reset de aprobaciones que una edición). Las
 * piezas ya publicadas no se sobrescriben (el backend responde 409).
 * `POST /api/piezas/{id}/clonar`; toast + invalidación.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorRed } from "@/components/comunes/SelectorRed";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import type { Pieza } from "@/types";

import { CLAVE_PIEZAS } from "./claves";

export function DialogoClonar({
  pieza,
  onCerrar,
}: {
  pieza: Pieza | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [red, setRed] = React.useState("");

  // Catálogo de redes desde la API (misma clave que el resto de superficies: se comparte caché).
  const opcionesQuery = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: pieza !== null,
  });
  // La red de ORIGEN no es destino válido (clonar una pieza sobre sí misma no hace nada).
  const redes = (opcionesQuery.data?.redes ?? []).filter((r) => r.id !== pieza?.red);

  React.useEffect(() => {
    setRed("");
  }, [pieza]);

  const clonar = useMutation({
    mutationFn: () => {
      if (!pieza) throw new Error("Sin publicación");
      return api.clonarPieza(pieza.id, red);
    },
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success(`Publicacion clonado a ${res.pieza.red_nombre}.`);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={pieza !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Copy className="h-5 w-5" />
            Clonar a otra red
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="clonar-red">Red destino</Label>
          <SelectorRed
            id="clonar-red"
            redes={redes}
            valor={red}
            onCambio={setRed}
            incluirTodas={false}
            ariaLabel="Red destino"
            className="w-full"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={clonar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => clonar.mutate()} disabled={clonar.isPending || !red}>
            {clonar.isPending ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            Clonar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
