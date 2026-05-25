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

// --- Agentes (marca = carpeta con CLAUDE.md, sub-contextos y runs) ---

/** Resumen de un agente (una marca = su carpeta) en el listado. */
export interface AgenteResumen {
  id: string;
  nombre: string;
  ruta: string;
  tiene_claude_md: boolean;
  n_publicaciones: number;
  n_runs: number;
}

export interface RespuestaAgentes {
  agentes: AgenteResumen[];
}

/** Un sub-contexto del agente: un archivo `contexto/*.md`. */
export interface SubContexto {
  nombre: string;
  contenido: string;
}

/** Modo de ejecución de un run del agente. */
export type ModoRun = "headless" | "interactivo";

/**
 * Estado del ciclo de vida de un run. `ejecutando` = corriendo en segundo plano
 * (se sondea hasta `completado`/`error`); `lanzado` = run interactivo abierto.
 */
export type EstadoRun = "completado" | "error" | "ejecutando" | "lanzado" | string;

/**
 * Métricas de monitorización de un run IA, tal y como las reporta el CLI cuando
 * devuelve JSON. Puede venir `null` (p. ej. un run interactivo o un CLI que no
 * emitió JSON), en cuyo caso la UI no muestra cifras.
 */
export interface MetricasRun {
  /** Tokens de entrada (prompt) consumidos. */
  tokens_in: number;
  /** Tokens de salida (respuesta) generados. */
  tokens_out: number;
  /** Número de turnos del run. */
  num_turns: number;
  /** Coste total en dólares estadounidenses. */
  total_cost_usd: number;
  /** Duración del run en milisegundos. */
  duration_ms: number;
  /** Identificador del modelo usado. */
  modelo: string;
}

/** Un run (ejecución) del agente. */
export interface Run {
  id: string;
  prompt: string;
  modo: ModoRun;
  estado: EstadoRun;
  fecha_inicio: string;
  /** Salida del run headless (puede venir vacía mientras corre o si es interactivo). */
  salida?: string;
  /** Mensaje legible (p. ej. al lanzar uno interactivo). */
  mensaje?: string;
  /** Métricas de monitorización (tokens, coste, duración…); `null` si no hay. */
  metricas?: MetricasRun | null;
  /** Id del agente dueño del run (presente en el listado global `/api/runs`). */
  agente?: string;
  /** Nombre legible del agente (presente en el listado global `/api/runs`). */
  agente_nombre?: string;
}

/** Detalle completo de un agente. */
export interface AgenteDetalle {
  id: string;
  nombre: string;
  ruta: string;
  claude_md: string;
  sub_contextos: SubContexto[];
  runs: Run[];
}

export interface RespuestaSubContextos {
  sub_contextos: SubContexto[];
}

/** Cuerpo para guardar el contenido de un sub-contexto. */
export interface CuerpoGuardarContexto {
  contenido: string;
}

/** Cuerpo para lanzar un run del agente. */
export interface CuerpoCrearRun {
  prompt: string;
  modo: ModoRun;
}

export interface RespuestaRun {
  run: Run;
}

export interface RespuestaRuns {
  runs: Run[];
}

// --- Monitorización de actividad IA (runs globales + agregados) ---

/** Totales acumulados de toda la actividad IA del periodo disponible. */
export interface TotalRuns {
  coste_usd: number;
  tokens: number;
  runs: number;
}

/** Agregado de actividad IA por agente. */
export interface AgregadoPorAgente {
  agente: string;
  agente_nombre: string;
  coste_usd: number;
  tokens: number;
  runs: number;
}

/** Agregado de actividad IA por día (clave `dia` en ISO `YYYY-MM-DD`). */
export interface AgregadoPorDia {
  dia: string;
  coste_usd: number;
  tokens: number;
  runs: number;
}

/** Respuesta de `GET /api/runs/agregados`. */
export interface RespuestaRunsAgregados {
  total: TotalRuns;
  por_agente: AgregadoPorAgente[];
  por_dia: AgregadoPorDia[];
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
  /** Título opcional para las publicaciones creadas a partir del copy. */
  titulo?: string;
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
  /**
   * Publicaciones ya creadas (borradores), una por red. Si viene vacío, no se
   * guardó nada automáticamente y hay que guardar a mano eligiendo red.
   */
  publicaciones: Publicacion[];
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
  /** Título de la generación (puede venir vacío en entradas antiguas). */
  titulo: string;
  /** Piezas por red (pueden venir vacías en entradas antiguas). */
  piezas: PiezaGenerada[];
}

/**
 * Cuerpo opcional para recuperar una entrada del historial como publicación(es)
 * (`POST /api/skills/historial/{id}/guardar`). Si la entrada no tiene piezas,
 * hay que indicar `red`; si las tiene, `redes` permite acotar cuáles guardar.
 */
export interface CuerpoGuardarHistorial {
  titulo?: string;
  /** Subconjunto de redes a guardar (cuando la entrada tiene piezas). */
  redes?: string[];
  /** Red obligatoria cuando la entrada no tiene piezas. */
  red?: string;
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
  /** Marcada como contenido perenne (reutilizable indefinidamente). */
  evergreen: boolean;
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
  /** Marca/desmarca la publicación como perenne. */
  evergreen?: boolean;
  /** Nombre del archivo de imagen adjunto (`""` para quitarla). */
  imagen?: string;
}

/** Respuesta al reciclar una publicación perenne. */
export interface RespuestaReciclarPublicacion {
  publicacion: Publicacion;
  /** `true` si quedó encolada (con fecha); `false` si quedó como borrador. */
  encolado: boolean;
}

/** Cuerpo opcional para duplicar una publicación (red/marca/título destino). */
export interface CuerpoDuplicarPublicacion {
  red?: string;
  marca?: string;
  titulo?: string;
}

// --- Plantillas de post (copy reutilizable) ---

/** Una plantilla de copy guardada. */
export interface Plantilla {
  id: string;
  nombre: string;
  /** Marca asociada (`""` si es general). */
  marca: string;
  marca_nombre: string;
  /** Red asociada (`""` si aplica a cualquier red). */
  red: string;
  red_nombre: string;
  contenido: string;
}

export interface RespuestaPlantillas {
  plantillas: Plantilla[];
}

export interface RespuestaPlantilla {
  plantilla: Plantilla;
}

/** Cuerpo para crear una plantilla. */
export interface CuerpoCrearPlantilla {
  nombre: string;
  /** Marca asociada (opcional). */
  marca?: string;
  /** Red asociada (opcional). */
  red?: string;
  contenido: string;
}

/** Cuerpo parcial para actualizar una plantilla. */
export interface CuerpoActualizarPlantilla {
  nombre?: string;
  marca?: string;
  red?: string;
  contenido?: string;
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
  /** `true` si el item ya se marcó como usado. */
  usado: boolean;
}

export interface RespuestaItemsRss {
  items: ItemRss[];
  /** Errores por feed al refrescar (mensajes legibles en español). */
  errores: string[];
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
}

/**
 * Respuesta de generar copy desde un item (auto-guarda como Publicaciones).
 * Misma forma que ejecutar una skill.
 */
export interface RespuestaGenerarDesdeItem {
  resultado: string;
  historial_id: string;
  verdicto: Veredicto;
  piezas: PiezaGenerada[];
  publicaciones: Publicacion[];
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
  /** "1" para mostrar solo publicaciones perennes. */
  evergreen?: string;
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
