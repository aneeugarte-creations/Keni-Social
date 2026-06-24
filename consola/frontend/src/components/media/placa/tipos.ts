/**
 * Tipos y constantes compartidos del editor de placa inline (`EditorPlacaInline` y sus
 * sub-componentes en `components/media/placa/`).
 */
import type { OrigenImagenPropio } from "@/components/media/EditorImagen";
import type { Documento } from "@/editor/documento";
import type { FotoCollage } from "@/lib/placa/docPieza";
import type { DatosStock } from "@/lib/stock";
import type { PlataformaStock } from "@/types";

/** Lienzo por defecto del post de foto (4:5) cuando no hay plantilla (foto cruda). */
export const LIENZO_4_5 = { w: 1080, h: 1350, safe_top: 0, safe_bottom: 0 };

export interface EditorPlacaInlineProps {
  marca: string;
  /** Id de la publicación que se edita: al generar imagen con IA, correlaciona la generación
   * con el pipeline de la pieza (etapa Arte) en vez de quedar como una generación suelta. */
  piezaId?: string;
  /** Plantilla del estudio elegida (documento de capas). `null` = sin plantilla = foto cruda. */
  documento: Documento | null;
  /** Titular en vivo (texto DENTRO de la imagen / copy-in de la pieza). */
  copyIn: string;
  /** Edita el titular: el copy-in es clicable y reescribible IN PLACE sobre la plantilla. */
  onCopyInCambio?: (valor: string) => void;
  /** Copy de la pieza (contenido del post): se usa como SUGERENCIA del prompt al generar con IA. */
  copy?: string;
  /** Título del TEMA de la pieza: respaldo de la consulta inicial del buscador de fotos de stock. */
  titulo?: string;
  /** Keyword visual que propone Sugerir hashtags (`imagen_clave`): consulta por defecto del buscador
   *  de stock; cae al tema del título si no la hay. */
  imagenClave?: string;
  /** Una foto por HUECO (collage), en orden de `capas`. `fotos[i]` va al hueco `es_foto` i. */
  fotos: FotoCollage[];
  /** Notifica un cambio en el array de fotos (foto/reencuadre de algún hueco). */
  onFotosCambio: (fotos: FotoCollage[]) => void;
  /**
   * REEMPLAZO del FONDO (hueco 0) por una foto PROPIA (subir/galería/IA): declara su origen propio
   * para que el padre lo mande al guardar y el back LIMPIE el metadato de licencia heredado (p. ej.
   * de una foto de stock). NO se llama al reemplazar por el BUSCADOR de stock/agencias (el server
   * fija ese origen), ni al editar solo TEXTO/diseño, ni al tocar un hueco secundario del collage.
   */
  onOrigenPropio?: (origen: OrigenImagenPropio) => void;
  /** URL de la imagen original (RSS de marca propia), si la pieza la trae. */
  imagenFuente?: string;
  /** "Sin plantilla": publicar solo la foto cruda (sin la plantilla encima). */
  sinPlantilla: boolean;
  /** Alterna "sin plantilla" (icono de plantilla tachada). */
  onAlternarSinPlantilla: () => void;
  /** Abre la galería de plantillas del estudio (selector nativo en la cabecera). */
  onAbrirGaleria?: () => void;
  /**
   * Estado de imagen de STOCK de la pieza (origen/proveedor/autorización). Con `piezaId`, habilita
   * "Buscar foto", el tratamiento "SIN LICENCIA" sobre el lienzo y el control de autorizar.
   */
  stock?: DatosStock;
  /** Notifica que la imagen de stock cambió (adjuntar/autorizar): el padre recarga la pieza. */
  onStockCambio?: (plataforma: PlataformaStock) => void;
}
