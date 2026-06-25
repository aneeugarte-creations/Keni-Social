/**
 * Buscador de la BIBLIOTECA para dar imagen a una pieza desde el editor, junto a stock/agencias/
 * propio. Lee `catalogo_media` (todas las carpetas: portal · subidas · fotografías) por
 * título + etiquetas y, al elegir un item (`POST /api/biblioteca/adjuntar {pieza_id, id}`), el back
 * lo adjunta a la pieza dejándola publicable y devuelve la `PlataformaStock` para refrescar.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { ImageOff, Search } from "lucide-react";
import * as React from "react";
import { useEffect } from "react";
import { toast } from "sonner";

import { TarjetaBiblioteca } from "@/components/media/biblioteca/TarjetaBiblioteca";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import type { ItemBiblioteca, PlataformaStock } from "@/types";

export interface BuscadorBibliotecaProps {
  open: boolean;
  onCerrar: () => void;
  piezaId: string;
  /** Marca de la pieza: acota la búsqueda a su biblioteca. */
  marca?: string;
  /** Texto inicial de búsqueda (el tema de la pieza). */
  consultaInicial?: string;
  /** Tras adjuntar: la fila por plataforma actualizada, para refrescar. */
  onAdjuntada: (plataforma: PlataformaStock) => void;
}

export function BuscadorBiblioteca({
  open,
  onCerrar,
  piezaId,
  marca,
  consultaInicial = "",
  onAdjuntada,
}: BuscadorBibliotecaProps) {
  const [q, setQ] = React.useState(consultaInicial);
  const [qDebounced, setQDebounced] = React.useState(consultaInicial.trim());

  useEffect(() => {
    if (open) {
      setQ(consultaInicial);
      setQDebounced(consultaInicial.trim());
    }
  }, [open, consultaInicial]);

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["biblioteca", "editor", marca ?? "", qDebounced],
    queryFn: ({ signal }) =>
      api.buscarBiblioteca({ q: qDebounced || undefined, marca: marca || undefined }, signal),
    enabled: open,
  });

  const items = data?.items ?? [];

  const adjuntar = useMutation({
    mutationFn: (id: string) => api.adjuntarBiblioteca({ pieza_id: piezaId, id }),
    onSuccess: (res) => {
      onAdjuntada(res.plataforma);
      toast.success("Foto de la biblioteca adjuntada. Lista para publicar.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const elegir = (item: ItemBiblioteca) => adjuntar.mutate(item.id);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Buscar en la biblioteca</DialogTitle>
          <DialogDescription>
            Fotos catalogadas del equipo (portal, subidas y fotografías). Al adjuntar una, la pieza
            queda lista para publicar.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por título o etiqueta…"
            className="h-9 rounded-lg border-transparent bg-muted/60 pl-8 placeholder:text-muted-foreground focus-visible:border-border"
            aria-label="Buscar en la biblioteca"
          />
        </div>

        <div className="max-h-[55vh] min-h-[12rem] overflow-y-auto">
          {isLoading ? (
            <div className="flex h-48 items-center justify-center text-muted-foreground">
              <Spinner className="h-5 w-5" />
            </div>
          ) : isError ? (
            <p className="flex h-48 items-center justify-center text-sm text-destructive">
              {mensajeError(error)}
            </p>
          ) : items.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
              <ImageOff className="h-6 w-6" />
              <p className="text-sm">Sin resultados en la biblioteca.</p>
            </div>
          ) : (
            <div
              className={
                adjuntar.isPending
                  ? "pointer-events-none grid grid-cols-2 gap-3 opacity-60 sm:grid-cols-3"
                  : "grid grid-cols-2 gap-3 sm:grid-cols-3"
              }
            >
              {items.map((item) => (
                <TarjetaBiblioteca
                  key={item.id}
                  item={item}
                  onElegir={elegir}
                  elegirLabel="Usar"
                  ocupado={adjuntar.isPending}
                />
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
