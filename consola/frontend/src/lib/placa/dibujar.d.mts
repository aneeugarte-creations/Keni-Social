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

// Render del DOCUMENTO de capas (editor profesional). Misma rutina canvas-2D, sobre una lista de
// capas arbitrarias. `imgs` mapea objeto|media_id -> imagen ya cargada (o null).
// `final: true` = render del píxel final (ignora `visible: false`); sin `final` = previa de edición.
export interface DibujarDocumentoArgs {
  documento: import("../../editor/documento").Documento;
  imgs: Record<string, CanvasImageSource | null>;
  bindings?: { copy_in?: string; etiqueta_default?: string };
  familiaReal: (logica: string) => string;
  final?: boolean;
}

export function dibujarDocumento(ctx: CanvasRenderingContext2D, args: DibujarDocumentoArgs): void;

// Mapa etiqueta de modo de fusión -> `globalCompositeOperation`. Compartido con el editor (Konva)
// para que la previa y el export usen el mismo modo. "normal" => "source-over".
export const MAPA_MEZCLA: Record<import("../../editor/documento").TipoMezcla, string>;
