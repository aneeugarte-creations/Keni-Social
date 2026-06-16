import type { Pieza } from "../types.gen";
import type { Veredicto, PiezaGenerada } from "./comun";
import type { Generacion } from "./generaciones";

// --- Carril Rápido de Breaking (Claro Sports) ---

/**
 * Un tema breaking del Radar de Claro Sports.
 * `estado_borrador`: "ninguno" | "generando" | "listo"
 */
export interface BreakingItem {
  titulo: string;
  marca: string;
  marca_nombre: string;
  senal: number;
  senal_texto: string;
  breaking: true;
  idioma: string;
  fuentes: string[];
  enlaces: { titulo: string; url: string; fuente: string }[];
  fecha: string;
  estado_borrador: "ninguno" | "generando" | "listo";
  publicacion_id: string;
  generacion_id: string;
}

/** Respuesta de GET /api/breaking. */
export interface RespuestaBreaking {
  items: BreakingItem[];
}

/** Cuerpo de POST /api/breaking/preparar. */
export interface CuerpoPreparar {
  titulo: string;
  marca: string;
  redes?: string[];
}

/** Respuesta de POST /api/breaking/preparar. */
export interface RespuestaPreparar {
  publicacion_id: string;
  generacion_id: string;
}

// --- Hub genérico de fuentes (item G): RSS + API + galerías + ideas + internas ---

/** Una fuente del hub genérico (cualquier tipo), con su config JSON y prioridad. */
export interface FuenteHub {
  id: string;
  /** Tipo de fuente: rss / api / galeria / idea / interna. */
  tipo: string;
  nombre: string;
  /** Config específica del tipo (p. ej. {url, incluir, excluir} para rss). */
  config: Record<string, unknown>;
  marca: string;
  marca_nombre: string;
  /** Prioridad entera (mayor = pesa más al priorizar). */
  prioridad: number;
  etiquetas: string[];
  activo: boolean;
  ultima_actualizacion: string;
  ultimo_error: string;
  ultimo_conteo: number;
  /** Id de la `fuentes_rss` de la que se inicializó (vacío si nació en el hub). */
  origen_rss_id: string;
}

/** Estado HONESTO de una agencia de noticias (Reuters/AFP), gateada por credencial. */
export interface AgenciaFuente {
  red: string;
  nombre: string;
  disponible: boolean;
  motivo: string;
}

/** Respuesta de GET /api/fuentes (hub genérico + estado de agencias). */
export interface RespuestaFuentesHub {
  fuentes: FuenteHub[];
  tipos: string[];
  agencias: AgenciaFuente[];
  pendientes: AgenciaFuente[];
}

// --- Radar de tendencias (lo más viral del momento, multi-red · F7/#147) ---

/** Una nota/enlace que explica por qué sube un tema (título + URL + medio). */
export interface EnlaceRadar {
  titulo: string;
  url: string;
  /** Medio/fuente de la nota (p. ej. "ESPN Deportes"). */
  fuente: string;
}

/**
 * Estado de gestión de un tema/ítem del Investigador (Fase 2b): refleja si el tema
 * sigue sin tocar, ya está en la parrilla del CM, o ya se publicó. La UI pinta un
 * badge solo para `en_parrilla`/`publicado` (lo `nuevo` es lo normal, no se ensucia).
 */
export type EstadoTema = "nuevo" | "en_parrilla" | "publicado";

/** Un tema en tendencia, consolidado de una o varias fuentes y deduplicado. */
export interface TemaRadar {
  titulo: string;
  /**
   * Estado de gestión del tema (Investigador F2b). Opcional/retrocompat: si falta se
   * trata como "nuevo" (sin badge). Lo provee el backend.
   */
  estado?: EstadoTema;
  /** `true` si el tema es prioritario (algo fuerte que debe salir rápido). Opcional. */
  prioritario?: boolean;
  /** `true` si la señal del tema está acelerando ("En aumento"/breaking). Opcional. */
  breaking?: boolean;
  /** Redes/superficies donde aparece (p. ej. "busquedas-mx", "rss"). */
  redes: string[];
  /** Fuentes que lo reportan (p. ej. "Google Trends", el nombre del feed). */
  fuentes: string[];
  /** Por qué sube: señal real + la nota más relevante (sin inventar la causa). */
  por_que: string;
  /** Señal numérica comparable para priorizar (mayor = más viral). */
  senal: number;
  /** Señal tal cual la da la fuente, para mostrarla sin reinterpretar ("50 mil+"). */
  senal_texto: string;
  /** `true` si viene de una fuente propia de la marca activa (curado: en su foco siempre). */
  curado?: boolean;
  enlaces: EnlaceRadar[];
  /** Código de idioma del tema (p. ej. "en", "fr"). Opcional; ausente si es ES o no se detectó. */
  idioma?: string;
  /** `true` si el título/por_qué ya fueron traducidos al español por el backend. */
  traducido?: boolean;
  /** Título en el idioma original, antes de la traducción (solo si `traducido` es true). */
  titulo_original?: string;
}

/** Estado HONESTO de una fuente del radar (disponible o no, con su motivo). */
export interface FuenteRadar {
  id: string;
  nombre: string;
  /** Red/superficie de la fuente. */
  red: string;
  /** `true` si la fuente respondió; `false` si falló o no está disponible. */
  disponible: boolean;
  /** Motivo legible cuando no está disponible; "" si todo bien. */
  motivo: string;
  /** Nº de temas que aportó esta fuente. */
  conteo: number;
}

/** Una red que el radar AÚN no cubre, con el motivo (degradación honesta). */
export interface FuentePendienteRadar {
  red: string;
  nombre: string;
  motivo: string;
}

/** Un país (geo) disponible para el feed de Google Trends. */
export interface GeoRadar {
  id: string;
  nombre: string;
}

/** Respuesta de GET /api/radar. */
export interface RespuestaRadar {
  /** Geo activo del feed de tendencias (id ISO, p. ej. "MX"). */
  geo: string;
  geos_disponibles: GeoRadar[];
  /** Temas consolidados, deduplicados y ordenados por señal desc. */
  temas: TemaRadar[];
  /** Estado por fuente consultada (con su motivo si no está disponible). */
  fuentes: FuenteRadar[];
  /** Redes aún no cubiertas, con el motivo (no se inventan datos). */
  fuentes_pendientes: FuentePendienteRadar[];
  /** Nº total de temas (ya filtrados por marca si la hay). */
  total: number;
  /** Marca con la que se filtró (id canónico), o `null`/ausente si sin marca. */
  marca?: string | null;
  /** Temas descartados por NO ser de la marca activa (0 sin marca). */
  total_fuera_foco?: number;
}

// --- Presets del catálogo de fuentes (Ola 4: Fuentes externas + idiomas) ---

/**
 * Un preset del catálogo curado de fuentes: RSS listo para activar con un clic.
 * Corresponde al dict que devuelve `GET /api/fuentes/presets`.
 */
export interface Preset {
  id: string;
  nombre: string;
  url: string;
  /** Categoría del preset: "mx", "internacional", "deportes", "ciencia-tech", "gaming", "tendencias". */
  categoria: string;
  /** Marca sugerida para asignar el feed al activarlo (id canónico). */
  marca_sugerida: string;
  /** Línea editorial sugerida al activar. */
  linea_sugerida: string;
  /** Código de idioma del feed (p. ej. "en", "es", "fr"). */
  idioma: string;
  /** Región geográfica del feed (p. ej. "MX", "GLOBAL"). */
  region: string;
  descripcion: string;
  /** `true` si ya hay una `fuentes_rss` activa con esta URL. */
  activa: boolean;
}

/** Respuesta de GET /api/fuentes/presets. */
export interface RespuestaPresets {
  presets: Preset[];
  categorias: string[];
}

/** Respuesta de POST /api/fuentes/presets/activar. */
export interface RespuestaActivarPresets {
  creadas: number;
  fuentes: FuenteRss[];
}

// --- RSS (fuentes y elementos para Generar copy) ---

/** Una fuente RSS dada de alta. */
export interface FuenteRss {
  id: string;
  nombre: string;
  url: string;
  /** Marca asociada (`""` si es general). */
  marca: string;
  marca_nombre: string;
  /** `true` si el feed está activo (se incluye al refrescar items). */
  activo: boolean;
  /** Palabra(s) clave que deben aparecer para incluir un item (`""` = todos). */
  incluir: string;
  /** Palabra(s) clave que excluyen un item si aparecen (`""` = ninguno). */
  excluir: string;
  /** Redes por defecto al generar copy desde un item de este feed. */
  redes_def: string[];
  /** ISO de la última vez que se refrescó el feed; `""`/`null` si nunca. */
  ultima_actualizacion: string | null;
  /** Mensaje del último error al refrescar; `""`/`null` si todo fue bien. */
  ultimo_error: string | null;
  /** Nº de items obtenidos en el último refresco. */
  ultimo_conteo: number;
  /** `true` si es un sitio de MARCA PROPIA: su imagen original es reutilizable, así que las
   *  piezas generadas desde sus items nacen con la imagen del artículo (`tipo_contenido='fuente'`). */
  propia: boolean;
  /** Categoría del feed (mx | regional | internacional | deportes | ciencia-tech | gaming |
   *  negocios | tendencias | breaking | ""): manda la CADENCIA de sondeo del motor. */
  categoria: string;
  /** Peso editorial de la fuente: pondera la corroboración del ranking (potente 2.0 /
   *  normal 1.0 / baja 0.5). */
  peso: number;
  /** Tier legible del peso. */
  tier: "potente" | "normal" | "baja" | string;
}

export interface RespuestaFuentesRss {
  fuentes: FuenteRss[];
}

export interface RespuestaFuenteRss {
  fuente: FuenteRss;
}

/** Cuerpo para dar de alta una fuente RSS. */
export interface CuerpoCrearFuenteRss {
  nombre: string;
  url: string;
  /** Marca asociada (opcional). */
  marca?: string;
  /** Palabra(s) clave de inclusión (opcional). */
  incluir?: string;
  /** Palabra(s) clave de exclusión (opcional). */
  excluir?: string;
  /** Redes por defecto (opcional). */
  redes_def?: string[];
  /** `true` si es un sitio de marca propia (su imagen original es reutilizable). */
  propia?: boolean;
  /** Categoría del feed (opcional): manda la cadencia de sondeo del motor. */
  categoria?: string;
  /** Peso editorial (opcional; sin él, el back usa el seed por host). */
  peso?: number;
}

/** Cuerpo parcial para actualizar una fuente RSS. */
export interface CuerpoActualizarFuenteRss {
  nombre?: string;
  url?: string;
  marca?: string;
  activo?: boolean;
  incluir?: string;
  excluir?: string;
  redes_def?: string[];
  propia?: boolean;
  categoria?: string;
  peso?: number;
}

/** Un elemento (item) de un feed RSS. */
export interface ItemRss {
  titulo: string;
  resumen: string;
  enlace: string;
  fecha: string;
  fuente_id: string;
  fuente_nombre: string;
  /** Clave estable del item dentro de su feed (para marcar usado/dedup). */
  clave: string;
  /** URL de la imagen del artículo (media:content/thumbnail/enclosure); `""` si no la trae. */
  imagen: string;
  /** `true` si el item ya se marcó como usado. */
  usado: boolean;
}

/** Error de un feed concreto al refrescar la lista de items. */
export interface ErrorFuenteRss {
  fuente_id: string;
  fuente_nombre: string;
  /** Mensaje legible en español, sin tracebacks crudos. */
  error: string;
}

export interface RespuestaItemsRss {
  items: ItemRss[];
  /** Errores por feed al refrescar (uno por feed que falló). */
  errores: ErrorFuenteRss[];
}

/** Cuerpo para marcar un item como usado / no usado. */
export interface CuerpoMarcarItemUsado {
  fuente_id: string;
  clave: string;
  /** `true` (por defecto) marca usado; `false` lo desmarca. */
  usado?: boolean;
}

/** Cuerpo para generar copy directamente desde un item de feed. */
export interface CuerpoGenerarDesdeItem {
  titulo: string;
  resumen?: string;
  enlace?: string;
  marca: string;
  redes: string[];
  fuente_id?: string;
  clave?: string;
  /** URL de la imagen del artículo; solo se reutiliza si la fuente es de marca propia (gate
   *  server-side). La pieza nace con esa imagen original (`tipo_contenido='fuente'`). */
  imagen?: string;
}

/**
 * Respuesta de generar copy desde un item (auto-guarda como Piezas).
 * Misma forma que ejecutar un prompt.
 */
export interface RespuestaGenerarDesdeItem {
  resultado: string;
  historial_id: string;
  verdicto: Veredicto;
  piezas: PiezaGenerada[];
  /** Items de tablero creados desde las piezas generadas (no leído hoy por el SPA). */
  piezas_creadas?: Pieza[];
}

// --- Cajón PRESIDENCIA (Fuentes → Internas): nota de WhatsApp -> pieza carrusel ---

/** Un elemento de media de la nota (ya subido a /api/media): imagen o video, en orden. */
export interface MediaNotaPresidencia {
  tipo: "imagen" | "video";
  objeto: string;
}

/** Una nota volcada al cajón (el tema `origen='presidencia'`) + estado de su pieza. */
export interface NotaPresidencia {
  id: string;
  titulo: string;
  texto: string;
  marca: string;
  marca_nombre: string;
  autor_nombre: string;
  creado: string;
  /** 'generando' (copy en curso) | 'lista' (con copy en el feed) | 'sin_pieza'. */
  estado_pieza: "generando" | "lista" | "sin_pieza";
}

/** Cuerpo de `POST /api/presidencia/notas`. */
export interface CuerpoCrearNotaPresidencia {
  marca: string;
  texto: string;
  titulo?: string;
  media: MediaNotaPresidencia[];
}

/** Respuesta de `GET /api/presidencia/notas`. */
export interface RespuestaNotasPresidencia {
  notas: NotaPresidencia[];
  marcas: { id: string; nombre: string }[];
}

/** Respuesta de `POST /api/presidencia/notas`. */
export interface RespuestaCrearNotaPresidencia {
  nota: NotaPresidencia;
  publicacion_id: string;
  generacion: Generacion;
}

// --- Cajón CLIPS (Fuentes → Internas, Claro Sports): vídeo/foto -> pieza automática ---

/** Un clip volcado al cajón (el tema `origen='clips'`) + el formato y estado de su pieza. */
export interface Clip {
  id: string;
  titulo: string;
  texto: string;
  marca: string;
  marca_nombre: string;
  /** 'video' (un clip de vídeo) | 'carrusel' (fotos). */
  formato: string;
  autor_nombre: string;
  creado: string;
  /** 'generando' (copy en curso) | 'lista' (con copy en el feed) | 'sin_pieza'. */
  estado_pieza: "generando" | "lista" | "sin_pieza";
}

/** Cuerpo de `POST /api/clips`. El media reutiliza la forma de Presidencia (imagen/video). */
export interface CuerpoCrearClip {
  marca: string;
  texto: string;
  titulo?: string;
  media: MediaNotaPresidencia[];
}

/** Respuesta de `GET /api/clips`. */
export interface RespuestaClips {
  clips: Clip[];
  marcas: { id: string; nombre: string }[];
}

/** Respuesta de `POST /api/clips`. */
export interface RespuestaCrearClip {
  clip: Clip;
  publicacion_id: string;
  generacion: Generacion;
}
