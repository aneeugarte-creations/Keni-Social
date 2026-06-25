/**
 * Visor de RÁFAGA (burst del keeper): dado un archivo de una galería, llama a
 * `GET /api/artes/propio/rafaga` y muestra las fotos del MISMO disparo en ráfaga para navegarlas.
 * Lectura pura: aquí solo se MIRA (descargar/guardar viven en la tarjeta de la biblioteca).
 */
import { useQuery } from "@tanstack/react-query";
import { ImageOff } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";

export interface RafagaRef {
  galeria_id: string;
  archivo: string;
  marca?: string;
  dispositivo?: string;
  /** Título a mostrar en el encabezado del visor. */
  titulo?: string;
}

export interface VisorRafagaProps {
  /** Foto cuya ráfaga se navega; `null` mantiene el visor cerrado. */
  ref_: RafagaRef | null;
  onCerrar: () => void;
}

export function VisorRafaga({ ref_, onCerrar }: VisorRafagaProps) {
  const abierto = ref_ !== null;

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["rafaga", ref_?.galeria_id ?? "", ref_?.archivo ?? "", ref_?.marca ?? ""],
    queryFn: ({ signal }) =>
      api.rafagaPropio(
        {
          galeria_id: ref_!.galeria_id,
          archivo: ref_!.archivo,
          marca: ref_?.marca,
          dispositivo: ref_?.dispositivo,
        },
        signal,
      ),
    enabled: abierto,
  });

  const fotos = data?.fotos ?? [];

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Ráfaga</DialogTitle>
          <DialogDescription>
            {ref_?.titulo
              ? `Fotos del mismo disparo de «${ref_.titulo}».`
              : "Fotos del mismo disparo en ráfaga."}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] min-h-[12rem] overflow-y-auto">
          {isLoading ? (
            <div className="flex h-48 items-center justify-center text-muted-foreground">
              <Spinner className="h-5 w-5" />
            </div>
          ) : isError ? (
            <p className="flex h-48 items-center justify-center text-sm text-destructive">
              {mensajeError(error)}
            </p>
          ) : fotos.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
              <ImageOff className="h-6 w-6" />
              <p className="text-sm">No hay más fotos en esta ráfaga.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {fotos.map((f, i) => (
                <figure
                  key={`${f.archivo}-${i}`}
                  className="overflow-hidden rounded-lg border border-border bg-muted/20"
                >
                  <img
                    src={f.thumb}
                    alt={f.archivo || "Foto de la ráfaga"}
                    loading="lazy"
                    className="aspect-square w-full object-cover"
                  />
                  <figcaption className="block truncate px-2 py-1 text-[11px] text-muted-foreground">
                    {f.archivo}
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
