/**
 * Render de la placa de marca EN EL NAVEGADOR, sobre un `<canvas>` 2D, reutilizando el MISMO
 * motor que el servidor (`dibujar.mjs`, espejo byte-a-byte de `render_node/dibujar.mjs`). Así
 * la previa en vivo del editor coincide exactamente con lo que compone el servidor (auto-gen),
 * sin round-trips: el titular se "escribe" sobre la imagen a medida que se teclea.
 */
import type { FormatoId, FormatoSpec, PlantillaSpec } from "@/lib/specPlantilla";

import { dibujarSpec } from "./dibujar.mjs";
import type { DibujarSpecArgs, ImgsPlaca } from "./dibujar.mjs";

export type { ImgsPlaca };

/** Resuelve una familia lógica ("sans"/"condensada") al nombre real (espejo de `fuentes.mjs`). */
export function familiaRealDe(
  fuentes: PlantillaSpec["fuentes"],
): (logica: string) => string {
  return (logica: string) => {
    if (logica === "sans") return fuentes?.sans || "Barlow";
    if (logica === "condensada") return fuentes?.condensada || "Barlow Condensed";
    return logica || "Barlow";
  };
}

/** Formato de placa para una red (espejo de `estudio_imagen.formato_por_red`).
 *  Regla de producto: todo POST DE FOTO va en 4:5 (`feed`) sea cual sea la red. Solo el video
 *  nativo vertical (tiktok) cae a 9:16; los reels/stories no pasan por esta placa de foto. */
export function formatoPorRed(red: string | undefined): FormatoId {
  if (red === "tiktok") return "vertical";
  return "feed"; // instagram, facebook, x, youtube y desconocidas -> 4:5
}

/** Dibuja la placa (o solo la foto si `imgs.placeholder`/sin marca) en el contexto dado. */
export function dibujarPlaca(
  ctx: CanvasRenderingContext2D,
  args: {
    formato: FormatoSpec;
    fuentes: PlantillaSpec["fuentes"];
    bindings: { copy_in: string; etiqueta_default: string };
    placeholder: boolean;
    imgs: ImgsPlaca;
  },
): void {
  const completo: DibujarSpecArgs = { ...args, familiaReal: familiaRealDe(args.fuentes) };
  dibujarSpec(ctx, completo);
}
