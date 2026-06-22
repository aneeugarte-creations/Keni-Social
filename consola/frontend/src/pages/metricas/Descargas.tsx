/**
 * Descargas del dashboard de Métricas: DOS comandos del menú "⋮" de la página, CSV y PDF.
 *
 *   - "Descargar CSV": TODO lo que está en pantalla volcado a un único CSV (KPIs, por marca,
 *     por red, cobertura, tendencia, seguidores, desglose, cruces, correlación, líneas,
 *     publicidad y las listas de piezas), leído de las queries ACTIVAS de la caché de React
 *     Query con el filtro de marca/red/periodo ya aplicado. Ver `exportarCsv.ts`.
 *   - "Descargar PDF (presentación)": maqueta el dashboard como deck horizontal y abre
 *     "Guardar como PDF" del navegador (motor de impresión nativo: gráficas vectoriales,
 *     idéntico a pantalla, sin rasterizar). Ver `exportarPdf.ts`.
 *
 * Viven en el "⋮" (no como botones sueltos) para no saturar la barra superior: la cabecera
 * deja sitio a los FILTROS (periodo, red) y a Configurar vista / Vistas guardadas.
 */
import { useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Presentation } from "lucide-react";
import { toast } from "sonner";

import { ItemMenu } from "@/components/layout/MenuAcciones";

import { construirCsvCompleto, descargarTexto } from "./exportarCsv";
import { imprimirPresentacion } from "./exportarPdf";

interface ItemsDescargaProps {
  rango: string;
  /** `undefined` cuando está seleccionada la opción "Todas las marcas". */
  marca?: string;
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

/** Comandos de descarga (CSV + PDF) para meter DENTRO de un `<MenuAcciones/>`. */
export function ItemsDescarga({
  rango,
  marca,
  marcaEtiqueta,
  redEtiqueta,
  periodoEtiqueta,
  generadoEn,
}: ItemsDescargaProps) {
  const qc = useQueryClient();

  const descargarCsv = () => {
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
    const nombre = [marca ?? "todas", redEtiqueta, rango].map(slug).filter(Boolean).join("-");
    descargarTexto(`analiticas-${nombre}.csv`, csv, "text/csv;charset=utf-8");
    toast.success("CSV completo descargado.");
  };

  const exportarPdf = () => {
    try {
      imprimirPresentacion({
        marca: marcaEtiqueta,
        red: redEtiqueta,
        periodo: periodoEtiqueta,
        generadoEn,
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo preparar el PDF.");
    }
  };

  return (
    <>
      <ItemMenu icono={FileSpreadsheet} onClick={descargarCsv}>
        Descargar CSV (todo)
      </ItemMenu>
      <ItemMenu icono={Presentation} onClick={exportarPdf}>
        Descargar PDF (presentación)
      </ItemMenu>
    </>
  );
}
