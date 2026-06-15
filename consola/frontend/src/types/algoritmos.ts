import type { EnlaceRadar, EstadoTema, GeoRadar } from "./fuentes";

// ── Algoritmos: inteligencia de plataforma (cambios de algoritmo + tendencias) ──
// Tipos a mano (los handlers de `api/algoritmos.py` construyen dicts ad-hoc, no modelos),
// igual que el Radar. Texto orientado al usuario llega ya en español desde el backend.

/** Nivel de importancia heurístico de una noticia de algoritmo. */
export type NivelAlgoritmo = "alta" | "media" | "baja";

/** Una noticia de algoritmo ya ingerida y clasificada. */
export interface NoticiaAlgoritmo {
  id: string;
  fuente_id: string;
  fuente_nombre: string;
  /** Plataforma (id, p. ej. "instagram"); `general` si es multiplataforma. */
  plataforma: string;
  /** Etiqueta humana de la plataforma (p. ej. "Instagram"). */
  plataforma_nombre: string;
  /** Origen de la fuente: "oficial" (la plataforma) o "agregador" (industria). */
  tipo: string;
  titulo: string;
  resumen: string;
  enlace: string;
  /** Fecha tal cual la da el feed (puede venir vacía). */
  fecha: string;
  /** Score heurístico comparable (mayor = más importante). */
  importancia: number;
  nivel: NivelAlgoritmo;
  /** Palabras clave que dispararon el score (el "por qué" honesto). */
  senales: string[];
  /** `true` si parece un cambio de algoritmo confirmado (candidato a la ficha). */
  es_cambio: boolean;
  /** `true` si ya se propuso a la texto editorial. */
  aplicada: boolean;
  archivada: boolean;
}

/** Una fuente de inteligencia de plataforma (blog oficial o agregador). */
export interface FuenteAlgoritmo {
  id: string;
  nombre: string;
  url: string;
  plataforma: string;
  plataforma_nombre: string;
  tipo: string;
  tipo_nombre: string;
  activo: boolean;
  ultima_actualizacion: string;
  ultimo_error: string;
  ultimo_conteo: number;
}

/** Una plataforma SIN feed RSS oficial: el hueco se declara, no se inventa. */
export interface PendienteAlgoritmo {
  plataforma: string;
  nombre: string;
  motivo: string;
}

/** Un par {id, nombre} para los selectores de plataforma/tipo. */
export interface OpcionAlgoritmo {
  id: string;
  nombre: string;
}

/** Respuesta de GET /api/algoritmos. */
export interface RespuestaAlgoritmos {
  noticias: NoticiaAlgoritmo[];
  fuentes: FuenteAlgoritmo[];
  pendientes: PendienteAlgoritmo[];
  plataformas: OpcionAlgoritmo[];
  tipos: OpcionAlgoritmo[];
  niveles: NivelAlgoritmo[];
}

/** Error por fuente en una ingesta (degradación honesta). */
export interface ErrorFuenteAlgoritmo {
  fuente_id: string;
  fuente_nombre: string;
  error: string;
}

/** Resumen de una ingesta (POST /api/algoritmos/refrescar). */
export interface ResumenRefrescoAlgoritmos {
  fuentes: number;
  insertadas: number;
  actualizadas: number;
  errores: ErrorFuenteAlgoritmo[];
}

export interface RespuestaRefrescarAlgoritmos {
  resumen: ResumenRefrescoAlgoritmos;
}

export interface RespuestaInicializarAlgoritmos {
  creadas: FuenteAlgoritmo[];
  total: number;
}

export interface RespuestaFuenteAlgoritmo {
  fuente: FuenteAlgoritmo;
}

/** Respuesta de POST /api/algoritmos/{id}/texto: borrador para la ficha. */
export interface RespuestaATextoAlgoritmo {
  noticia: NoticiaAlgoritmo;
  /** Bloque markdown listo para pegar/confirmar en la Texto. */
  propuesta: string;
  plataforma: string;
}

export interface RespuestaArchivarAlgoritmo {
  noticia: NoticiaAlgoritmo | null;
}

/** Filtros del listado de noticias de algoritmo. */
export interface FiltrosAlgoritmos {
  plataforma?: string;
  nivel?: NivelAlgoritmo;
  solo_cambios?: boolean;
  incluir_archivadas?: boolean;
  limite?: number;
}

/** Cuerpo de alta/edición de una fuente de algoritmo. */
export interface CuerpoFuenteAlgoritmo {
  nombre?: string;
  url?: string;
  plataforma?: string;
  tipo?: string;
  activo?: boolean;
}

/** Subtipo de un posteo de la parrilla (vacío para los video-editoriales). */
export type SubtipoParrilla = "clip" | "galeria" | "infografia" | "normal" | "";

/** Un tema clasificado y jerarquizado para la parrilla del día. */
export interface ItemParrilla {
  titulo: string;
  /**
   * Estado de gestión del ítem (Investigador F2b). Opcional/retrocompat: si falta se
   * trata como "nuevo" (sin badge). Lo provee el backend.
   */
  estado?: EstadoTema;
  /** `true` si el ítem es prioritario (algo fuerte que debe salir rápido). Opcional. */
  prioritario?: boolean;
  /** `true` si la señal del ítem está acelerando ("En aumento"/breaking). Opcional. */
  breaking?: boolean;
  /** "posteo" (clip/galería/infografía/normal) o "editorial" (video con carnita). */
  tipo: "posteo" | "editorial";
  subtipo: SubtipoParrilla;
  /** Puntuación de jerarquía (mayor = más importante). */
  score: number;
  /** Posición 1-based en la parrilla del día (1 = se publica primero). */
  orden: number;
  /** Texto en español explicando el porqué del orden. */
  razon: string;
  senal: number;
  senal_texto: string;
  por_que: string;
  redes: string[];
  fuentes: string[];
  enlaces: EnlaceRadar[];
  /** Código de idioma del ítem (p. ej. "en"). Opcional; ausente si es ES o no se detectó. */
  idioma?: string;
  /** `true` si el título/por_qué ya fueron traducidos al español por el backend. */
  traducido?: boolean;
  /** Título en el idioma original, antes de la traducción (solo si `traducido` es true). */
  titulo_original?: string;
}

/** Respuesta de GET/POST /api/parrilla-dia: la parrilla editorial del día. */
export interface RespuestaParrilla {
  /** Geo activo (id ISO, p. ej. "MX"). */
  geo: string;
  geos_disponibles: GeoRadar[];
  /** Hasta `cuota_posteos` posteos, jerarquizados (1 = primero). */
  posteos: ItemParrilla[];
  /** Hasta `cuota_editorial` video-editoriales, jerarquizados. */
  editorial: ItemParrilla[];
  /** Temas que superan las cuotas (igualmente jerarquizados). */
  sobrantes: ItemParrilla[];
  total_entrada: number;
  total_posteos: number;
  total_editorial: number;
  total_sobrantes: number;
  /** Temas descartados por NO ser de la marca activa (0 sin marca). */
  total_fuera_foco?: number;
  cuota_posteos: number;
  cuota_editorial: number;
  /** Geo/contexto usado en el scoring. */
  contexto: string;
  /** Marca con la que se armó el plan (id canónico), o `null`/ausente si general. */
  marca?: string | null;
}
