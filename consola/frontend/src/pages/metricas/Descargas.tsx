/**
 * Descargas del dashboard de Métricas en CSV / Markdown / JSON: comandos del menú "⋮"
 * de la página (descargar es una ACCIÓN global, no un control del cuerpo).
 *
 * Dos grupos (separados):
 *   - "Reporte (…)": el reporte agregado del periodo (`api.exportarMetricas`).
 *   - "Top y peores piezas (…)": el Top 5 / Peores 5 de piezas del periodo
 *     (`api.exportarPiezas`, endpoint `/api/metricas/piezas-export`).
 *
 * Ambos reutilizan el rango y la marca activos del reporte; el cliente API abre la
 * URL de descarga del backend.
 */
import { Download } from "lucide-react";

import { ItemMenu } from "@/components/layout/MenuAcciones";
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

/** Items de descarga para meter DENTRO de un `<MenuAcciones/>`. */
export function ItemsDescargas({ rango, marca }: DescargasProps) {
  return (
    <>
      {FORMATOS.map(({ formato, etiqueta }) => (
        <ItemMenu
          key={`reporte-${formato}`}
          icono={Download}
          onClick={() => api.exportarMetricas(formato, { rango, marca })}
        >
          {`Reporte (${etiqueta})`}
        </ItemMenu>
      ))}
      <div role="separator" aria-orientation="horizontal" className="my-1 h-px bg-border" />
      {FORMATOS.map(({ formato, etiqueta }) => (
        <ItemMenu
          key={`piezas-${formato}`}
          icono={Download}
          onClick={() => api.exportarPiezas(formato, { rango, marca })}
        >
          {`Top y peores piezas (${etiqueta})`}
        </ItemMenu>
      ))}
    </>
  );
}
