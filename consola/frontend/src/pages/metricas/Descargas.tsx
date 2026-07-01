/**
 * Descargas del dashboard de Métricas: TRES comandos del menú "⋮" de la página.
 *
 *   - "Métricas Digitales": el reporte mensual por plataforma que el equipo entrega a su
 *     dirección (13 meses por red + comparativa de los dos últimos meses). Lo genera el
 *     BACKEND a partir de los últimos 13 meses de la marca activa (no de lo que esté en
 *     pantalla), así que necesita una marca concreta. Ver `api/metricas/_digital.py`.
 *   - "Descargar CSV": TODO lo que está en pantalla volcado a un único CSV (KPIs, por marca,
 *     por red, cobertura, tendencia, seguidores, desglose, cruces, correlación, líneas,
 *     publicidad y las listas de piezas), leído de las queries ACTIVAS de la caché de React
 *     Query con el filtro de marca/red/periodo ya aplicado. Ver `exportarCsv.ts`.
 *   - "Descargar PDF (presentación)": deck 16:9 generado con jsPDF a partir de los MISMOS
 *     datos (portada + KPIs + gráficas vectoriales + tablas). Descarga directa, sin diálogo
 *     ni rasterizar el DOM. Ver `exportarPdf.ts`.
 *
 * Viven en el "⋮" (no como botones sueltos) para no saturar la barra superior: la cabecera
 * deja sitio a los FILTROS (periodo, red) y a Configurar vista / Vistas guardadas.
 */
import { useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Presentation, Table2 } from "lucide-react";
import { toast } from "sonner";

import { ItemMenu } from "@/components/layout/MenuAcciones";
import { api } from "@/lib/api";
import { slug } from "@/lib/formato";

import { construirCsvCompleto, descargarTexto } from "./exportarCsv";
import { descargarPresentacion } from "./exportarPdf";

interface ItemsDescargaProps {
  rango: string;
  /** `undefined` cuando está seleccionada la opción "Todas las marcas". */
  marca?: string;
  /** Etiqueta legible de la marca activa (o "Todas las marcas"). */
  marcaEtiqueta: string;
  /** Etiqueta legible de la red activa (o "Todas las redes"). */
  redEtiqueta: string;
  /** Etiqueta legible del formato activo (o "Todos los formatos"). */
  formatoEtiqueta: string;
  /** Etiqueta legible del periodo. */
  periodoEtiqueta: string;
  /** ISO de generación del reporte, para el pie de la portada. */
  generadoEn?: string;
}

/** Comandos de descarga (CSV + PDF) para meter DENTRO de un `<MenuAcciones/>`. */
export function ItemsDescarga({
  rango,
  marca,
  marcaEtiqueta,
  redEtiqueta,
  formatoEtiqueta,
  periodoEtiqueta,
  generadoEn,
}: ItemsDescargaProps) {
  const qc = useQueryClient();

  // Datasets ACTIVOS de métricas (= las secciones montadas en pantalla, con marca/red/periodo
  // ya aplicados). Fuente común de CSV y PDF.
  const entradasActivas = () =>
    (
      qc.getQueriesData({ queryKey: ["metricas"], type: "active" }) as Array<
        [readonly unknown[], unknown]
      >
    ).filter(([, d]) => d != null);

  const ctx = {
    marca: marcaEtiqueta,
    red: redEtiqueta,
    formato: formatoEtiqueta,
    periodo: periodoEtiqueta,
    generadoEn,
    // Id de métricas de la marca activa (para resolver su logo en el PDF); undefined si todas.
    marcaId: marca,
  };
  const nombre = [marca ?? "todas", redEtiqueta, formatoEtiqueta, rango]
    .map(slug)
    .filter(Boolean)
    .join("-");

  const descargarCsv = () => {
    const conDatos = entradasActivas();
    if (conDatos.length === 0) {
      toast.error("No hay datos cargados que exportar.");
      return;
    }
    descargarTexto(`analiticas-${nombre}.csv`, construirCsvCompleto(conDatos, ctx), "text/csv;charset=utf-8");
    toast.success("CSV completo descargado.");
  };

  const exportarPdf = async () => {
    const conDatos = entradasActivas();
    if (conDatos.length === 0) {
      toast.error("No hay datos cargados que exportar.");
      return;
    }
    try {
      await descargarPresentacion(conDatos, ctx, nombre);
      toast.success("PDF de presentación descargado.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo generar el PDF.");
    }
  };

  // Reporte mensual por plataforma (el Excel de dirección): lo genera el backend a partir de
  // los últimos 13 meses de la marca activa, así que NO depende de lo que esté en pantalla,
  // pero SÍ necesita una marca concreta (no "todas las marcas").
  const descargarDigitales = () => {
    if (!marca) {
      toast.error("Elige una marca para descargar Métricas Digitales.");
      return;
    }
    toast.info("Generando Métricas Digitales… la descarga empezará en breve.");
    api.exportarMetricasDigitales({ marca });
  };

  return (
    <>
      <ItemMenu icono={Table2} onClick={descargarDigitales}>
        Métricas Digitales
      </ItemMenu>
      <ItemMenu icono={FileSpreadsheet} onClick={descargarCsv}>
        Descargar CSV (todo)
      </ItemMenu>
      <ItemMenu icono={Presentation} onClick={() => void exportarPdf()}>
        Descargar PDF (presentación)
      </ItemMenu>
    </>
  );
}
