/**
 * Tipos y constantes compartidos del editor de placa inline (`EditorPlacaInline` y sus
 * sub-componentes en `components/media/placa/`).
 */
import type { Documento } from "@/editor/documento";
import type { FotoCollage } from "@/lib/placa/docPieza";

/** Lienzo por defecto del post de foto (4:5) cuando no hay plantilla (foto cruda). */
export const LIENZO_4_5 = { w: 1080, h: 1350, safe_top: 0, safe_bottom: 0 };

export interface EditorPlacaInlineProps {
  marca: string;
  /** Plantilla del estudio elegida (documento de capas). `null` = sin plantilla = foto cruda. */
  documento: Documento | null;
  /** Titular en vivo (texto DENTRO de la imagen / copy-in de la pieza). */
  copyIn: string;
  /** Edita el titular: el copy-in es clicable y reescribible IN PLACE sobre la plantilla. */
  onCopyInCambio?: (valor: string) => void;
  /** Copy de la pieza (contenido del post): se usa como SUGERENCIA del prompt al generar con IA. */
  copy?: string;
  /** Una foto por HUECO (collage), en orden de `capas`. `fotos[i]` va al hueco `es_foto` i. */
  fotos: FotoCollage[];
  /** Notifica un cambio en el array de fotos (foto/reencuadre de algún hueco). */
  onFotosCambio: (fotos: FotoCollage[]) => void;
  /** URL de la imagen original (RSS de marca propia), si la pieza la trae. */
  imagenFuente?: string;
  /** "Sin plantilla": publicar solo la foto cruda (sin la plantilla encima). */
  sinPlantilla: boolean;
  /** Alterna "sin plantilla" (icono de plantilla tachada). */
  onAlternarSinPlantilla: () => void;
  /** Abre la galería de plantillas del estudio (selector nativo en la cabecera). */
  onAbrirGaleria?: () => void;
}
