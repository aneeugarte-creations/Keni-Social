import type { MarcaDisponible } from "../types.gen";

// --------------------------------------------------------------------------- //
// Texto de documentos (prompts + línea editorial)                         //
// --------------------------------------------------------------------------- //

export type TipoDocumento = "prompt" | "editorial";

/** Un documento de la texto (prompt o pieza editorial). */
export interface DocumentoTexto {
  id: string;
  titulo: string;
  /** Explicación humana (qué es / para qué). NO se inyecta en ningún prompt; solo UI. */
  descripcion?: string;
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
  /** Tags transversales (navegación / facetas). */
  etiquetas?: string[];
  /** Pipelines a los que se ata el doc (atribución). [] = aplica a todos los pipelines. */
  pipelines?: string[];
  /** Solo prompt: rol que ata el prompt a un pipeline (copy | verificación | evergreen | arte | ""). */
  rol?: string;
  /** Orden de ensamblaje del auto-adjunto (menor = antes). */
  prioridad?: number;
  /**
   * SOLO LECTURA (transparencia): procesos/agentes a los que se INYECTA este prompt. Sale del
   * catálogo en código (`prompts_procesos`), no del contenido editable. [] = sin catalogar.
   */
  procesos?: string[];
  /**
   * SOLO LECTURA: contrato de salida (forma del JSON que exige el parser) de un prompt
   * ESTRUCTURADO, o `null`/ausente si su salida es prosa. Vive en código (`prompts_contratos`),
   * NO en el cuerpo editable: el editor oculta su placeholder y lo pinta read-only aparte.
   */
  contrato_salida?: string | null;
  /**
   * Versión PUBLICADA (la que sirven los pipelines), o `null` si nunca se publicó.
   * Opcionales mientras el backend del flujo de publicación se despliega en paralelo.
   */
  produccion?: ProduccionTexto | null;
  /** SHA del borrador actual (HEAD del historial git), o `null` sin versionado. */
  sha_actual?: string | null;
  /** `true` si el borrador actual difiere de lo publicado (hay cambios sin publicar). */
  sin_publicar?: boolean;
  /**
   * Hash de revisión (estilo ETag) del working copy: el cliente lo echa al guardar y el
   * backend rechaza con 409 si otro editor guardó debajo (concurrencia optimista).
   */
  rev?: string;
}

/** Resumen de facetas para poblar los filtros de navegación. */
export interface FacetasTexto {
  etiquetas: { valor: string; total: number }[];
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
  adjuntos: AdjuntoInyectado[];
}

/** Un documento editorial que un prompt INYECTA (forma de `adjuntos`, en orden de ensamblaje). */
export interface AdjuntoInyectado {
  id: string;
  titulo: string;
  clase: string;
  prioridad: number;
}

/**
 * `GET /api/prompts/{id}/contexto?marca=`: los editoriales que ese prompt inyecta para una marca.
 * `inyecta=false` (con `adjuntos` vacío y `pipeline=null`) si el prompt no lleva contexto editorial.
 */
export interface RespuestaContextoInyectado {
  prompt_id: string;
  inyecta: boolean;
  pipeline: string | null;
  marca: string;
  adjuntos: AdjuntoInyectado[];
}

/** Versión PUBLICADA (en producción) de un documento: la que sirven los pipelines. */
export interface ProduccionTexto {
  sha: string;
  autor: string;
  nota: string;
  creado: string;
}

/** Una variable `{{NOMBRE}}` del catálogo (`GET /api/prompts/variables`). `nombre` SIN llaves. */
export interface VariableCatalogo {
  nombre: string;
  descripcion: string;
  ejemplo: string;
  /** De dónde sale el valor al inyectar (p. ej. "marca activa", "noticia"). */
  origen: string;
}

export interface RespuestaVariablesTexto {
  variables: VariableCatalogo[];
}

/** Estado de una solicitud de publicación. */
export type EstadoSolicitud = "abierta" | "aprobada" | "rechazada";

/** Solicitud de publicación de una versión de un documento (flujo no-admin). */
export interface SolicitudPieza {
  id: string;
  doc_id: string;
  titulo: string;
  sha_propuesto: string;
  autor: string;
  nota: string;
  estado: EstadoSolicitud | string;
  revisor?: string | null;
  comentario?: string | null;
  creado: string;
  resuelto?: string | null;
}

export interface RespuestaSolicitudesTexto {
  solicitudes: SolicitudPieza[];
}

export interface RespuestaSolicitudTexto {
  solicitud: SolicitudPieza;
}

/** Respuesta de aprobar una solicitud (rechazar no devuelve `documento`). */
export interface RespuestaResolverSolicitud {
  solicitud: SolicitudPieza;
  documento?: DocumentoTexto;
}

/** Cuerpo de `POST /texto/{id}/publicar` y `POST /texto/{id}/solicitar`. */
export interface CuerpoPublicarTexto {
  /** Versión a publicar; omitido = la versión actual (HEAD). */
  sha?: string;
  /** Nota de cambio (obligatoria en la UI). */
  nota: string;
}

/** Cuerpo de aprobar/rechazar una solicitud. */
export interface CuerpoResolverSolicitud {
  comentario?: string;
}

/** Campos de estado de publicación compartidos por etapas y capas de la máquina. */
export interface EstadoPiezaDoc {
  produccion: ProduccionTexto | null;
  sha_actual: string | null;
  sin_publicar: boolean;
}

/**
 * Etapa MECÁNICA del flujo (`GET /api/prompts/maquina`): paso del proceso SIN prompt de la
 * Prompts (código puro o prompt hardcodeado). Da contexto: cuenta la historia completa.
 */
export interface EtapaMecanica {
  tipo: "mecanica";
  id: string;
  titulo: string;
}

/** Etapa con PROMPT editable: el documento de la Prompts que se inyecta en ese paso. */
export interface EtapaPrompt extends EstadoPiezaDoc {
  tipo: "prompt";
  id: string;
  titulo: string;
  doc_id: string;
  /** Sección visual opcional: `"taller"` separa el evergreen del flujo principal. */
  seccion?: string;
}

/** Una etapa del flujo, discriminada por `tipo`. */
export type EtapaMaquina = EtapaMecanica | EtapaPrompt;

/** Una de las TRES máquinas del ADR 0011 (investigacion | produccion | importacion). */
export interface MaquinaTexto {
  id: string;
  titulo: string;
  subtitulo: string;
  etapas: EtapaMaquina[];
}

/** `GET /api/prompts/maquina`: las tres máquinas en orden, con sus etapas. Flujo GLOBAL. */
export interface RespuestaMaquinaTexto {
  maquinas: MaquinaTexto[];
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

/** `GET /api/prompts`: documentos filtrados + carpetas existentes + facetas. */
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

export interface RespuestaMarcasTexto {
  marcas: MarcaDisponible[];
}

export interface CuerpoCrearDocumento {
  titulo: string;
  descripcion?: string;
  tipo?: TipoDocumento;
  carpeta?: string;
  cuerpo?: string;
  clase?: string;
  marcas?: string[];
  etiquetas?: string[];
  pipelines?: string[];
  rol?: string;
  prioridad?: number;
}

export interface CuerpoGuardarDocumento {
  titulo?: string;
  descripcion?: string;
  cuerpo?: string;
  carpeta?: string;
  clase?: string;
  marcas?: string[];
  etiquetas?: string[];
  pipelines?: string[];
  rol?: string;
  prioridad?: number;
  /** Revisión base (ETag) que cargó el cliente: el backend devuelve 409 si cambió debajo. */
  rev?: string;
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
