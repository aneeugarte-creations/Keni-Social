import type { MarcaDisponible } from "../types.gen";

// --------------------------------------------------------------------------- //
// Texto de documentos (prompts + línea editorial)                         //
// --------------------------------------------------------------------------- //

export type TipoDocumento = "prompt" | "editorial";

/** Un documento de la texto (prompt o pieza editorial). */
export interface DocumentoTexto {
  id: string;
  titulo: string;
  tipo: TipoDocumento | string;
  carpeta: string;
  cuerpo: string;
  creado: string;
  actualizado: string;
  /** Solo editorial: marca | voz | plataforma | tropicalizacion | reglas (o ""). */
  clase: string;
  /** Solo editorial: marcas a las que aplica (para el auto-adjunto). */
  marcas: string[];
  /** Solo prompt: "" | "documento" (texto) | "piezas" (copy por red -> borradores). */
  salida?: string;
  /** Ciclo de vida: activo | borrador | archivado. Solo `activo` se inyecta en pipelines. */
  estado?: string;
  /** Tags transversales (navegación / facetas). */
  etiquetas?: string[];
  /** Pipelines a los que se ata el doc (atribución). [] = aplica a todos los pipelines. */
  pipelines?: string[];
  /** Solo prompt: rol que ata el prompt a un pipeline (copy | qa | evergreen | arte | ""). */
  rol?: string;
  /** Orden de ensamblaje del auto-adjunto (menor = antes). */
  prioridad?: number;
}

/** Resumen de facetas para poblar los filtros de navegación. */
export interface FacetasTexto {
  etiquetas: { valor: string; total: number }[];
  estados: Record<string, number>;
  pipelines: Record<string, number>;
}

/** Un pipeline de generación (registro): su prompt base efectivo y rol esperado. */
export interface PipelineTexto {
  id: string;
  titulo: string;
  descripcion: string;
  rol: string;
  prompt_base_id: string;
}

export interface RespuestaPipelinesTexto {
  pipelines: PipelineTexto[];
}

/** Preview del prompt ENSAMBLADO de un pipeline (lo que recibiría claude -p). */
export interface PreviewPipeline {
  pipeline: string;
  prompt_base_id: string;
  falta_base: boolean;
  prompt_efectivo: string;
  adjuntos: { id: string; titulo: string; clase: string; prioridad: number }[];
}

/** Una entrada del historial de versiones (git) de un documento. */
export interface VersionTexto {
  sha: string;
  sha_corto: string;
  fecha: string;
  autor: string;
  mensaje: string;
}

export interface RespuestaHistorialTexto {
  historial: VersionTexto[];
}

/** `GET /api/texto`: documentos filtrados + carpetas existentes + facetas. */
export interface RespuestaTexto {
  documentos: DocumentoTexto[];
  carpetas: string[];
  facetas?: FacetasTexto;
}

export interface RespuestaDocumento {
  documento: DocumentoTexto;
}

export interface ItemPapelera {
  id: string;
  titulo: string;
  tipo: string;
  /** Id de origen al que se restauraría. */
  origen: string;
}

export interface RespuestaPapelera {
  papelera: ItemPapelera[];
}

export interface RespuestaEditoriales {
  editoriales: DocumentoTexto[];
}

/** Diagnóstico de los 4 pilares de la línea editorial de una marca (GET /texto/validacion). */
export interface ValidacionEditorial {
  completa: boolean;
  faltan: string[];
  recomendacion: string;
  pilares: Record<string, boolean>;
}

export interface AreaTexto {
  id: string;
  nombre: string;
}

export interface RespuestaAreas {
  areas: AreaTexto[];
}

export interface RespuestaMarcasTexto {
  marcas: MarcaDisponible[];
}

export interface CuerpoCrearDocumento {
  titulo: string;
  tipo?: TipoDocumento;
  carpeta?: string;
  cuerpo?: string;
  clase?: string;
  marcas?: string[];
  estado?: string;
  etiquetas?: string[];
  pipelines?: string[];
  rol?: string;
  prioridad?: number;
}

export interface CuerpoGuardarDocumento {
  titulo?: string;
  cuerpo?: string;
  carpeta?: string;
  clase?: string;
  marcas?: string[];
  estado?: string;
  etiquetas?: string[];
  pipelines?: string[];
  rol?: string;
  prioridad?: number;
}

/** Target sobre el que se lanza un prompt. */
export interface TargetLanzamiento {
  tipo: "ninguno" | "contenido" | "url" | "area";
  valor?: string;
}

export interface CuerpoLanzarTexto {
  prompt_id?: string;
  texto?: string;
  titulo?: string;
  marca: string;
  /** Ids de documentos editoriales a adjuntar. */
  adjuntos?: string[];
  target?: TargetLanzamiento;
  /** Solo prompts salida=piezas: redes objetivo del copy (ids de red). */
  redes?: string[];
}
