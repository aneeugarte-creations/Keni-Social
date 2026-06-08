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
      {ids.map((z) => {
        const meta = metaZona(z);
        return (
          <span key={z} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: meta.color }}
            />
            {meta.etiqueta}
          </span>
        );
      })}
    </div>
  );
}
