import type { PrioridadEvento } from "./rota";
import type { TemaRadar } from "./fuentes";

// --- Tablero de CONTENIDO unificado (herramienta de community manager) ---

/** Usuario asignable como responsable (#145 F5): solo id + nombre. */
export interface UsuarioTarea {
  id: string;
  usuario: string;
}

/** Flujo editorial del tablero: lo importante del día, evergreen o cobertura de evento. */
export type FlujoContenido = "importante" | "evergreen" | "evento" | "";
/** Una fila por red lleva su propio estado en este ciclo unificado. */
export type EstadoContenidoPlataforma =
  | "pendiente"
  | "en_curso"
  | "en_revision"
  | "aprobado"
  | "programado"
  | "publicado";

/** Una fila por plataforma (red) de un contenido: estado propio + checklist "falta X". */
export interface ContenidoPlataforma {
  id: string;
  contenido_id: string;
  red: string;
  red_nombre: string;
  estado: EstadoContenidoPlataforma;
  falta_copy: boolean;
  falta_imagen: boolean;
  falta_revision: boolean;
  falta_publicar: boolean;
  /** Ola F: falta el asset de video (solo relevante cuando la pieza es formato='video'). */
  falta_video: boolean;
  copy: string;
  /** Nombre de archivo de la imagen en el dir de media ("" si no hay). NO es navegable. */
  imagen: string;
  /** URL de la imagen de la FUENTE original (cuando tipo_contenido='fuente'). "" si no. */
  imagen_fuente: string;
  /**
   * Ruta servible de la imagen, lista para un <img>. Es `/api/media/{imagen}` si hay media
   * adjunta; si no, cae a `imagen_fuente` (URL externa ya navegable). "" si no hay ninguna.
   */
  imagen_url: string;
  /** Clave del asset de video en el almacén ("" si no hay). Ola F. */
  video: string;
  /** URL servible del video (análogo a imagen_url). "" si no hay. Ola F. */
  video_url: string;
  veredicto: string;
  fecha_programada: string;
  hora_post: string;
  enlace: string;
  evergreen: boolean;
  /** Id del post en Metricool (lo estampa el programador al publicar). "" si aún no se publicó. */
  id_post_metricool: string;
  /** `true` si esta fila es una PUBLICACIÓN (es_publicacion=1): nació en el flujo de publicación. */
  es_publicacion: boolean;
}

/** Rendimiento REAL de una pieza ya publicada, leído de Metricool por su `id_post_metricool`. */
export interface MetricaPieza {
  id_post: string;
  plataforma: string;
  /** `false` si Metricool aún no tiene datos del post (la UI muestra "sin datos todavía"). */
  encontrado: boolean;
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
  url: string | null;
  publicado: string | null;
  /** "muestra" (demo) o "metricool" (datos reales). */
  fuente: string;
  /** Cuándo se leyó de Metricool (ISO); "" si no encontrado. */
  generado_en: string;
}

/** Respuesta de `GET /api/contenido/metricas`: rendimiento por `contenido_plataforma.id`. */
export interface RespuestaMetricasContenido {
  /** Mapa id de fila por plataforma → su rendimiento (solo las que tienen id_post_metricool). */
  metricas: Record<string, MetricaPieza>;
}

/**
 * Eje (clase) de una etiqueta editorial: campaña, vertical (= LÍNEA de contenido),
 * tipo de formato, u origen (interno / petición externa). `string` deja pasar ejes
 * nuevos del backend sin romper el tipado.
 */
export type ClaseEtiqueta = "campania" | "vertical" | "tipo" | "origen" | string;

/** Una etiqueta editorial del catálogo (clasifica transversalmente las piezas del tablero).
 *
 * `marca = ""` = etiqueta GLOBAL (visible en todas las marcas/workspaces); cualquier otro
 * valor la acota a esa marca. `color` es un token hex opcional para el chip ("" = sin color).
 */
export interface Etiqueta {
  id: string;
  nombre: string;
  clase: ClaseEtiqueta;
  marca: string;
  marca_nombre: string;
  color: string;
  /** CSV de palabras clave para auto-clasificar piezas en esta etiqueta. */
  keywords: string;
  activo: boolean;
  /** Días que un ítem de esta línea se considera fresco. 0 = sin caducidad / evergreen. */
  ttl_dias: number;
  /** True = línea evergreen reutilizable en fines de semana; nunca caduca. */
  es_evergreen: boolean;
}

/** Forma reducida de una etiqueta en los catálogos del tablero (chips/selector). */
export interface EtiquetaCatalogo {
  id: string;
  nombre: string;
  clase: ClaseEtiqueta;
  marca: string;
  color: string;
}

export interface RespuestaEtiquetas {
  etiquetas: Etiqueta[];
  clases: ClaseEtiqueta[];
  marcas: { id: string; nombre: string }[];
}

export interface CuerpoCrearEtiqueta {
  nombre: string;
  clase?: ClaseEtiqueta;
  marca?: string;
  color?: string;
  /** CSV de palabras clave para auto-clasificar. */
  keywords?: string;
  /** Días de vida del ítem (0 = sin caducidad / evergreen). */
  ttl_dias?: number;
  /** True = línea evergreen, nunca caduca. */
  es_evergreen?: boolean;
}

export interface CuerpoActualizarEtiqueta {
  nombre?: string;
  clase?: ClaseEtiqueta;
  marca?: string;
  color?: string;
  keywords?: string;
  activo?: boolean;
  /** Días de vida del ítem (0 = sin caducidad / evergreen). */
  ttl_dias?: number;
  /** True = línea evergreen, nunca caduca. */
  es_evergreen?: boolean;
}

export interface RespuestaEtiqueta {
  etiqueta: Etiqueta;
}

// --- Evergreen: ideas de contenido evergreen (evergreen) ---------------------------

/** Estado de una idea Evergreen: propuesta → aprobada / descartada. */
export type EstadoIdeaEvergreen = "propuesta" | "aprobada" | "descartada" | string;

/** Una idea de contenido evergreen (banco de ideas evergreens por marca). */
export interface IdeaEvergreen {
  id: string;
  marca: string;
  titulo: string;
  descripcion: string;
  estado: EstadoIdeaEvergreen;
  /** De dónde salió la idea (p. ej. "ia" cuando la propuso el asistente, "manual"). */
  origen: string;
  /** Id del contenido generado a partir de la idea (vacío si aún no se generó). */
  contenido_id: string;
  creado: string;
}

export interface RespuestaIdeasEvergreen {
  ideas: IdeaEvergreen[];
  estados: EstadoIdeaEvergreen[];
  marcas: { id: string; nombre: string }[];
}

export interface CuerpoCrearIdeaEvergreen {
  marca: string;
  titulo: string;
  descripcion?: string;
  /**
   * Origen de la aportación dentro del banco único: `manual` (alta rápida), `idea` ("Idea del
   * equipo") o `interna` ("Interno AMX"). Por defecto el backend asume `manual`.
   */
  origen?: "manual" | "idea" | "interna";
}

export interface CuerpoActualizarIdeaEvergreen {
  estado?: EstadoIdeaEvergreen;
  titulo?: string;
  descripcion?: string;
}

export interface CuerpoProponerEvergreen {
  marca: string;
  contexto?: string;
}

export interface CuerpoGenerarIdeaEvergreen {
  redes?: string[];
}

export interface RespuestaIdeaEvergreen {
  idea: IdeaEvergreen;
}

// --- Métrica por línea (vertical) y por origen -------------------------------

/** Rendimiento agregado de una LÍNEA (o un ORIGEN) en el periodo. */
export interface FilaMetricaLinea {
  id: string;
  nombre: string;
  piezas: number;
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
}

export interface MetricasLineas {
  marca: string;
  rango: string;
  etiqueta_rango: string;
  lineas: FilaMetricaLinea[];
  origenes: FilaMetricaLinea[];
  total: FilaMetricaLinea;
  fuente: string;
}

/** Un item del tablero: contenido publicable (con plataformas) o tarea libre del equipo. */
/**
 * Tipo de contenido: de DÓNDE sale la imagen de la pieza.
 *   - `ia`:      se genera con IA (texto → imagen).
 *   - `galeria`: se sube/elige de la galería de medios.
 *   - `fuente`:  se usa la imagen de la FUENTE original (nota/clip), vía su URL.
 */
export type TipoContenido = "ia" | "galeria" | "fuente";

export interface Contenido {
  id: string;
  clase: "contenido" | "tarea";
  flujo: FlujoContenido;
  titulo: string;
  descripcion: string;
  marca: string;
  marca_nombre: string;
  evento_id: string;
  programa: string;
  prioridad: PrioridadEvento;
  estado: string;
  fecha_objetivo: string;
  hora_objetivo: string;
  fecha_entrega: string;
  responsable_id: string;
  responsable_nombre: string;
  autor_nombre: string;
  origen: string;
  notas: string;
  /** De dónde sale la imagen (IA / galería / fuente original). */
  tipo_contenido: TipoContenido;
  /** Formato de la pieza — "foto" (3 redes), "video" (5) o "carrusel" (2: IG/FB). */
  formato: string;
  /** Derivado: deadline pasado y aún sin cerrar. */
  vencido: boolean;
  plataformas: ContenidoPlataforma[];
  /** Ids de las etiquetas asignadas (resolver contra `catalogos.etiquetas`). */
  etiquetas: string[];
}

/** Catálogos para los selects del tablero. */
export interface CatalogosContenido {
  usuarios: UsuarioTarea[];
  marcas: { id: string; nombre: string }[];
  redes: { id: string; nombre: string; limite: number | null }[];
  flujos: string[];
  prioridades: string[];
  estados_contenido: string[];
  estados_plataforma: string[];
  eventos: { id: string; titulo: string; fecha: string; hora: string }[];
  etiquetas: EtiquetaCatalogo[];
  /** Variables `{...}` que el copy puede llevar y se autocompletan en la previa. */
  variables: VariableCopy[];
}

/** Una variable de copy (`{marca}`, `{fecha}`, ...) para insertar y autocompletar. */
export interface VariableCopy {
  /** Nombre de la variable (sin llaves), p.ej. "marca". */
  clave: string;
  /** Sintaxis lista para insertar, p.ej. "{marca}". */
  ejemplo: string;
  /** Explicación humana de qué inserta. */
  etiqueta: string;
}

export interface RespuestaContenido {
  contenidos: Contenido[];
  catalogos: CatalogosContenido;
}

export interface CuerpoCrearContenido {
  titulo: string;
  clase?: "contenido" | "tarea";
  flujo?: FlujoContenido;
  marca?: string;
  evento_id?: string;
  programa?: string;
  prioridad?: PrioridadEvento;
  descripcion?: string;
  fecha_objetivo?: string;
  hora_objetivo?: string;
  fecha_entrega?: string;
  responsable_id?: string;
  notas?: string;
  /** De dónde sale la imagen (IA / galería / fuente original). Def 'ia'. */
  tipo_contenido?: TipoContenido;
  /** Redes para crear una fila por plataforma por cada una. */
  redes?: string[];
  /** Ids de etiquetas a asignar al crear. */
  etiquetas?: string[];
}

/** Respuesta de asignar/quitar una etiqueta a un contenido: el set actualizado de ids. */
export interface RespuestaEtiquetasContenido {
  etiquetas: string[];
}

/** Cambios parciales sobre el padre; cada campo es opcional. */
export interface CuerpoActualizarContenido {
  titulo?: string;
  flujo?: FlujoContenido;
  marca?: string;
  evento_id?: string;
  programa?: string;
  prioridad?: PrioridadEvento;
  estado?: string;
  descripcion?: string;
  fecha_objetivo?: string;
  hora_objetivo?: string;
  fecha_entrega?: string;
  responsable_id?: string;
  notas?: string;
  /** Ola F: flip de formato (foto↔video). El backend ajusta las redes (3↔5) y devuelve `aviso`. */
  formato?: string;
}

/** Cambios parciales sobre una fila por plataforma; cada campo es opcional. */
export interface CuerpoActualizarPlataforma {
  estado?: EstadoContenidoPlataforma;
  falta_copy?: boolean;
  falta_imagen?: boolean;
  falta_revision?: boolean;
  falta_publicar?: boolean;
  copy?: string;
  imagen?: string;
  imagen_fuente?: string;
  enlace?: string;
  fecha_programada?: string;
  hora_post?: string;
  veredicto?: string;
  evergreen?: boolean;
  copy_in_exento?: boolean;
  /** Ola F: clave del asset de video; al enviarlo el backend limpia falta_video. */
  video?: string;
}

export interface RespuestaContenidoItem {
  contenido: Contenido;
  /** Ola F: presente cuando el flip foto↔video conservó redes con contenido (aviso al usuario). */
  aviso?: string;
}

export interface RespuestaPlataforma {
  plataforma: ContenidoPlataforma;
}

/** `POST /api/contenido/{id}/preview`: copy con sus variables `{...}` ya sustituidas. */
export interface RespuestaPreviewContenido {
  preview: string;
}

/** Modo del asistente IA del tablero. */
export type ModoAsistenteContenido = "generar" | "variantes" | "resumir";

/** `POST /api/contenido/{id}/asistente`: lanza el asistente IA sobre un contenido. */
export interface CuerpoAsistenteContenido {
  modo: ModoAsistenteContenido;
  /** Redes a generar; por defecto, las redes sociales del propio contenido. */
  redes?: string[];
}

export interface CuerpoDesdeRadar {
  titulo: string;
  marca?: string;
  redes?: string[];
  prioridad?: PrioridadEvento;
  descripcion?: string;
}

/** Intención editorial opcional al aportar material (mapea el flujo del tablero). */
export type IntencionMaterial = "breaking" | "evergreen" | "hilo";

/** `POST /api/contenido/aportar` (multipart): la PUERTA CREATIVA del equipo (Fase 1).
 *  El equipo sube material ORIGINAL con marca y eso enciende la auto-generación de copy
 *  (origen='equipo'). La marca es OBLIGATORIA (sin voz no hay generación). */
export interface CuerpoAportarMaterial {
  /** De qué va la pieza (la auto-generación lo usa como nota base). */
  titulo: string;
  /** Marca obligatoria (id canónico). */
  marca: string;
  /** Nota / idea / texto crudo -> descripción del tema. */
  material?: string;
  /** Enlace de la fuente del material -> `imagen_fuente` de cada red. */
  url?: string;
  /** Intención editorial; mapea el flujo (breaking/hilo -> importante; evergreen). */
  intencion?: IntencionMaterial;
  /** Redes objetivo; por defecto, las canónicas. */
  redes?: string[];
  /** La FOTO que el equipo trae de fuera (la IA no la genera). */
  imagen?: File;
  /** Un VÍDEO/AUDIO que el equipo graba; se transcribe EN LOCAL y el texto entra como
   *  material base del auto-copy (nota NO verificada). El clip no se guarda. */
  clip?: File;
}

// --- Fase3 auto-planificación: sugerencia de hora + auto-promoción del Radar ---

/** `POST /api/planificacion/sugerir-hora`: pide la mejor fecha-hora para una marca/red. */
export interface CuerpoSugerirHora {
  /** Id canónico de la marca (slug-guion, como en el tablero). */
  marca: string;
  /** Red canónica (p. ej. "x", "instagram"). */
  red: string;
  /** Periodo del histórico a considerar (def "mes"). */
  rango?: string;
}

/** Una sugerencia de fecha-hora óptima de publicación (`dominio.planificacion.Sugerencia`). */
export interface SugerenciaHora {
  /** Fecha-hora propuesta, ISO 'YYYY-MM-DDTHH:MM' (lo que entiende el programador). */
  fecha: string;
  /** Peso histórico del día de la semana de esa fecha (0 si no hay histórico). */
  score: number;
  /** Por qué se eligió, en español (día que más rinde / próximo hueco libre). */
  motivo: string;
  /** `true` si está respaldada por el histórico; `false` si es mero "próximo hueco". */
  con_historico: boolean;
}

/** Respuesta de `POST /api/planificacion/sugerir-hora`. */
export interface RespuestaSugerirHora {
  /** La sugerencia, o `null` si no hay franjas/huecos (entonces `motivo` lo explica). */
  sugerencia: SugerenciaHora | null;
  /** Motivo cuando no hay sugerencia ("" si sí la hay). */
  motivo: string;
}

/** Config viva de la auto-promoción del Radar (espejo de `radar_auto`/`config`). */
export interface ConfigRadarAuto {
  /** `true` si el daemon está activo (`KENI_RADAR_AUTO`). */
  activo: boolean;
  /** Umbral mínimo de señal para auto-promover. */
  umbral: number;
  /** Geo del Radar (id ISO, p. ej. "MX"). */
  geo: string;
  /** Máximo de temas a promover por barrido. */
  max_por_barrido: number;
  /** Cada cuántas horas barre el daemon. */
  intervalo_horas: number;
  /** Marca (id canónico) asignada a las piezas auto-promovidas ("" = sin marca). */
  marca: string;
}

/** Respuesta de `GET /api/radar/auto/bandeja`: temas que se promoverían ahora. */
export interface RespuestaBandejaRadarAuto {
  config: ConfigRadarAuto;
  /** Temas que superarían el umbral y entrarían (sin escribir nada). */
  temas: TemaRadar[];
  total: number;
}

/** Respuesta de `POST /api/radar/auto/ejecutar`: piezas promovidas a "importante". */
export interface RespuestaEjecutarRadarAuto {
  promovidos: Contenido[];
  total: number;
}
