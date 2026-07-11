/**
 * Tarjeta de un item de la biblioteca de medios: miniatura, título, etiquetas (chips) y acciones.
 * Acciones según props:
 *  - Descargar SIEMPRE (`GET /api/biblioteca/descargar/{id}`).
 *  - `onRafaga` (opcional): «Ráfaga» — abre el visor del burst (solo tiene sentido en fotografías).
 *  - `onElegir` (opcional): acción primaria (p. ej. «Usar» para adjuntar a una pieza en el editor).
 */
import { Download, Images } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { ItemBiblioteca } from "@/types";

export interface TarjetaBibliotecaProps {
  item: ItemBiblioteca;
  /** Si se pasa, muestra «Ráfaga» para navegar el burst del keeper. */
  onRafaga?: (item: ItemBiblioteca) => void;
  /** Si se pasa, muestra la acción primaria (p. ej. adjuntar en el editor). */
  onElegir?: (item: ItemBiblioteca) => void;
  /** Etiqueta de la acción primaria (def «Usar»). */
  elegirLabel?: string;
  /** Deshabilita las acciones (p. ej. mientras se adjunta). */
  ocupado?: boolean;
}

export function TarjetaBiblioteca({
  item,
  onRafaga,
  onElegir,
  elegirLabel = "Usar",
  ocupado,
}: TarjetaBibliotecaProps) {
  return (
    <figure className="flex flex-col overflow-hidden rounded-xl border bg-card">
      <img
        src={item.thumb || item.url}
        alt={item.titulo || "Foto de la biblioteca"}
        loading="lazy"
        className="aspect-square w-full object-cover"
      />
      <figcaption className="flex flex-1 flex-col gap-1.5 px-2 py-1.5">
        <span className="block truncate text-[11px] font-medium text-foreground">
          {item.titulo || "Sin título"}
        </span>
        {item.etiquetas.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {item.etiquetas.slice(0, 4).map((e) => (
              <Badge key={e} variant="outline" className="px-1.5 py-0 text-[10px]">
                {e}
              </Badge>
            ))}
          </div>
        )}
        <div className="mt-auto flex flex-wrap items-center gap-1 pt-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1 px-2 text-[11px]"
            disabled={ocupado}
            onClick={() => api.descargarBiblioteca(item.id)}
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            Descargar
          </Button>
          {onRafaga && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="gap-1 px-2 text-[11px]"
              disabled={ocupado}
              onClick={() => onRafaga(item)}
            >
              <Images className="h-3.5 w-3.5" aria-hidden="true" />
              Ráfaga
            </Button>
          )}
          {onElegir && (
            <Button
              type="button"
              size="sm"
              className="px-2 text-[11px]"
              disabled={ocupado}
              onClick={() => onElegir(item)}
            >
              {elegirLabel}
            </Button>
          )}
        </div>
      </figcaption>
    </figure>
  );
}
