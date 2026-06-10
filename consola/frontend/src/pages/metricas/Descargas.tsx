/**
 * Descargas del dashboard de Métricas en CSV / Markdown / JSON.
 *
 * Un único menú con dos grupos (separados):
 *   - "Reporte (…)": el reporte agregado del periodo (`api.exportarMetricas`).
 *   - "Top y peores piezas (…)": el Top 5 / Peores 5 de piezas del periodo
 *     (`api.exportarPiezas`, endpoint `/api/metricas/piezas-export`).
 *
 * Ambos reutilizan el rango y la marca activos del reporte; el cliente API abre la
 * URL de descarga del backend.
 */
import { ChevronDown, Download } from "lucide-react";

import {
  MenuContextual,
  type EntradaMenuContextual,
} from "@/components/comunes/MenuContextual";
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
  const items: EntradaMenuContextual[] = [
    ...FORMATOS.map(({ formato, etiqueta }) => ({
      etiqueta: `Reporte (${etiqueta})`,
      icono: Download,
      onClick: () => api.exportarMetricas(formato, { rango, marca }),
    })),
    { separador: true },
    ...FORMATOS.map(({ formato, etiqueta }) => ({
      etiqueta: `Top y peores piezas (${etiqueta})`,
      icono: Download,
      onClick: () => api.exportarPiezas(formato, { rango, marca }),
    })),
  ];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <MenuContextual disparador="click" etiqueta="Descargar reporte" items={items}>
        <Button variant="outline" size="sm">
          <Download className="h-4 w-4" />
          Descargar
          <ChevronDown className="h-4 w-4 opacity-60" />
        </Button>
      </MenuContextual>
    </div>
  );
}
