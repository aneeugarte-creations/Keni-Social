/**
 * Descargas del dashboard de Métricas: DOS acciones, CSV y PDF presentación.
 *
 *   - "CSV": TODO lo que está en pantalla volcado a un único CSV (KPIs, por marca, por red,
 *     cobertura, tendencia, seguidores, desglose, cruces, correlación, líneas, publicidad y
 *     las listas de piezas), leído de las queries ACTIVAS de la caché de React Query con el
 *     filtro de marca/red/periodo ya aplicado. Ver `exportarCsv.ts`.
 *   - "PDF": un deck 16:9 "presentación" generado en el navegador a partir del ESTADO VIVO
 *     de la página, capturando los bloques `[data-slide]` del cuerpo. Ver `exportarPdf.ts`.
 *
 * Reemplaza al antiguo menú de 6 formatos (reporte/piezas × csv/md/json): el equipo de AMX
 * solo necesita un CSV completo para hojas de cálculo y un PDF listo para presentar a dirección.
 */
import { useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Loader2, Presentation } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { construirCsvCompleto, descargarTexto } from "./exportarCsv";
import { exportarPresentacion } from "./exportarPdf";

interface BotonesDescargaProps {
  rango: string;
  /** `undefined` cuando está seleccionada la opción "Todas las marcas". */
  marca?: string;
  /** Red en foco (id de plataforma), o `undefined` cuando son "Todas las redes". */
  red?: string;
  /** Etiqueta legible de la marca activa (o "Todas las marcas"). */
  marcaEtiqueta: string;
  /** Etiqueta legible de la red activa (o "Todas las redes"). */
  redEtiqueta: string;
  /** Etiqueta legible del periodo. */
  periodoEtiqueta: string;
  /** ISO de generación del reporte, para el pie de la portada. */
  generadoEn?: string;
}

/** Slug minimal para el nombre del archivo (sin acentos ni espacios). */
function slug(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

/** Los dos botones de descarga (CSV + PDF) para la barra de acciones de la página. */
export function BotonesDescarga({
  rango,
  marca,
  marcaEtiqueta,
  redEtiqueta,
  periodoEtiqueta,
  generadoEn,
}: BotonesDescargaProps) {
  const [generandoPdf, setGenerandoPdf] = React.useState(false);
  const qc = useQueryClient();

  const nombreArchivo = React.useMemo(
    () =>
      [marca ?? "todas", redEtiqueta, rango]
        .map((p) => slug(String(p)))
        .filter(Boolean)
        .join("-"),
    [marca, redEtiqueta, rango],
  );

  // CSV completo: vuelca las queries ACTIVAS de métricas (= las secciones montadas en
  // pantalla), con el filtro de marca/red/periodo ya aplicado. Síncrono y al instante.
  const descargarCsv = React.useCallback(() => {
    const entradas = qc.getQueriesData({ queryKey: ["metricas"], type: "active" }) as Array<
      [readonly unknown[], unknown]
    >;
    const conDatos = entradas.filter(([, d]) => d != null);
    if (conDatos.length === 0) {
      toast.error("No hay datos cargados que exportar.");
      return;
    }
    const csv = construirCsvCompleto(conDatos, {
      marca: marcaEtiqueta,
      red: redEtiqueta,
      periodo: periodoEtiqueta,
      generadoEn,
    });
    descargarTexto(`analiticas-${nombreArchivo}.csv`, csv, "text/csv;charset=utf-8");
    toast.success("CSV completo descargado.");
  }, [qc, marcaEtiqueta, redEtiqueta, periodoEtiqueta, generadoEn, nombreArchivo]);

  const descargarPdf = React.useCallback(async () => {
    const raiz = document.querySelector<HTMLElement>("[data-deck-root]");
    if (!raiz) {
      toast.error("No se encontró el contenido del dashboard.");
      return;
    }
    setGenerandoPdf(true);
    try {
      await exportarPresentacion({
        raiz,
        marca: marcaEtiqueta,
        red: redEtiqueta,
        periodo: periodoEtiqueta,
        generadoEn,
        nombreArchivo,
      });
      toast.success("PDF de presentación generado.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo generar el PDF.");
    } finally {
      setGenerandoPdf(false);
    }
  }, [marcaEtiqueta, redEtiqueta, periodoEtiqueta, generadoEn, nombreArchivo]);

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="h-8 gap-1.5 text-xs"
        onClick={descargarCsv}
      >
        <FileSpreadsheet className="h-4 w-4" />
        CSV
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="h-8 gap-1.5 text-xs"
        onClick={() => void descargarPdf()}
        disabled={generandoPdf}
      >
        {generandoPdf ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Presentation className="h-4 w-4" />
        )}
        PDF
      </Button>
    </>
  );
}
