/**
 * Diálogo para CLONAR el contenido de una pieza a OTRA RED de la misma idea (no crea otra
 * idea: la pieza destino cuelga del mismo `contenido` padre). Copia copy, copy-in y
 * foto/collage+plantilla; si la idea no salía en esa red, la pieza nace ahí como borrador;
 * si ya salía, se SOBRESCRIBE (con el mismo reset de aprobaciones que una edición). Las
 * piezas ya publicadas no se sobrescriben (el backend responde 409).
 * `POST /api/publicaciones/{id}/clonar`; toast + invalidación.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorRed } from "@/components/comunes/SelectorRed";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { api, mensajeError } from "@/lib/api";
import type { Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";

export function DialogoClonar({
  publicacion,
  onCerrar,
}: {
  publicacion: Publicacion | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [red, setRed] = React.useState("");

  // Catálogo de redes desde la API (misma clave que el resto de superficies: se comparte caché).
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: publicacion !== null,
  });
  // La red de ORIGEN no es destino válido (clonar una pieza sobre sí misma no hace nada).
  const redes = (opcionesQuery.data?.redes ?? []).filter((r) => r.id !== publicacion?.red);

  React.useEffect(() => {
    setRed("");
  }, [publicacion]);

  const clonar = useMutation({
    mutationFn: () => {
      if (!publicacion) throw new Error("Sin publicación");
      return api.clonarPublicacion(publicacion.id, red);
    },
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success(`Contenido clonado a ${res.publicacion.red_nombre}.`);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={publicacion !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Copy className="h-5 w-5" />
            Clonar a otra red
          </DialogTitle>
          <DialogDescription>
            Copia el contenido a otra red
          </DialogDescription>
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
              <Loader2 className="h-4 w-4 animate-spin" />
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
