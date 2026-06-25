/**
 * Sugeridor foto→pieza: lista las mejores fotos de la biblioteca para la pieza activa
 * (`GET /api/biblioteca/sugerir`) junto a la fuente «Biblioteca» del editor. Un clic adjunta la foto
 * a la pieza (`POST /api/biblioteca/adjuntar`, el mismo flujo que el buscador) y la deja publicable.
 * Si no hay sugerencias —o aún cargan— la sección no se muestra (silencioso).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { TarjetaBiblioteca } from "@/components/media/biblioteca/TarjetaBiblioteca";
import { api, mensajeError } from "@/lib/api";
import type { ItemBiblioteca, PlataformaStock } from "@/types";

export interface SugeridasBibliotecaProps {
  piezaId: string;
  /** Tras adjuntar: la fila por plataforma actualizada, para refrescar. */
  onAdjuntada: (plataforma: PlataformaStock) => void;
  /** Deshabilita las acciones (p. ej. mientras otra fuente está en curso). */
  ocupado?: boolean;
}

export function SugeridasBiblioteca({ piezaId, onAdjuntada, ocupado }: SugeridasBibliotecaProps) {
  const { data } = useQuery({
    queryKey: ["biblioteca", "sugeridas", piezaId],
    queryFn: ({ signal }) => api.sugerirBiblioteca(piezaId, 6, signal),
  });

  const adjuntar = useMutation({
    mutationFn: (id: string) => api.adjuntarBiblioteca({ pieza_id: piezaId, id }),
    onSuccess: (res) => {
      onAdjuntada(res.plataforma);
      toast.success("Foto sugerida adjuntada. Lista para publicar.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const items = data?.items ?? [];
  if (items.length === 0) return null;

  const elegir = (item: ItemBiblioteca) => adjuntar.mutate(item.id);

  return (
    <div className="space-y-1.5">
      <span className="text-xs text-muted-foreground">Fotos sugeridas:</span>
      <div
        className={
          adjuntar.isPending
            ? "pointer-events-none grid grid-cols-3 gap-2 opacity-60"
            : "grid grid-cols-3 gap-2"
        }
      >
        {items.map((item) => (
          <TarjetaBiblioteca
            key={item.id}
            item={item}
            onElegir={elegir}
            elegirLabel="Usar"
            ocupado={ocupado || adjuntar.isPending}
          />
        ))}
      </div>
    </div>
  );
}
