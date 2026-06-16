import type { MetricasRun, Paginacion, Publicacion } from "../types.gen";
import type { PiezaGenerada, Veredicto } from "./comun";
import type { ErrorImportCalendario } from "./catalogo";

// --- Generaciones (trabajos de IA en segundo plano, seguibles en vivo) ---

/** Tipo de trabajo de IA: define cómo se renderiza su `resultado`. */
export type TipoGeneracion =
  | "copy"
  | "rss"
  | "hashtags"
  | "imagen"
  | "verificacion"
  | "revision";

/** Estado del ciclo de vida de una generación. */
export type EstadoGeneracion = "ejecutando" | "completado" | "error";

/**
 * Etapa de PROGRESO de una generación (en qué etapa va, no cuánto falta). La deriva el
 * backend del propio stream: `razonando` (arrancó, aún sin texto visible) →
 * `generando` (escribiendo el copy token a token) → `completado` (terminó). `""` en
 * registros legados o antes de arrancar (la UI cae a su comportamiento previo).
 */
export type FaseGeneracion = "razonando" | "generando" | "completado" | "";

/**
 * Resultado de una generación COMPLETADA. Los campos presentes dependen del
 * `tipo`: copy/rss traen `{resultado, historial_id, verdicto, piezas,
 * publicaciones}`; hashtags trae `{hashtags}`; imagen trae `{id, url}`.
 */
export interface ResultadoGeneracion {
  // copy / rss
  resultado?: string;
  historial_id?: string;
  verdicto?: Veredicto;
  piezas?: PiezaGenerada[];
  publicaciones?: Publicacion[];
  /** Documento Markdown completo (prompts con `salida === "documento"`). */
  documento?: string;
  // hashtags
  hashtags?: string[];
  // imagen
  id?: string;
  url?: string;
  /** Modelo de imagen que la produjo (lanzamiento manual de arte). */
  modelo?: string;
  /** Coste en USD de esta imagen (lanzamiento manual de arte); 0 si no se reportó. */
  coste_usd?: number;
  /**
   * Imágenes producidas por el estudio de imagen, ya importadas al
   * almacén de media para previsualizarlas. Cada una trae su `nombre` y la `url`
   * (`/api/media/...`). Vacío o ausente si no se generaron imágenes.
   */
  imagenes?: ImagenGenerada[];
  // verificacion (workflow propio: datar un video)
  verificacion?: ReporteVerificacion;
  // revision (workflow propio: revisar el copy ya escrito por el community)
  informe?: InformeRevision;
  // import-calendario (importación AGNÓSTICA por IA en el worker)
  creados?: number;
  omitidos?: { titulo: string; motivo: string }[];
  errores?: ErrorImportCalendario[];
}

/** Una imagen producida por el estudio de imagen, lista para previsualizar. */
export interface ImagenGenerada {
  /** Nombre del archivo en el almacén de media. */
  nombre: string;
  /** URL para servir la imagen (`/api/media/{nombre}`). */
  url: string;
}

/** Una señal (pista objetiva) del análisis de procedencia, clasificada por nivel. */
export interface SenalVerificacion {
  nivel: "alto" | "medio" | "bajo" | "info" | string;
  texto: string;
}

/** Una verificación previa relacionada (Google Fact Check API), si hubo key. */
export interface FactCheckResultado {
  afirmacion?: string | null;
  quien_lo_dijo?: string | null;
  verificador?: string | null;
  dictamen?: string | null;
  url?: string | null;
  fecha?: string | null;
}

/**
 * Reporte del motor de verificación de video (`analiza-video.py`). Junta EVIDENCIA
 * para datar un video (nuevo vs reciclado); NO es un dictamen automático.
 */
export interface ReporteVerificacion {
  entrada: string;
  tipo_entrada: "url" | "archivo" | string;
  contexto_afirmado?: string | null;
  metadatos: {
    disponible?: boolean;
    plataforma?: string | null;
    titulo?: string | null;
    autor?: string | null;
    url_pagina?: string | null;
    miniatura?: string | null;
    subido_iso?: string | null;
    anio_subida?: number | null;
    duracion_s?: number | null;
    vistas?: number | null;
    error?: string;
  };
  ocr: {
    frames_analizados?: number;
    anios?: number[];
    fechas?: string[];
    horas?: string[];
    error?: string;
  };
  busqueda_inversa: {
    base?: string;
    imagen_url?: string;
    enlaces?: Record<string, string>;
    fotogramas_guardados_en?: string | null;
  };
  fact_check: { consultado: boolean; motivo?: string; resultados?: FactCheckResultado[] };
  /** Indicios de copyright / derechos de agencia (Storyful, AP, Reuters…). */
  senales_copyright?: SenalesCopyright;
  /** Hipótesis de país de origen + fuentes de confirmación dirigidas. */
  pais_origen?: PaisOrigen;
  senales: SenalVerificacion[];
  avisos?: string[];
  carpeta_trabajo?: string;
}

/** Una agencia/derecho detectado en el video (por OCR, título o dominio). */
export interface AgenciaCopyright {
  agencia: string;
  /** "alto" | "medio" | "bajo" según la fuente de la señal. */
  nivel_confianza: string;
  /** Dónde se detectó: "ocr" | "titulo" | "descripcion" | "dominio". */
  fuente: string;
  /** Patrón/texto que disparó la detección. */
  patron_detectado: string;
}

/** Indicios de copyright/derechos: heurística local (no consulta APIs externas). */
export interface SenalesCopyright {
  agencias_detectadas: AgenciaCopyright[];
  /** Resumen legible (p. ej. "watermark de Storyful: verifica licencia"). */
  resumen: string;
  /** Atajo: ¿hay algún indicio que revisar antes de publicar? */
  tiene_indicios: boolean;
}

/** Una fuente de confirmación sugerida (búsqueda dirigida; el humano la juzga). */
export interface FuenteConfirmacionPais {
  descripcion: string;
  url: string;
  /** Tipo de fuente (p. ej. "busqueda_google_idioma_local", "busqueda_google_news"). */
  tipo: string;
}

/** Hipótesis del país donde ocurrió el hecho del video (heurística, honesta). */
export interface PaisOrigen {
  /** Nombre del país, o null si no hay señal suficiente. */
  pais_hipotesis: string | null;
  /** Código ISO 3166-1 alfa-2, o null. */
  codigo_iso: string | null;
  /** "alta" | "media" | "baja" | "insuficiente". */
  confianza: string;
  /** Señales que llevaron a la hipótesis (topónimos, idioma…). */
  senales_detectadas?: string[];
  /** ≥ 2 enlaces de búsqueda dirigida para confirmar (vacío si insuficiente). */
  fuentes_confirmacion: FuenteConfirmacionPais[];
  /** Nota/aclaración honesta sobre la inferencia. */
  nota?: string;
}

/** Cuerpo de POST /api/verificar: el enlace del video y, opcional, lo que se afirma. */
export interface CuerpoVerificar {
  enlace: string;
  contexto?: string;
}

// --- revisión editorial (revisar el copy YA escrito por el community, ficha F3 / #143) ---

/** Tipo de hallazgo del revisión editorial: qué dimensión se incumple. */
export type TipoHallazgoRevision = "ortografia" | "dato" | "legal" | "voz";

/** Gravedad de un hallazgo: `error` baja a 🔴; `aviso` baja (a lo sumo) a 🟡. */
export type GravedadHallazgoRevision = "error" | "aviso";

/**
 * Un hallazgo de la revisión editorial: SEÑALA un problema en el copy ajeno con su
 * tipo, gravedad, el fragmento donde está y una corrección SUGERIDA (que el equipo
 * acepta o ignora; nunca se aplica sola). Si `no_verificable`, es un dato que no se
 * pudo comprobar contra la fuente: no se afirma erróneo ni se inventa el correcto.
 */
export interface HallazgoRevision {
  tipo: TipoHallazgoRevision;
  gravedad: GravedadHallazgoRevision;
  fragmento: string;
  explicacion: string;
  sugerencia: string;
  no_verificable: boolean;
}

/**
 * Informe del revisión editorial sobre el copy del community manager. Abre con un dictamen
 * 🟢/🟡/🔴 (`verdicto`, igual codificación que el resto del producto) y lista los
 * hallazgos. NO reescribe el copy ni publica: es solo el informe.
 */
export interface InformeRevision {
  verdicto: Veredicto;
  resumen: string;
  hallazgos: HallazgoRevision[];
  /** El informe legible completo (Markdown), por si se quiere leer/copiar entero. */
  informe_texto: string;
}


/**
 * Un trabajo de IA en segundo plano. El POST que lo lanza responde de inmediato
 * con `estado="ejecutando"`; el frontend sondea `GET /api/generaciones/{id}` hasta
 * el estado terminal. `salida` es el texto del asistente EN VIVO (crece token a
 * token con streaming); `resultado` se rellena al completar.
 */
export interface Generacion {
  id: string;
  tipo: TipoGeneracion | string;
  marca: string;
  /** Etiqueta legible (p. ej. "Copy desde nota · UnoTV"). */
  etiqueta: string;
  estado: EstadoGeneracion | string;
  /**
   * Etapa de PROGRESO mientras corre (en qué etapa va): "razonando" → "generando" →
   * "completado". "" en registros legados o antes de arrancar.
   */
  fase: FaseGeneracion | string;
  /** Motivo terminal (p. ej. "timeout"); normalmente vacío. */
  motivo: string;
  /** Texto del asistente en vivo (vacío para imágenes; crece mientras corre). */
  salida: string;
  /** Mensaje de error legible (cuando `estado === "error"`). */
  error: string;
  /**
   * Prompt EXACTO enviado a `claude -p` (visibilidad/control). Solo lo devuelve el
   * detalle `GET /api/generaciones/{id}`, no el listado de Actividad. Ausente => sin dato.
   */
  prompt?: string;
  /**
   * Razonamiento (thinking) EN VIVO: cola acotada de los últimos tokens de pensamiento,
   * para feedback inmediato mientras el modelo aún no escribe la respuesta. Como el prompt,
   * solo en el detalle, no en el listado. Ausente => sin dato.
   */
  razonamiento?: string;
  /** Métricas (tokens/coste/turnos/duración); `null` mientras no hay. */
  metricas: MetricasRun | null;
  /** Payload al completar; `null` mientras corre o si falla. */
  resultado: ResultadoGeneracion | null;
  /** Atribución por usuario (#130 Fase 1): id estable de quien lanzó. "" si legado/anónimo. */
  autor_id: string;
  /** Nombre de quien lanzó (para mostrar). "" si legado/anónimo. */
  autor_nombre: string;
  fecha_inicio: string;
  fecha_fin: string;
}

export interface RespuestaGeneracion {
  generacion: Generacion;
}

export interface RespuestaGeneraciones {
  generaciones: Generacion[];
  /** Envelope de paginacion (#121); opcional para retrocompat. */
  paginacion?: Paginacion;
}
