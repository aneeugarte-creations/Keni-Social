/**
 * Diálogo para duplicar una publicación, con opción de elegir red/título
 * destino. La marca destino la fija el switch global `marcaActiva`; si no hay
 * marca activa, cae a la marca de la publicación origen.
 * `POST /api/piezas/{id}/duplicar`; toast + invalidación.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { MarcaDisponible, Pieza, RedPieza } from "@/types";

import { CLAVE_PIEZAS } from "./claves";

export function DialogoDuplicar({
  pieza,
  marcas,
  redes,
  onCerrar,
}: {
  pieza: Pieza | null;
  marcas: MarcaDisponible[];
  redes: RedPieza[];
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const marcaValida = Boolean(marcaActiva && marcas.some((m) => m.id === marcaActiva));
  const [red, setRed] = React.useState("");
  const [titulo, setTitulo] = React.useState("");

  React.useEffect(() => {
    if (!pieza) return;
    setRed(pieza.red);
    setTitulo(`${pieza.titulo} (copia)`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pieza]);

  const duplicar = useMutation({
    mutationFn: () => {
      if (!pieza) throw new Error("Sin publicación");
      // Marca destino = switch global si es válido; si no, la de la publicación origen.
      const marca = marcaValida ? (marcaActiva as string) : pieza.marca;
      return api.duplicarPieza(pieza.id, {
        red: red || undefined,
        marca: marca || undefined,
        titulo: titulo.trim() || undefined,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      toast.success("Publicación duplicada");
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
            Duplicar publicación
          </DialogTitle>
          <DialogDescription>
            Crea una copia. Puedes cambiar la red o el título de destino.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="dup-titulo">Título</Label>
            <Input
              id="dup-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dup-red">Red destino</Label>
            <SelectorRed
              id="dup-red"
              redes={redes}
              valor={red}
              onCambio={setRed}
              incluirTodas={false}
              ariaLabel="Red destino"
              className="w-full"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={duplicar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => duplicar.mutate()} disabled={duplicar.isPending}>
            {duplicar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            Duplicar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
