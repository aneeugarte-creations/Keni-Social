/**
 * Descarga del reporte actual en CSV / Markdown / JSON.
 *
 * Reutilizan el rango y la marca activos del reporte y delegan en
 * `api.exportarMetricas`, que abre la URL de descarga del backend.
 */
import { ChevronDown, Download } from "lucide-react";

import { MenuContextual } from "@/components/comunes/MenuContextual";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

interface DescargasProps {
  rango: string;
  /** `undefined` cuando está seleccionada la opción "Todas las marcas". */
  marca?: string;
}

const FORMATOS: Array<{ formato: "csv" | "md" | "json"; etiqueta: string }> = [
  { formato: "csv", etiqueta: "CSV" },
  { formato: "md", etiqueta: "Markdown" },
  { formato: "json", etiqueta: "JSON" },
];

export function Descargas({ rango, marca }: DescargasProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <MenuContextual
        disparador="click"
        etiqueta="Descargar reporte"
        items={FORMATOS.map(({ formato, etiqueta }) => ({
          etiqueta,
          icono: Download,
          onClick: () => api.exportarMetricas(formato, { rango, marca }),
        }))}
      >
        <Button variant="outline" size="sm">
          <Download className="h-4 w-4" />
          Descargar
          <ChevronDown className="h-4 w-4 opacity-60" />
        </Button>
      </MenuContextual>
    </div>
  );
}
