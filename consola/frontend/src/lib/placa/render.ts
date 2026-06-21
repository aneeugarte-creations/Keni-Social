/**
 * Render de la placa de marca EN EL NAVEGADOR, sobre un `<canvas>` 2D, reutilizando el MISMO
 * motor que el servidor (`dibujar.mjs`, espejo byte-a-byte de `render_node/dibujar.mjs`). Así
 * la previa en vivo del editor coincide exactamente con lo que compone el servidor (auto-gen),
 * sin round-trips: el titular se "escribe" sobre la imagen a medida que se teclea.
 */
import type { PlantillaSpec } from "@/lib/specPlantilla";

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
