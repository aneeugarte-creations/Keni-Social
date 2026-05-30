/**
 * Selector "Usar plantilla" para el compositor/editor de copy.
 *
 * Carga el catálogo unificado (`/api/plantillas-contenido`) y, al elegir una plantilla:
 *   - modo 'plano':      vuelca su `contenido` directamente en el editor (`onUsar`).
 *   - modo 'estructura': abre el diálogo "Aplicar" para rellenar variables y, al confirmar,
 *                        inserta el copy compuesto.
 * Prioriza las plantillas que coinciden con la marca/red actual, pero muestra todas. React
 * Query + toasts; modo claro/oscuro; texto es-MX.
 */
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { PlantillaContenido } from "@/types";

import { DialogoAplicarPlantilla } from "./DialogoAplicarPlantilla";
import { CLAVE_PLANTILLAS } from "./util";

export function SelectorPlantilla({
  marca,
  red,
  onUsar,
}: {
  /** Marca actual (para priorizar plantillas relevantes). */
  marca: string;
  /** Red actual (para priorizar plantillas relevantes). */
  red: string;
  /** Recibe el copy de la plantilla elegida (texto plano o estructura ya compuesta). */
  onUsar: (contenido: string) => void;
}) {
  const query = useQuery({
    queryKey: CLAVE_PLANTILLAS,
    queryFn: ({ signal }) => api.plantillasContenido(undefined, signal),
  });

  const plantillas = React.useMemo(
    () => query.data?.plantillas ?? [],
    [query.data],
  );

  // Plantilla de estructura elegida que abre el diálogo "Aplicar" (null = cerrado).
  const [aAplicar, setAAplicar] = React.useState<PlantillaContenido | null>(null);

  // Orden: primero las que coinciden con marca y red; luego marca; luego red;
  // luego genéricas; el resto al final.
  const ordenadas = React.useMemo(() => {
    const rango = (p: { marca: string; red: string }) => {
      const m = !p.marca || p.marca === marca;
      const r = !p.red || p.red === red;
      if (p.marca === marca && p.red === red) return 0;
      if (m && r) return 1;
      if (m || r) return 2;
      return 3;
    };
    return [...plantillas].sort((a, b) => rango(a) - rango(b));
  }, [plantillas, marca, red]);

  function usar(id: string) {
    const plantilla = plantillas.find((p) => p.id === id);
    if (!plantilla) return;
    if (plantilla.modo === "plano") {
      onUsar(plantilla.contenido);
      toast.success(`Plantilla aplicada: ${plantilla.nombre}`);
      return;
    }
    // Estructura: rellenar variables en el diálogo y luego insertar el copy compuesto.
    setAAplicar(plantilla);
  }

  return (
    <>
      <Select
        value=""
        onValueChange={usar}
        disabled={query.isPending || plantillas.length === 0}
      >
        <SelectTrigger className="h-8 w-auto gap-1.5 text-xs" aria-label="Usar plantilla">
          <FileText className="h-3.5 w-3.5" />
          <SelectValue
            placeholder={plantillas.length === 0 ? "Sin plantillas" : "Usar plantilla"}
          />
        </SelectTrigger>
        <SelectContent>
          {ordenadas.map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {p.nombre}
              {p.modo === "estructura" ? " · estructura" : ""}
              {p.marca ? ` · ${p.marca_nombre || p.marca}` : ""}
              {p.red ? ` · ${p.red_nombre || p.red}` : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {aAplicar && (
        <DialogoAplicarPlantilla
          plantilla={aAplicar}
          abierto={aAplicar !== null}
          onCerrar={() => setAAplicar(null)}
          onUsar={onUsar}
        />
      )}
    </>
  );
}
