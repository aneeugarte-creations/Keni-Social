/**
 * Diálogo de "plantilla de marca": elige una marca y diseña su plantilla por formato (fondo,
 * foto, logo, textos) en el editor visual. UN solo editor, UN solo Guardar (dentro del editor).
 *
 * La identidad visual vive en el SPEC de capas (`EditorPlantillaSpec`), que el servidor renderiza
 * idéntico al generar las placas. (El antiguo formulario plano se retiró: causaba duplicación —
 * logo, "wordmark" y Guardar repetidos. Sus campos planos quedan como semilla del spec por
 * defecto en el backend.)
 */
import * as React from "react";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { EditorPlantillaSpec } from "@/components/editor/EditorPlantillaSpec";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import type { MarcaDisponible } from "@/types";

export function EditorPlantillaMarca({
  abierto,
  onOpenChange,
  marcas,
  marcaInicial,
}: {
  abierto: boolean;
  onOpenChange: (abierto: boolean) => void;
  marcas: MarcaDisponible[];
  /** Marca a preseleccionar al abrir (la del contexto de la pieza, si la hay). */
  marcaInicial?: string;
}) {
  const [marca, setMarca] = React.useState(marcaInicial || marcas[0]?.id || "");

  React.useEffect(() => {
    if (abierto && !marca) setMarca(marcaInicial || marcas[0]?.id || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abierto]);

  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-6xl">
        <DialogHeader>
          <DialogTitle>Plantilla de marca</DialogTitle>
          <DialogDescription>
            Diseña la plantilla por formato (fondo, foto, logo y textos). Lo que diseñas es lo que
            se genera en las placas de esta marca.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Label htmlFor="plantilla-marca" className="text-xs text-muted-foreground">
              Marca
            </Label>
            <SelectorMarca
              id="plantilla-marca"
              marcas={marcas}
              valor={marca}
              onCambio={setMarca}
              incluirTodas={false}
              placeholder="Elige una marca"
              ariaLabel="Marca de la plantilla"
              className="w-56"
            />
          </div>

          {marca && (
            <EditorPlantillaSpec
              key={marca}
              marca={marca}
              onGuardado={() => onOpenChange(false)}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
