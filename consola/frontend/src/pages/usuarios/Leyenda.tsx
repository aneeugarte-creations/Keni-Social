import { Network } from "lucide-react";

import { metaZona } from "@/lib/organigrama";

/** Leyenda de las áreas/marcas presentes en el organigrama. */
export function Leyenda({ zonas }: { zonas: Set<string> }) {
  const ids = [...zonas];
  if (ids.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <Network className="h-3.5 w-3.5" /> Áreas:
      </span>
      {ids.map((z) => (
        <span key={z}>{metaZona(z).etiqueta}</span>
      ))}
    </div>
  );
}
