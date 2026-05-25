/**
 * Contrato tipado de la API de la Consola Keni (`/api/*`).
 *
 * Estos tipos reflejan exactamente las respuestas y cuerpos documentados en el
 * contrato del backend. El frontend se construye contra estos tipos; la
 * integracion runtime contra el backend real se valida al combinar ramas.
 *
 * Todo el texto orientado al usuario (nombres, detalles, mensajes) llega ya en
 * espanol desde el backend.
 */

// --- Estado (autodiagnostico del sistema) ---

export type NivelEstado = "ok" | "aviso" | "error";

export interface ResultadoEstado {
  estado: NivelEstado;
  nombre: string;
  detalle: string;
  icono: string;
}

export interface RespuestaEstado {
  resultados: ResultadoEstado[];
  resumen: string;
  siguiente_paso: string;
}

// --- Configuracion ---

export interface MarcaDisponible {
  id: string;
  nombre: string;
}

export interface CredencialesPresentes {
  meta: boolean;
  youtube: boolean;
  x: boolean;
  tiktok: boolean;
}

export interface RespuestaConfig {
  fuente: string;
  fuentes_validas: string[];
  marcas: string[];
  marcas_disponibles: MarcaDisponible[];
  credenciales_presentes: CredencialesPresentes;
}

export interface CuerpoGuardarConfig {
  fuente: string;
  marcas: string[];
}

// --- Proyectos ---

export interface Proyecto {
  id: string;
  nombre: string;
  ruta: string;
  existe: boolean;
  tiene_claude_md: boolean;
  claude_md: string | null;
}

export interface RespuestaProyectos {
  proyectos: Proyecto[];
}

export interface CuerpoCrearProyecto {
  nombre: string;
  ruta: string;
}

export interface CuerpoGuardarClaudeMd {
  contenido: string;
}

// --- Carpetas ---

export interface PlantillaCarpeta {
  id: string;
  nombre: string;
}

export interface RespuestaCarpetas {
  raiz: string;
  plantillas: PlantillaCarpeta[];
}

export interface CuerpoCrearCarpeta {
  nombre: string;
  plantilla: string;
}

export interface RespuestaCrearCarpeta {
  mensaje: string;
  ruta: string;
}

// --- Skills (Generar copy) ---

export interface Skill {
  id: string;
  nombre: string;
  descripcion: string;
}

export interface GrupoSkills {
  etiqueta: string;
  experimental: boolean;
  skills: Skill[];
}

export interface RespuestaSkills {
  grupos: GrupoSkills[];
  marcas: MarcaDisponible[];
  skills_media: string[];
}

export interface CuerpoEjecutarSkill {
  skill: string;
  marca: string;
  texto: string;
  /** Redes para las que generar piezas. Si se omite, el backend decide. */
  redes?: string[];
}

/** Veredicto editorial de una pieza/generación. "" = sin veredicto. */
export type Veredicto = "listo" | "revisar" | "no_publicar" | "";

/** Una pieza generada para una red concreta. */
export interface PiezaGenerada {
  red: string;
  contenido: string;
  caracteres: number;
}

export interface RespuestaEjecutarSkill {
  resultado: string;
  historial_id: string;
  verdicto: Veredicto;
  /** Una pieza por red. Si viene vacío, se muestra `resultado` en una sola pestaña. */
  piezas: PiezaGenerada[];
}

export interface EntradaHistorial {
  id: string;
  skill: string;
  skill_nombre: string;
  marca: string;
  marca_nombre: string;
  fecha: string;
  preview: string;
}

export interface RespuestaHistorial {
  historial: EntradaHistorial[];
}

export interface DetalleHistorial {
  id: string;
  skill: string;
  marca: string;
  fecha: string;
  resultado: string;
}

// --- Tareas ---

export type EstadoTarea = string;

export interface Tarea {
  id: string;
  proyecto: string;
  proyecto_nombre: string;
  titulo: string;
  detalle: string;
  estado: EstadoTarea;
  fecha: string;
}

export interface ProyectoTarea {
  id: string;
  nombre: string;
  existe: boolean;
}

export interface RespuestaTareas {
  tareas: Tarea[];
  proyectos: ProyectoTarea[];
}

export interface CuerpoCrearTarea {
  proyecto: string;
  titulo: string;
  detalle: string;
}

export interface RespuestaCrearTarea {
  tarea: Tarea;
}

export interface CuerpoActualizarTarea {
  estado: EstadoTarea;
}

// --- Metricas ---

export interface RangoMetrica {
  id: string;
  etiqueta: string;
}

export interface OpcionesMetricas {
  marcas: MarcaDisponible[];
  rangos: RangoMetrica[];
}

export interface TotalMetricas {
  visualizaciones: number;
  alcance: number;
  interacciones: number;
  engagement_pct: number;
}

export interface CuentaMetrica {
  marca_id: string;
  marca: string;
  visualizaciones: number;
  alcance: number;
  interacciones: number;
  engagement_pct: number;
}

export interface ReporteMetricas {
  rango: string;
  etiqueta_rango: string;
  marca: string;
  total: TotalMetricas;
  cuentas: CuentaMetrica[];
}

export interface ComparativaMetrica {
  metrica: string;
  a: number;
  b: number;
  diferencia: number;
  variacion_pct: number;
}

export interface ComparativaPorMarca {
  marca_id: string;
  marca: string;
  comparativa: ComparativaMetrica[];
}

export interface CompararMetricas {
  marca: string;
  rango_a: string;
  rango_b: string;
  etiqueta_a: string;
  etiqueta_b: string;
  total: {
    metricas: ComparativaMetrica[];
  };
  por_marca: ComparativaPorMarca[];
}

// --- Publicaciones ---

/** Estados del ciclo de vida de una publicación, en orden de avance. */
export type EstadoPublicacion = "borrador" | "aprobado" | "programado" | "publicado";

/** Una red social del catálogo (id canónico + límite de caracteres). */
export interface RedPublicacion {
  id: string;
  nombre: string;
  /** Límite de caracteres; `null` si la red no tiene límite. */
  limite: number | null;
}

/** Una opción de estado para los filtros. */
export interface EstadoOpcion {
  id: string;
  nombre: string;
}

export interface OpcionesPublicaciones {
  redes: RedPublicacion[];
  estados: EstadoOpcion[];
  marcas: MarcaDisponible[];
}

export interface Publicacion {
  id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  red: string;
  red_nombre: string;
  contenido: string;
  estado: EstadoPublicacion;
  veredicto: Veredicto;
  fecha_creacion: string;
  fecha_actualizacion: string;
  /** ISO de la fecha/hora programada; `null` si no aplica. */
  fecha_programada: string | null;
  /** Origen (p. ej. `historial_id` de la generación). */
  origen: string | null;
  /** Nombre del archivo de imagen adjunto; `""` si no hay imagen. */
  imagen: string;
  /** URL para servir la imagen (`/api/media/...`); `""` si no hay imagen. */
  imagen_url: string;
}

export interface RespuestaPublicaciones {
  publicaciones: Publicacion[];
}

export interface RespuestaPublicacion {
  publicacion: Publicacion;
}

/** Cuerpo para crear una publicación. */
export interface CuerpoCrearPublicacion {
  titulo: string;
  marca: string;
  red: string;
  contenido: string;
  estado?: EstadoPublicacion;
  fecha_programada?: string | null;
  veredicto?: Veredicto;
  origen?: string | null;
  /** Nombre del archivo de imagen adjunto (vacío para ninguna). */
  imagen?: string;
}

export interface CuerpoCrearPublicacionesLote {
  publicaciones: CuerpoCrearPublicacion[];
}

/** Cuerpo parcial para actualizar una publicación. */
export interface CuerpoActualizarPublicacion {
  titulo?: string;
  contenido?: string;
  estado?: EstadoPublicacion;
  fecha_programada?: string | null;
  /** Nombre del archivo de imagen adjunto (`""` para quitarla). */
  imagen?: string;
}

/** Cuerpo opcional para duplicar una publicación (red/marca/título destino). */
export interface CuerpoDuplicarPublicacion {
  red?: string;
  marca?: string;
  titulo?: string;
}

// --- Media (imágenes) ---

/** Respuesta al subir o generar una imagen. */
export interface RespuestaMedia {
  id: string;
  /** URL para servir la imagen (`/api/media/{id}`). */
  url: string;
}

/** Cuerpo para generar una imagen con IA. */
export interface CuerpoGenerarMedia {
  prompt: string;
}

// --- Hashtags ---

/** Un grupo de hashtags guardado. */
export interface GrupoHashtags {
  id: string;
  nombre: string;
  /** Marca asociada (`""` si es general). */
  marca: string;
  marca_nombre: string;
  hashtags: string[];
}

export interface RespuestaHashtags {
  grupos: GrupoHashtags[];
}

export interface RespuestaGrupoHashtags {
  grupo: GrupoHashtags;
}

/** Cuerpo para crear o editar un grupo de hashtags. */
export interface CuerpoGrupoHashtags {
  nombre: string;
  /** Marca asociada (opcional). */
  marca?: string;
  hashtags: string[];
}

/** Cuerpo para pedir sugerencias de hashtags con IA. */
export interface CuerpoSugerirHashtags {
  texto: string;
  marca: string;
  red?: string;
}

export interface RespuestaSugerirHashtags {
  hashtags: string[];
}

// --- Franjas (colas de publicación) ---

/** Una franja horaria de la cola de publicación. */
export interface Franja {
  id: string;
  /** Marca asociada (`""` si aplica a todas). */
  marca: string;
  marca_nombre: string;
  /** Red asociada (`""` si aplica a todas). */
  red: string;
  red_nombre: string;
  /** Día de la semana: 0=lunes .. 6=domingo. */
  dia_semana: number;
  /** Hora en formato "HH:MM". */
  hora: string;
}

export interface RespuestaFranjas {
  franjas: Franja[];
}

export interface RespuestaFranja {
  franja: Franja;
}

/** Cuerpo para crear una franja. */
export interface CuerpoCrearFranja {
  dia_semana: number;
  hora: string;
  marca?: string;
  red?: string;
}

export interface FiltrosPublicaciones {
  marca?: string;
  red?: string;
  estado?: string;
  /** Permite pasarse a `query()` (Record<string, string | undefined>). */
  [clave: string]: string | undefined;
}

// --- Conexiones (clave de imagen IA + tokens de redes) ---
//
// Los secretos son write-only: nunca llegan al frontend. Del servidor solo se
// recibe el estado (`configurado`/`conectado`) y, para la imagen IA, una
// `pista` no sensible (p. ej. los últimos caracteres de la clave).

/** Estado de la configuración del proveedor de imagen con IA. */
export interface RespuestaConexionImagen {
  proveedor: string;
  modelo: string;
  configurado: boolean;
  /** Pista no sensible de la clave (nunca el valor completo). */
  pista: string;
}

/** Cuerpo para guardar la clave del proveedor de imagen IA. */
export interface CuerpoGuardarConexionImagen {
  /** Identificador del proveedor (opcional; el backend tiene uno por defecto). */
  proveedor?: string;
  api_key: string;
}

/** Respuesta al guardar la clave de imagen IA. */
export interface RespuestaGuardarConexionImagen {
  configurado: boolean;
  mensaje: string;
}

/** Respuesta de la prueba de conexión de imagen IA. */
export interface RespuestaProbarConexionImagen {
  ok: boolean;
  mensaje: string;
}

/** Estado de conexión de una red social. */
export interface RedConexion {
  plataforma: string;
  nombre: string;
  conectado: boolean;
}

export interface RespuestaConexionesRedes {
  redes: RedConexion[];
}

/** Cuerpo para conectar (guardar token de) una red social. */
export interface CuerpoConectarRed {
  token: string;
}

/** Respuesta al conectar una red social. */
export interface RespuestaConectarRed {
  conectado: boolean;
  mensaje: string;
}

// --- Respuesta generica con mensaje ---

export interface RespuestaMensaje {
  mensaje: string;
}

/** Forma de error que devuelve el backend (uno u otro campo, en espanol). */
export interface ErrorApi {
  error?: string;
  mensaje?: string;
}
