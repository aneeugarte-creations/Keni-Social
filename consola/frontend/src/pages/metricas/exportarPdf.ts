/**
 * Exportación del dashboard de Métricas a un PDF "presentación" (deck 16:9). Monta el informe
 * REAL (`<Informe>`: los mismos componentes Tremor que la app, marca protagonista, esquema
 * Sereno, conclusiones) fuera de pantalla a tamaño real, rasteriza cada diapositiva con
 * `html-to-image` y compone un jsPDF (una página por diapositiva, 1280×720). Los datos salen
 * de las queries activas de React Query (`desdeEntradas`), los mismos que el CSV.
 */
import { createElement } from "react";

import { importarModulo, rasterizarDeckAPdf } from "@/lib/rasterizarDeck";
import { comprobarVersionNueva, recargaSegura } from "@/lib/version";
import type { RangoMetrica } from "@/types";

import { desdeEntradas } from "./informe/desdeEntradas";
import { diasDePeriodo, partesMes, partesRango } from "./rango";

const MESES_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** Etiqueta legible de un token de periodo (preset, `mes:` o `rango:`). */
export function etiquetaPeriodo(token: string, rangos: RangoMetrica[]): string {
  const preset = rangos.find((r) => r.id === token);
  if (preset) return preset.etiqueta;
  const mes = partesMes(token);
  if (mes) return `${MESES_ES[mes.mes - 1]} ${mes.anio}`;
  const rango = partesRango(token);
  if (rango) return `${rango.desde} – ${rango.hasta}`;
  const dias = diasDePeriodo(token);
  return dias != null ? `Últimos ${dias} días` : token;
}

export interface ContextoDeck {
  marca: string;
  red: string;
  formato: string;
  periodo: string;
  generadoEn?: string;
  /** Id de métricas de la marca (`claro_sports`, …) para resolver su logo; ausente si todas. */
  marcaId?: string;
}

/**
 * Genera y DESCARGA el PDF presentación: monta `<Informe>` oculto a tamaño real, rasteriza
 * cada `.informe-slide` y la coloca como página del jsPDF. Lanza si no hay datos.
 */
export async function descargarPresentacion(
  entradas: Array<[readonly unknown[], unknown]>,
  ctx: ContextoDeck,
  nombreArchivo: string,
): Promise<void> {
  if (entradas.length === 0) throw new Error("No hay datos cargados para el PDF.");

  // Antes de montar nada: si ya hay un deploy más reciente que ESTE bundle, la pestaña tiene el
  // JS antiguo en memoria y el deck saldría con el diseño viejo (causa típica de "lo arreglé pero
  // el PDF sigue igual": una pestaña abierta desde antes del deploy). Refrescamos para generar el
  // PDF con el diseño DESPLEGADO; tras la recarga el usuario vuelve a pulsar. Timeout corto: si
  // `/version.json` no responde, seguimos sin bloquear (comprobarVersionNueva nunca lanza).
  {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 2500);
    let hayNueva = false;
    try {
      hayNueva = await comprobarVersionNueva(ac.signal);
    } finally {
      clearTimeout(t);
    }
    if (hayNueva && recargaSegura()) await new Promise<never>(() => {}); // la recarga corta la ejecución
  }

  const props = desdeEntradas(entradas, ctx);
  const { Informe } = await importarModulo(() => import("./informe/Informe"));
  await rasterizarDeckAPdf(createElement(Informe, { data: props }), nombreArchivo);
}
