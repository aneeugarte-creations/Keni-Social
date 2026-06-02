// Tipos para el espejo `dibujar.mjs` (render canvas-2D de la placa). `dibujar.mjs` es un
// ESPEJO BYTE A BYTE del motor del backend (render_node/dibujar.mjs); un test-guard
// (`dibujar.mirror.test.ts`) falla si difieren. Aquí solo declaramos su firma pública para TS.
import type { FormatoSpec } from "../specPlantilla";

export interface ImgsPlaca {
  foto: CanvasImageSource | null;
  logo: CanvasImageSource | null;
  fondo: CanvasImageSource | null;
}

export interface DibujarSpecArgs {
  formato: FormatoSpec;
  fuentes: { sans: string; condensada: string };
  bindings: { copy_in: string; etiqueta_default: string };
  placeholder: boolean;
  imgs: ImgsPlaca;
  familiaReal: (logica: string) => string;
}

export function dibujarSpec(ctx: CanvasRenderingContext2D, args: DibujarSpecArgs): void;
