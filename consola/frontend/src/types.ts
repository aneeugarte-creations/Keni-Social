/**
 * Contrato tipado de la API de la Consola Keni (`/api/*`).
 *
 * Estos tipos reflejan exactamente las respuestas y cuerpos documentados en el
 * contrato del backend. El frontend se construye contra estos tipos; la
 * integracion runtime contra el backend real se valida al combinar ramas.
 *
 * Todo el texto orientado al usuario (nombres, detalles, mensajes) llega ya en
 * espanol desde el backend.
 *
 * ── Tipos DERIVADOS del backend (#101 / H5/E6) ──────────────────────────────
 * Un SUBCONJUNTO ESTABLE del contrato (estado, config, límites/redes, métricas y
 * las respuestas genéricas) ya NO se mantiene a mano aquí: se GENERA desde el
 * backend (`keni_consola.esquema_api`) a `types.gen.ts` con `npm run gen:types`,
 * y se re-exporta abajo. Así esos tipos no se desincronizan en silencio (el guard
 * `npm run gen:types:check` falla si divergen). El RESTO sigue a mano en este
 * archivo porque sus handlers construyen dicts ad-hoc, no modelos. Ver README.
 */

// Re-export de los tipos generados desde el backend (NO editar `types.gen.ts`).
export type {
  ResultadoEstado,
  RespuestaEstado,
  MarcaDisponible,
  CredencialesPresentes,
  RespuestaConfig,
  CuerpoGuardarConfig,
  LimiteRed,
  RespuestaLimites,
  RangoMetrica,
  OpcionesMetricas,
  TotalMetricas,
  CuentaMetrica,
  ReporteMetricas,
  ComparativaMetrica,
  ComparativaPorMarca,
  TotalComparativa,
  CompararMetricas,
  PiezaAnalisis,
  MovimientoAnalisis,
  SiguientePasoAnalisis,
  AnalisisDiario,
  Paginacion,
  MetricasRun,
  Publicacion,
  RespuestaPublicaciones,
  RespuestaPublicacion,
  RespuestaColaAprobacion,
  TotalPanel,
  PicoPanel,
  MetricasPanel,
  ColaPanel,
  ProximaPanel,
  ProximasPanel,
  GatingPanel,
  RespuestaPanel,
  Run,
  RespuestaRun,
  RespuestaRuns,
  TotalRuns,
  AgregadoPorAgente,
  AgregadoPorDia,
  RespuestaRunsAgregados,
  ActualComercial,
  SnapshotComercial,
  PublicacionComercial,
  RespuestaPublicacionesComercial,
  RespuestaPublicacionComercial,
  RespuestaRefrescarComercial,
  RespuestaMensaje,
  ErrorApi,
} from "./types.gen";

// Import LOCAL de los tipos generados que usan otras interfaces de este archivo
// (un `export type { … } from` re-exporta pero NO crea binding local utilizable aquí).
import type {
  ActualComercial,
  MarcaDisponible,
  MetricasRun,
  Paginacion,
  Publicacion,
  RangoMetrica,
  ResultadoEstado,
  Run,
} from "./types.gen";

// --- Estado (autodiagnostico del sistema) ---

/** Nivel de un chequeo del autodiagnóstico (derivado del tipo generado). */
export type NivelEstado = ResultadoEstado["estado"];

/** Una opción del selector de esfuerzo de generación (`claude --effort`). */
export interface OpcionEsfuerzo {
  id: string; // "" = predeterminado del modelo
  etiqueta: string;
  descripcion: string;
}

export interface RespuestaEsfuerzo {
  esfuerzo: string; // nivel actual ("" = predeterminado)
  opciones: OpcionEsfuerzo[];
}

export interface CuerpoGuardarEsfuerzo {
  esfuerzo: string;
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

/** Resumen de un agente (carpeta con CLAUDE.md, sub-contextos y runs) en el listado. */
export interface AgenteResumen {
  id: string;
  nombre: string;
  ruta: string;
  /**
   * `true` para las 5 marcas de serie (no se pueden renombrar ni borrar);
   * `false` para los agentes genéricos (creados/conectados, gestionables).
   */
  es_marca: boolean;
  tiene_claude_md: boolean;
  n_publicaciones: number;
  n_runs: number;
}

export interface RespuestaAgentes {
  agentes: AgenteResumen[];
}

/** Una plantilla de CLAUDE.md disponible al crear un agente genérico. */
export interface PlantillaAgente {
  id: string;
  nombre: string;
}

/** Cuerpo para crear un agente genérico. */
export interface CuerpoCrearAgente {
  nombre: string;
  /** Plantilla de CLAUDE.md (p. ej. general/noticias/deportes/podcast/social). */
  tipo?: string;
}

/** Cuerpo para registrar (conectar) una subcarpeta existente de la raíz. */
export interface CuerpoConectarAgente {
  carpeta: string;
}

/** Cuerpo para renombrar el nombre visible de un agente genérico. */
export interface CuerpoRenombrarAgente {
  nombre: string;
}

/** Respuesta al crear o conectar un agente. */
export interface RespuestaAgente {
  agente: AgenteResumen;
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

// `MetricasRun` y `Run` (`agentes._parsear_run` + listado global `/api/runs`) se
// GENERAN desde el backend y se re-exportan arriba (#101/#120). El `Run` canónico
// trae `salida`/`fecha_fin` (run completo) y, en el listado global, `agente`/
// `agente_nombre`; el `mensaje` de lanzamiento interactivo viaja en el envelope
// `RespuestaRun`, no en el run.

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

// `RespuestaRun`/`RespuestaRuns` (con `paginacion`), `Paginacion` (#121) y los
// agregados de Monitor (`TotalRuns`/`AgregadoPorAgente`/`AgregadoPorDia`/
// `RespuestaRunsAgregados`) se GENERAN desde el backend y se re-exportan arriba
// (#101/#120). `RespuestaRun` lleva `mensaje?` (lanzamiento interactivo).

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

/** Tipo de control de un campo del formulario dinámico de una skill. */
export type TipoCampo = "textarea" | "texto" | "archivo" | "select" | "fecha";

/** Forma de la salida de una skill: piezas por red o un documento único. */
export type SalidaSkill = "piezas" | "documento";

/**
 * Un campo del formulario de una skill. El frontend renderiza el control según
 * `tipo` y valida `requerido`. `opciones` solo aplica a `select`; `media_tipos`
 * (accept) solo a `archivo`.
 */
export interface Campo {
  id: string;
  etiqueta: string;
  tipo: TipoCampo;
  requerido: boolean;
  placeholder?: string;
  ayuda?: string;
  /** Opciones para `tipo === "select"`. */
  opciones?: string[];
  /** Valor `accept` del input para `tipo === "archivo"` (p. ej. "video/*,audio/*"). */
  media_tipos?: string;
}

/**
 * Una skill editorial, tal y como la expone `GET /api/skills` para el formulario
 * de Generar copy. Cada skill tiene su PROPIO formulario (definido por `campos`).
 */
export interface Skill {
  id: string;
  nombre: string;
  /** Explicación breve mostrada bajo el selector. */
  explicacion: string;
  /** `true` si la skill genera piezas por red (muestra el selector de redes). */
  aplica_redes: boolean;
  /** Forma del resultado: piezas por red o un documento Markdown. */
  salida: SalidaSkill;
  /** `true` si algún campo es de tipo archivo (envío multipart). */
  media: boolean;
  /**
   * Modo de ingesta de la fuente. "" = la fuente la pega/sube el usuario tal cual.
   * "url" = el único campo es un enlace y la Consola extrae el texto de la página en
   * el servidor antes de generar (F9); ese texto se trata como NO verificado.
   */
  ingesta?: "" | "url";
  /** Campos del formulario dinámico. */
  campos: Campo[];
}

export interface GrupoSkills {
  etiqueta: string;
  experimental: boolean;
  skills: Skill[];
}

export interface RespuestaSkills {
  grupos: GrupoSkills[];
  marcas: MarcaDisponible[];
  /** Catálogo de redes para el selector. */
  redes: MarcaDisponible[];
  skills_media: string[];
}

/**
 * Definición completa de una skill (catálogo editable). Extiende `Skill` con los
 * metadatos de gestión: grupo, orden y la plantilla de invocación.
 */
export interface SkillDef extends Skill {
  grupo: "validadas" | "experimentales";
  orden: number;
  /** Plantilla del prompt de invocación (con marcadores de campos). */
  plantilla_invocacion: string;
}

export interface RespuestaCatalogoSkills {
  skills: SkillDef[];
}

export interface RespuestaSkillDef {
  skill: SkillDef;
}

/** Respuesta de `GET /api/skills/catalogo/{id}` (def + cuerpo SKILL.md). */
export interface RespuestaDetalleSkillDef {
  skill: SkillDef;
  skill_md: string;
}

/** Cuerpo para crear una skill en el catálogo. */
export interface CuerpoCrearSkill {
  nombre: string;
  explicacion?: string;
  grupo?: "validadas" | "experimentales";
  aplica_redes?: boolean;
  salida?: SalidaSkill;
  media?: boolean;
  campos?: Campo[];
  plantilla_invocacion?: string;
}

/** Cuerpo (parcial) para actualizar los metadatos de una skill. */
export interface CuerpoActualizarSkill {
  nombre?: string;
  explicacion?: string;
  grupo?: "validadas" | "experimentales";
  aplica_redes?: boolean;
  salida?: SalidaSkill;
  media?: boolean;
  campos?: Campo[];
  plantilla_invocacion?: string;
  orden?: number;
}

/** Cuerpo para guardar el cuerpo SKILL.md de una skill. */
export interface CuerpoGuardarSkillMd {
  contenido: string;
}

/** Respuesta de guardar el SKILL.md. */
export interface RespuestaSkillMd {
  mensaje: string;
}

/** Cuerpo para previsualizar el prompt de invocación (sin llamar a Claude). */
export interface CuerpoVistaPromptSkill {
  marca: string;
  valores: Record<string, string>;
  redes: string[];
}

/** Respuesta de la vista previa del prompt. */
export interface RespuestaVistaPromptSkill {
  prompt: string;
}

/** Cuerpo para ejecutar una skill (JSON, sin archivo). */
export interface CuerpoEjecutarSkill {
  skill: string;
  marca: string;
  /** Valores del formulario dinámico: id de campo -> valor. */
  valores: Record<string, string>;
  /** Redes para las que generar piezas. Solo si la skill `aplica_redes`. */
  redes?: string[];
}

/** Cuerpo para generar copy DESDE UNA URL (skills con `ingesta === "url"`, F9). */
export interface CuerpoEjecutarSkillUrl {
  skill: string;
  marca: string;
  /** Enlace de la nota; la Consola extrae su texto en el servidor. */
  url: string;
  /** Redes para las que generar piezas. */
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

// --- Generaciones (trabajos de IA en segundo plano, seguibles en vivo) ---

/** Tipo de trabajo de IA: define cómo se renderiza su `resultado`. */
export type TipoGeneracion =
  | "copy"
  | "rss"
  | "hashtags"
  | "imagen"
  | "verificacion"
  | "qa-editorial";

/** Estado del ciclo de vida de una generación. */
export type EstadoGeneracion = "ejecutando" | "completado" | "error";

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
  /** Documento Markdown completo (skills con `salida === "documento"`). */
  documento?: string;
  // hashtags
  hashtags?: string[];
  // imagen
  id?: string;
  url?: string;
  /**
   * Imágenes producidas por una skill de imagen (estudio-imagen), ya importadas al
   * almacén de media para previsualizarlas. Cada una trae su `nombre` y la `url`
   * (`/api/media/...`). Vacío o ausente si la skill no generó imágenes.
   */
  imagenes?: ImagenGenerada[];
  // verificacion (workflow propio: datar un video)
  verificacion?: ReporteVerificacion;
  // qa-editorial (workflow propio: revisar el copy ya escrito por el community)
  informe?: InformeQaEditorial;
}

/** Una imagen producida por una skill de imagen, lista para previsualizar. */
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
  veredicto?: string | null;
  url?: string | null;
  fecha?: string | null;
}

/**
 * Reporte del motor de verificación de video (`analiza-video.py`). Junta EVIDENCIA
 * para datar un video (nuevo vs reciclado); NO es un veredicto automático.
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
  senales: SenalVerificacion[];
  avisos?: string[];
  carpeta_trabajo?: string;
}

/** Cuerpo de POST /api/verificar: el enlace del video y, opcional, lo que se afirma. */
export interface CuerpoVerificar {
  enlace: string;
  contexto?: string;
}

// --- QA editorial (revisar el copy YA escrito por el community, ficha F3 / #143) ---

/** Tipo de hallazgo del QA editorial: qué dimensión se incumple. */
export type TipoHallazgoQa = "ortografia" | "dato" | "legal" | "voz";

/** Gravedad de un hallazgo: `error` baja a 🔴; `aviso` baja (a lo sumo) a 🟡. */
export type GravedadHallazgoQa = "error" | "aviso";

/**
 * Un hallazgo de la revisión editorial: SEÑALA un problema en el copy ajeno con su
 * tipo, gravedad, el fragmento donde está y una corrección SUGERIDA (que el equipo
 * acepta o ignora; nunca se aplica sola). Si `no_verificable`, es un dato que no se
 * pudo comprobar contra la fuente: no se afirma erróneo ni se inventa el correcto.
 */
export interface HallazgoQaEditorial {
  tipo: TipoHallazgoQa;
  gravedad: GravedadHallazgoQa;
  fragmento: string;
  explicacion: string;
  sugerencia: string;
  no_verificable: boolean;
}

/**
 * Informe del QA editorial sobre el copy del community manager. Abre con un veredicto
 * 🟢/🟡/🔴 (`verdicto`, igual codificación que el resto del producto) y lista los
 * hallazgos. NO reescribe el copy ni publica: es solo el informe.
 */
export interface InformeQaEditorial {
  verdicto: Veredicto;
  resumen: string;
  hallazgos: HallazgoQaEditorial[];
  /** El informe legible completo (Markdown), por si se quiere leer/copiar entero. */
  informe_texto: string;
}

/** Respuesta de GET /api/qa-editorial: lo que necesita el formulario de revisión. */
export interface OpcionesQaEditorial {
  marcas: { id: string; nombre: string }[];
  /** Plataformas seleccionables (para validar el límite); "" = no validar límite. */
  plataformas: string[];
  /** `true` si la skill `qa-editorial` está instalada en este equipo. */
  skill_disponible: boolean;
}

/** Cuerpo de POST /api/qa-editorial/revisar: el copy a revisar + su marca/plataforma. */
export interface CuerpoRevisarQaEditorial {
  marca: string;
  texto: string;
  /** Plataforma del copy (para validar su límite). Vacío = no validar ninguno. */
  plataforma?: string;
  /** Fuente/nota contra la que comprobar datos. Vacío = datos no verificables. */
  contexto?: string;
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
  /** Motivo terminal (p. ej. "timeout"); normalmente vacío. */
  motivo: string;
  /** Texto del asistente en vivo (vacío para imágenes; crece mientras corre). */
  salida: string;
  /** Mensaje de error legible (cuando `estado === "error"`). */
  error: string;
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

// --- Termómetro mundial (galería diaria de noticias internacionales) ---

/** Config del Termómetro mundial (la comparten la página y el cron de las 7:00). */
export interface ConfigTermometro {
  /** Número de slides de noticia (5–8). */
  numero: number;
  /** Regiones a cubrir (texto libre, separadas por coma). "" = reparto por defecto. */
  regiones: string;
  /** Hora de la generación programada ("HH:MM", 24h). */
  hora: string;
  /** Marca por defecto (id canónico). "" = sin fijar. */
  marca: string;
}

/** Respuesta de GET /api/termometro. */
export interface RespuestaTermometro {
  config: ConfigTermometro;
  /** `true` si la skill `termometro-mundial` está instalada en este equipo. */
  skill_disponible: boolean;
  marcas: MarcaDisponible[];
  regiones_sugeridas: string[];
}

/** Cuerpo de PUT /api/termometro/config (parcial: solo las claves a cambiar). */
export type CuerpoGuardarTermometro = Partial<ConfigTermometro>;

/** Respuesta de PUT /api/termometro/config. */
export interface RespuestaConfigTermometro {
  config: ConfigTermometro;
}

/** Cuerpo de POST /api/termometro/generar. */
export interface CuerpoGenerarTermometro {
  marca: string;
  /** Noticias internacionales candidatas (la materia prima de la galería). */
  noticias: string;
  /** Número de slides (5–8) como texto; vacío = el de la config/skill. */
  numero?: string;
  /** Regiones a cubrir (CSV); vacío = reparto por defecto. */
  regiones?: string;
  /** Fecha de la portada (YYYY-MM-DD); vacío = hoy. */
  fecha?: string;
}

// --- Radar de tendencias (lo más viral del momento, multi-red · F7/#147) ---

/** Una nota/enlace que explica por qué sube un tema (título + URL + medio). */
export interface EnlaceRadar {
  titulo: string;
  url: string;
  /** Medio/fuente de la nota (p. ej. "ESPN Deportes"). */
  fuente: string;
}

/** Un tema en tendencia, consolidado de una o varias fuentes y deduplicado. */
export interface TemaRadar {
  titulo: string;
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
  enlaces: EnlaceRadar[];
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
  /** Nº total de temas consolidados. */
  total: number;
}

export interface EntradaHistorial {
  id: string;
  skill: string;
  skill_nombre: string;
  marca: string;
  marca_nombre: string;
  fecha: string;
  preview: string;
  /** Atribución por usuario (#130 Fase 1): id estable de quien generó. "" si legado/anónimo. */
  autor_id: string;
  /** Nombre de quien generó (para mostrar). "" si legado/anónimo. */
  autor_nombre: string;
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
  /** Atribución por usuario (#130 Fase 1): id estable de quien generó. "" si legado/anónimo. */
  autor_id: string;
  /** Nombre de quien generó (para mostrar). "" si legado/anónimo. */
  autor_nombre: string;
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
  /** Atribución por usuario (#130 Fase 1): id estable de quien creó. "" si legado/anónimo. */
  autor_id: string;
  /** Nombre de quien creó (para mostrar). "" si legado/anónimo. */
  autor_nombre: string;
  /** Tablero compartido (#145 F5): id del responsable asignado. "" si sin asignar. */
  responsable_id: string;
  /** Nombre del responsable (para mostrar). "" si sin asignar. */
  responsable_nombre: string;
  /** Enlace/ruta opcional para actuar sobre el pendiente (abrir asistente, generar copy…). "" si no hay. */
  enlace: string;
}

export interface ProyectoTarea {
  id: string;
  nombre: string;
  existe: boolean;
}

/** Usuario asignable como responsable (#145 F5): solo id + nombre. */
export interface UsuarioTarea {
  id: string;
  usuario: string;
}

export interface RespuestaTareas {
  tareas: Tarea[];
  proyectos: ProyectoTarea[];
  /** Usuarios reales para el selector de responsable (#145 F5). */
  usuarios: UsuarioTarea[];
}

export interface CuerpoCrearTarea {
  proyecto: string;
  titulo: string;
  detalle: string;
  /** Responsable asignado al crear (#145 F5). "" / omitido = sin asignar. */
  responsable_id?: string;
  /** Enlace/ruta opcional para actuar sobre el pendiente (#145 F5). */
  enlace?: string;
}

export interface RespuestaCrearTarea {
  tarea: Tarea;
}

/** Cambios parciales sobre un pendiente (#145 F5): cada campo es opcional. */
export interface CuerpoActualizarTarea {
  estado?: EstadoTarea;
  /** "" desasigna; un id real reasigna. */
  responsable_id?: string;
  enlace?: string;
}

// --- Rota de horarios del equipo (F4 · #144) ---

/** Un miembro del equipo (un usuario de la consola) disponible para la rota. */
export interface MiembroRota {
  id: string;
  nombre: string;
}

export interface RespuestaEquipoRota {
  equipo: MiembroRota[];
}

/** Cómo se cubre un evento: con señal (transmisión), solo imágenes, o no se cubre. */
export type TipoCoberturaEvento = "transmision" | "imagenes" | "no_cubrir";

/** Prioridad de un evento del calendario (pista visual para qué cubrir primero). */
export type PrioridadEvento = "alta" | "media" | "baja";

/** Un evento/transmisión a cubrir: cuándo es, QUÉ sacar y CÓMO se cubre. */
export interface EventoRota {
  id: string;
  titulo: string;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  hora: string;
  /** "Qué sacar" de esta transmisión (el campo clave del Excel de Elías). */
  contenido: string;
  nota: string;
  /** Tipo de cobertura: transmisión (con señal) / solo imágenes / no cubrir. */
  tipo_cobertura: TipoCoberturaEvento;
  /** Prioridad del evento (alta/media/baja). */
  prioridad: PrioridadEvento;
  /** `true` si se reprogramó y aún no se ha avisado al equipo ("Cambió"). */
  cambiado: boolean;
  /** ISO de la última edición. */
  actualizado: string;
  es_sabado: boolean;
}

export interface RespuestaEventosRota {
  eventos: EventoRota[];
}

export interface RespuestaEventoRota {
  evento: EventoRota;
}

export interface CuerpoCrearEventoRota {
  titulo: string;
  fecha: string;
  hora?: string;
  contenido?: string;
  nota?: string;
  tipo_cobertura?: TipoCoberturaEvento;
  prioridad?: PrioridadEvento;
}

/**
 * Edición parcial de un evento (todo opcional; se manda lo que cambia). Editar
 * `fecha`/`hora`/`tipo_cobertura` lo marca como reprogramado (`cambiado=1`);
 * `cambiado:false` es la acción "marcar avisado" (limpia el aviso).
 */
export type CuerpoActualizarEventoRota = Partial<CuerpoCrearEventoRota> & {
  cambiado?: boolean;
};

/** Estado de un turno: `propuesto` (Keni) o `aprobado` (publicado por Elías). */
export type EstadoTurnoRota = "propuesto" | "aprobado";

/** Un turno: un miembro cubre un evento. Vincula ambos + qué sacar. */
export interface TurnoRota {
  id: string;
  /** Lunes ISO de la semana. */
  semana: string;
  evento_id: string;
  evento_titulo: string;
  evento_fecha: string;
  evento_hora: string;
  contenido: string;
  es_sabado: boolean;
  miembro_id: string;
  miembro_nombre: string;
  estado: EstadoTurnoRota;
  /** Cobertura forzada que rompe la rotación de sábados (la decide Elías). */
  override: boolean;
  motivo: string;
}

/** La rota de una semana: turnos + rango + si está publicada. */
export interface RotaSemana {
  /** Lunes ISO. */
  lunes: string;
  inicio: string;
  fin: string;
  turnos: TurnoRota[];
  /** `true` => todos los turnos aprobados (publicada al equipo). */
  aprobada: boolean;
  total: number;
  /** Mensaje de confirmación (p. ej. tras aprobar). */
  mensaje?: string;
}

export interface CuerpoAprobarRota {
  /** Lunes (o cualquier día) de la semana a aprobar. */
  lunes: string;
}

/** Edición de un turno por Elías (todo opcional; se manda lo que cambia). */
export interface CuerpoActualizarTurnoRota {
  miembro_id?: string;
  override?: boolean;
  motivo?: string;
  estado?: EstadoTurnoRota;
}

export interface RespuestaTurnoRota {
  turno: TurnoRota;
}

/** "Mi próxima semana": la semana + los turnos del usuario actual. */
export interface MiSemanaRota extends RotaSemana {
  miembro_id: string;
  miembro_nombre: string;
  mis_turnos: TurnoRota[];
  /** Aviso si no hay sesión (token de mantenimiento). */
  aviso?: string;
}

// --- Gestión de turnos: horario de trabajo + ausencias (F4 · #144, ola A) ---

/** Tipo de una ausencia/vacación. */
export type TipoAusencia = "vacaciones" | "descanso" | "baja" | "otro";

/** Una ausencia: un rango (inclusivo) en que un miembro NO está disponible. */
export interface AusenciaRota {
  id: string;
  miembro_id: string;
  miembro_nombre: string;
  tipo: TipoAusencia;
  /** ISO (AAAA-MM-DD), inclusivo. */
  desde: string;
  hasta: string;
  motivo: string;
}

export interface RespuestaAusenciasRota {
  ausencias: AusenciaRota[];
}

export interface RespuestaAusenciaRota {
  ausencia: AusenciaRota;
}

export interface CuerpoCrearAusenciaRota {
  miembro_id: string;
  desde: string;
  hasta: string;
  tipo?: TipoAusencia;
  motivo?: string;
}

/** Edición de una ausencia (todo opcional; se manda lo que cambia). */
export interface CuerpoActualizarAusenciaRota {
  tipo?: TipoAusencia;
  desde?: string;
  hasta?: string;
  motivo?: string;
}

/** Franja de un turno de trabajo: mañana / tarde / descanso. */
export type FranjaTurno = "matutino" | "vespertino" | "descanso";

/** Un turno de TRABAJO: una persona trabaja una franja un día. */
export interface TurnoTrabajoRota {
  id: string;
  /** Lunes ISO de la semana. */
  semana: string;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  miembro_id: string;
  miembro_nombre: string;
  franja: FranjaTurno;
  estado: EstadoTurnoRota;
  /** Cobertura forzada que rompe la rotación de sábados (la decide Elías). */
  override: boolean;
  motivo: string;
  /** Reporte de fin de turno: qué queda pendiente para el siguiente. */
  nota_relevo: string;
  es_sabado: boolean;
}

/** El horario de trabajo de una semana: turnos + rango + si está publicado. */
export interface HorarioSemana {
  /** Lunes ISO. */
  lunes: string;
  inicio: string;
  fin: string;
  /** Las 7 fechas ISO (lunes->domingo) de la semana. */
  dias: string[];
  turnos: TurnoTrabajoRota[];
  /** `true` => todos los turnos aprobados (publicado al equipo). */
  aprobada: boolean;
  total: number;
  /** Mensaje de confirmación (p. ej. tras aprobar). */
  mensaje?: string;
}

/** Edición de un turno de trabajo por Elías (todo opcional). */
export interface CuerpoActualizarTurnoTrabajoRota {
  franja?: FranjaTurno;
  miembro_id?: string;
  override?: boolean;
  motivo?: string;
  nota_relevo?: string;
  estado?: EstadoTurnoRota;
}

export interface RespuestaTurnoTrabajoRota {
  turno: TurnoTrabajoRota;
}

/** "Mi próximo horario": el horario + los turnos de trabajo del usuario actual. */
export interface MiHorarioRota extends HorarioSemana {
  miembro_id: string;
  miembro_nombre: string;
  mis_turnos: TurnoTrabajoRota[];
  /** Aviso si no hay sesión (token de mantenimiento). */
  aviso?: string;
}

// --- Metricas ---
//
// Los tipos de métricas (`RangoMetrica`, `OpcionesMetricas`, `TotalMetricas`,
// `CuentaMetrica`, `ReporteMetricas`, `ComparativaMetrica`, `ComparativaPorMarca`,
// `CompararMetricas`) se GENERAN desde el backend y se re-exportan arriba. Ver #101.
// NOTA: `fuente` ahora es REQUERIDO (el backend siempre lo emite, cae a "muestra").

// --- Reporte de deportes (deck semanal de Claro Sports) ---

export interface OpcionesReporteDeportes {
  rangos: RangoMetrica[];
  cuenta: { id: string; nombre: string };
  hermanas: { id: string; nombre: string }[];
}

/** Un evento de la agenda editorial (curaduría manual). */
export interface EventoAgenda {
  nombre: string;
  plan: string;
}

export interface AgendaReporte {
  principales: EventoAgenda[];
  propios: EventoAgenda[];
}

export interface CuerpoReporteDeportes {
  rango: string;
  top?: number;
  agenda?: AgendaReporte;
}

export interface PiezaReporte {
  plataforma: string;
  titulo: string;
  visualizaciones: number;
  interacciones: number;
  url: string | null;
  publicado: string;
}

export interface BloquePlataforma {
  plataforma: string;
  piezas: PiezaReporte[];
}

export interface PromocionHermana {
  cuenta: string;
  nombre: string;
  piezas: PiezaReporte[];
  /** Procedencia: `"muestra"` (sintéticos), `"real"` o `"sin_datos_reales"`
   *  (cuenta no conectada todavía: no se inventan cifras, #141). */
  datos?: "muestra" | "real" | "sin_datos_reales";
}

export interface ReporteDeportes {
  tipo: string;
  rango: string;
  /** Periodo concreto del reporte (lun→dom de la semana cerrada por defecto). */
  periodo?: { desde: string; hasta: string };
  generado: string;
  fuente: string;
  cuenta: { id: string; nombre: string };
  mejores_por_plataforma: BloquePlataforma[];
  promocion_hermanas: PromocionHermana[];
  agenda: { principales: EventoAgenda[]; propios: EventoAgenda[]; nota?: string };
}

// --- Publicaciones ---

/** Estados del ciclo de vida de una publicación, en orden de avance.
 *
 * Se DERIVA del tipo generado `Publicacion["estado"]` para no driftar del backend
 * (el flujo de aprobación de equipo, #9, añadió `en_revision`): si el backend cambia
 * el set de estados, este alias lo sigue solo. */
export type EstadoPublicacion = Publicacion["estado"];

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

// `LimiteRed` y `RespuestaLimites` (`GET /api/limites`, fuente única de los topes
// de caracteres; ver #112) se GENERAN desde el backend y se re-exportan arriba (#101).

// `Publicacion` (`dominio.publicaciones.publicacion_a_dict`), `RespuestaPublicaciones`
// (con `paginacion`, #121) y `RespuestaPublicacion` se GENERAN desde el backend y se
// re-exportan arriba (#101/#120). OJO: el backend SIEMPRE emite `fecha_programada`/
// `origen` como cadena ("" si no aplica), nunca `null` — el tipo generado lo refleja.

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

// --- Reciclaje proactivo (sugerencias de archivo a retomar, #110) ---

/** Motivo por el que el archivo sugiere retomar una pieza (heurística explicable). */
export type MotivoReciclaje = "efemeride" | "perenne" | "recurrente";

/** Una pieza de archivo que la heurística propone reciclar, con su motivo. */
export interface SugerenciaReciclaje {
  id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  red: string;
  red_nombre: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
  /** Tipo de señal que la hizo candidata. */
  motivo: MotivoReciclaje;
  /** Frase en es-MX que explica POR QUÉ retomarla ahora. */
  motivo_detalle: string;
  /** Puntuación interna para ordenar (mayor = más prioritaria). */
  puntuacion: number;
}

/** Parámetros (días) de la heurística, para que la UI los pueda mostrar. */
export interface ParametrosReciclaje {
  ventana_efemeride_dias: number;
  edad_minima_perenne_dias: number;
  edad_minima_antiguedad_dias: number;
}

/** Respuesta de `GET /api/reciclaje/sugerencias`. */
export interface RespuestaSugerenciasReciclaje {
  sugerencias: SugerenciaReciclaje[];
  parametros: ParametrosReciclaje;
}

/** Filtros opcionales para pedir sugerencias de reciclaje. */
export interface FiltrosReciclaje {
  marca?: string;
  red?: string;
  /** Permite pasarse a `query()` (Record<string, string | undefined>). */
  [clave: string]: string | undefined;
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
  /** Paginacion offset-based (#121): tamaño de pagina; ausente = conjunto completo. */
  limite?: string;
  /** Paginacion offset-based (#121): offset; ausente = 0. */
  desplazamiento?: string;
  /** Permite pasarse a `query()` (Record<string, string | undefined>). */
  [clave: string]: string | undefined;
}

// --- Conexiones (clave de imagen IA + tokens de redes) ---
//
// Los secretos son write-only: nunca llegan al frontend. Del servidor solo se
// recibe el estado (`configurado`/`conectado`) y, para la imagen IA, una
// `pista` no sensible (p. ej. los últimos caracteres de la clave).

/** Un modelo de imagen IA de la lista curada (id + etiqueta legible para el dropdown). */
export interface ModeloImagen {
  id: string;
  etiqueta: string;
}

/** Estado de la configuración del proveedor de imagen con IA. */
export interface RespuestaConexionImagen {
  proveedor: string;
  /** Modelo de imagen EN USO (con su precedencia: almacén > env > por defecto). */
  modelo: string;
  /** Lista curada de modelos disponibles para el dropdown del selector. */
  modelos: ModeloImagen[];
  configurado: boolean;
  /** Pista no sensible de la clave (nunca el valor completo). */
  pista: string;
}

/** Cuerpo para fijar el modelo de imagen IA. */
export interface CuerpoGuardarModeloImagen {
  modelo: string;
}

/** Respuesta al fijar el modelo de imagen IA (devuelve el modelo guardado). */
export interface RespuestaGuardarModeloImagen {
  modelo: string;
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

// --- Buzón de sugerencias ---

export interface Sugerencia {
  id: string;
  titulo: string;
  detalle: string;
  categoria: string;
  estado: string;
  autor: string;
  creada: string;
}

export interface RespuestaSugerencias {
  sugerencias: Sugerencia[];
  categorias: string[];
  estados: string[];
}

export interface RespuestaSugerencia {
  sugerencia: Sugerencia;
}

export interface CuerpoCrearSugerencia {
  titulo: string;
  detalle?: string;
  categoria?: string;
  autor?: string;
}

export interface CuerpoActualizarSugerencia {
  estado: string;
}

// --- Respuesta generica con mensaje ---
//
// `RespuestaMensaje` y `ErrorApi` se GENERAN desde el backend y se re-exportan
// arriba. Ver #101.

// --- Comercial (seguimiento de publicaciones comerciales) ---

export type EstadoComercial = "activa" | "pausada" | "cerrada";
export type MetricaComercial = "interacciones" | "alcance";

// `SnapshotComercial`, `ActualComercial`, `PublicacionComercial` (`api/comercial._a_dict`)
// y las respuestas `RespuestaPublicacionesComercial`/`RespuestaPublicacionComercial`/
// `RespuestaRefrescarComercial` se GENERAN desde el backend y se re-exportan arriba
// (#101/#120). `fuente`/`es_muestra` (#124) son REQUERIDOS (el backend siempre los
// emite). El reporte (`RespuestaReporteComercial`, unión publicación|campaña) sigue a
// mano: su forma es polimórfica y aún no se modela en el subconjunto estable.

export interface OpcionComercial {
  id: string;
  nombre: string;
}

export interface RedComercial {
  id: string;
  nombre: string;
  limite?: number;
}

export interface OpcionesComercial {
  marcas: MarcaDisponible[];
  redes: RedComercial[];
  estados: OpcionComercial[];
  metricas: OpcionComercial[];
}

export interface CuerpoCrearComercial {
  url: string;
  titulo?: string;
  marca?: string;
  cliente?: string;
  campania?: string;
  red?: string;
  metrica_objetivo?: MetricaComercial;
  objetivo?: number;
  estado?: EstadoComercial;
  publicado?: string;
  notas?: string;
}

export type CuerpoActualizarComercial = Partial<Omit<CuerpoCrearComercial, "url">>;

export interface FiltrosComercial {
  estado?: string;
  cliente?: string;
  campania?: string;
  /** Permite pasarse a `query()` (Record<string, string | undefined>). */
  [clave: string]: string | undefined;
}

/** Datos de una pieza dentro de un reporte (nombres ya resueltos en servidor). */
export interface PiezaReporteComercial {
  id: string;
  titulo: string;
  url: string;
  cliente: string;
  campania: string;
  marca: string;
  marca_nombre: string;
  red: string;
  red_nombre: string;
  publicado: string;
  estado: EstadoComercial;
}

export interface ObjetivoReporteComercial {
  metrica: MetricaComercial;
  valor: number;
  progreso_pct: number;
  alcanzado: boolean;
  aviso_en: string;
}

export interface ReportePublicacionComercial {
  tipo: "publicacion";
  generado: string;
  /** Procedencia de las cifras (`"muestra"` = sintéticas). */
  fuente?: string;
  /** `true` mientras las cifras sean de muestra (sintéticas), no reales. */
  es_muestra?: boolean;
  publicacion: PiezaReporteComercial;
  periodo: { desde: string; hasta: string };
  actual: ActualComercial;
  objetivo: ObjetivoReporteComercial;
  puntos: number;
}

export interface FilaReporteCampania {
  publicacion: PiezaReporteComercial;
  actual: ActualComercial;
  objetivo: ObjetivoReporteComercial;
}

export interface ReporteCampaniaComercial {
  tipo: "campania";
  generado: string;
  /** Procedencia de las cifras (`"muestra"` = sintéticas). */
  fuente?: string;
  /** `true` mientras las cifras sean de muestra (sintéticas), no reales. */
  es_muestra?: boolean;
  campania: string;
  cliente: string;
  piezas: FilaReporteCampania[];
  total: {
    interacciones: number;
    alcance: number;
    engagement_pct: number;
    piezas: number;
  };
}

export type ReporteComercial = ReportePublicacionComercial | ReporteCampaniaComercial;

export interface RespuestaReporteComercial {
  reporte: ReporteComercial;
}

// --- Autenticación y usuarios (#auth) --------------------------------------
//
// Auth por usuario/contraseña sobre cookie de sesión (la pone el backend). El
// login devuelve el usuario actual; `GET /api/auth/me` lo recupera al cargar la
// app. La gestión de usuarios (`/api/usuarios`) es solo para el rol admin.

/** Rol de un usuario de la consola. `admin` ve además la gestión de usuarios. */
export type RolUsuario = "admin" | "editor";

/** Usuario autenticado (lo que devuelven login y `/api/auth/me`). */
export interface UsuarioSesion {
  id: string;
  usuario: string;
  rol: RolUsuario;
  /** `true` => hay que forzar el cambio de contraseña antes de usar la app. */
  debe_cambiar_password: boolean;
  /**
   * ISO 8601 de creación de la cuenta. Solo llega por `GET /api/auth/me` (la página
   * "Mi cuenta" lo muestra); el login devuelve la forma mínima y no lo incluye.
   */
  creado?: string;
  /** ISO 8601 del último acceso (vacío si nunca entró). Solo llega por `me`. */
  ultimo_acceso?: string;
}

/** Respuesta de `POST /api/auth/login` y `GET /api/auth/me`. */
export interface RespuestaSesion {
  usuario: UsuarioSesion;
}

/** Cuerpo de `POST /api/auth/login`. */
export interface CuerpoLogin {
  usuario: string;
  password: string;
}

/** Cuerpo de `POST /api/auth/cambiar-password`. */
export interface CuerpoCambiarPassword {
  password_actual: string;
  password_nueva: string;
}

/** Fila del listado `GET /api/usuarios` (solo admin). */
export interface UsuarioAdmin {
  id: string;
  usuario: string;
  rol: RolUsuario;
  /** ISO 8601 de creación. */
  creado: string;
  /** ISO 8601 del último acceso, o `null` si nunca entró. */
  ultimo_acceso: string | null;
}

/** Respuesta de `GET /api/usuarios`: el backend envuelve la lista en `{ usuarios }`. */
export interface RespuestaUsuarios {
  usuarios: UsuarioAdmin[];
}

/** Cuerpo de `POST /api/usuarios` (alta de usuario). */
export interface CuerpoCrearUsuario {
  usuario: string;
  password: string;
  rol: RolUsuario;
}

/**
 * Cuerpo de `PATCH /api/usuarios/{id}`: cambiar rol y/o resetear contraseña.
 * Ambos campos son opcionales (se manda solo lo que cambia).
 */
export interface CuerpoActualizarUsuario {
  rol?: RolUsuario;
  password?: string;
}
