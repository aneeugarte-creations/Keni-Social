/**
 * Diálogo para duplicar una publicación, con opción de elegir red/marca/título
 * destino. Por defecto reutiliza los de la publicación origen.
 * `POST /api/publicaciones/{id}/duplicar`; toast + invalidación.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
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
import { api, ApiError } from "@/lib/api";
import type { MarcaDisponible, Publicacion, RedPublicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

export function DialogoDuplicar({
  publicacion,
  marcas,
  redes,
  onCerrar,
}: {
  publicacion: Publicacion | null;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [red, setRed] = React.useState("");
  const [marca, setMarca] = React.useState("");
  const [titulo, setTitulo] = React.useState("");

  React.useEffect(() => {
    if (!publicacion) return;
    setRed(publicacion.red);
    setMarca(publicacion.marca);
    setTitulo(`${publicacion.titulo} (copia)`);
  }, [publicacion]);

  const duplicar = useMutation({
    mutationFn: () => {
      if (!publicacion) throw new Error("Sin publicación");
      return api.duplicarPublicacion(publicacion.id, {
        red: red || undefined,
        marca: marca || undefined,
        titulo: titulo.trim() || undefined,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      toast.success("Publicación duplicada");
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
            Duplicar publicación
          </DialogTitle>
          <DialogDescription>
            Crea una copia. Puedes cambiar la red, la marca o el título de destino.
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
          <div className="grid gap-4 sm:grid-cols-2">
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
            <div className="space-y-1.5">
              <Label htmlFor="dup-marca">Marca destino</Label>
              <SelectorMarca
                id="dup-marca"
                marcas={marcas}
                valor={marca}
                onCambio={setMarca}
                incluirTodas={false}
                ariaLabel="Marca destino"
                className="w-full"
              />
            </div>
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
