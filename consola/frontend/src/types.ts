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
  EstadoMetricas,
  PeriodoMetricas,
  EstadisticasNumericas,
  PiezaMetrica,
  DistribucionBucket,
  AnaliticaPiezas,
  PuntoSerie,
  TendenciaDiaria,
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

/** Subtipo de un posteo de la parrilla (vacío para los video-editoriales). */
export type SubtipoParrilla = "clip" | "galeria" | "infografia" | "normal" | "";

/** Un tema clasificado y jerarquizado para la parrilla del día. */
export interface ItemParrilla {
  titulo: string;
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
  cuota_posteos: number;
  cuota_editorial: number;
  /** Geo/contexto usado en el scoring. */
  contexto: string;
}

/** Resultado de programar una pieza en Metricool (preview dry-run o publicación real). */
export interface ResultadoProgramarMetricool {
  ok: boolean;
  /** true = solo se previsualizó (no se publicó); false = se publicó de verdad. */
  dry_run: boolean;
  /** Presente cuando ok=false: por qué no se pudo (sin credenciales, sin contenido…). */
  motivo?: string;
  /** Redes destino (nomenclatura Metricool: facebook/instagram/twitter/tiktok/youtube). */
  redes?: string[];
  /** Cuerpo exacto que se enviaría/envió al scheduler (preview). */
  cuerpo?: Record<string, unknown>;
  /** Id del post en Metricool (solo en publicación real). */
  id_post?: string;
  /** Estado por red devuelto por Metricool (solo en publicación real). */
  estados?: Record<string, string>;
}

/** Respuesta de POST /api/publicaciones/{id}/metricool. */
export interface RespuestaProgramarMetricool {
  resultado: ResultadoProgramarMetricool;
  /** Pieza tras el intento (actualizada a `publicado` si fue real); null si desapareció. */
  publicacion: Publicacion | null;
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
  /** Si la tarea está asociada a un evento de la rota: id del evento. "" / omitido si no. */
  evento_id?: string;
  /** Título del evento asociado (para mostrar). */
  evento_titulo?: string;
  /** Fecha del evento asociado (AAAA-MM-DD). */
  evento_fecha?: string;
  /** Hora del evento asociado. */
  evento_hora?: string;
  /** Tipo de cobertura del evento asociado. */
  evento_tipo_cobertura?: TipoCoberturaEvento;
  /** `true` si el proyecto referenciado existe en la allowlist. `false` si la tarea apunta a un proyecto borrado. */
  proyecto_existe?: boolean;
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
  /**
   * Eventos próximos de la rota cuya cobertura aún no tiene un pendiente asociado.
   * Aparecen como "pendientes implícitos" arriba del tablero (clic = crear tarea
   * con `evento_id` prellenado). Vacío si no hay eventos sin cubrir o si el equipo
   * no usa rota.
   */
  eventos_sin_cubrir: EventoSinCubrir[];
}

/** Evento de la rota que sigue sin cubrir (pendiente implícito). */
export interface EventoSinCubrir {
  id: string;
  titulo: string;
  /** AAAA-MM-DD. */
  fecha: string;
  hora: string;
  contenido: string;
  tipo_cobertura: TipoCoberturaEvento;
  prioridad: PrioridadEvento;
}

export interface CuerpoCrearTarea {
  /** OPCIONAL (#145 F5): "" o ausente crea un pendiente libre, sin proyecto. */
  proyecto?: string;
  titulo: string;
  detalle?: string;
  /** Responsable asignado al crear (#145 F5). "" / omitido = sin asignar. */
  responsable_id?: string;
  /** Enlace/ruta opcional para actuar sobre el pendiente (#145 F5). */
  enlace?: string;
  /** Si el pendiente cubre un evento de la rota: id del evento. */
  evento_id?: string;
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

// --- Tablero de CONTENIDO unificado (herramienta de community manager) ---

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
  copy: string;
  imagen: string;
  veredicto: string;
  fecha_programada: string;
  hora_post: string;
  enlace: string;
  evergreen: boolean;
}

/** Un item del tablero: contenido publicable (con plataformas) o tarea libre del equipo. */
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
  /** Derivado: deadline pasado y aún sin cerrar. */
  vencido: boolean;
  plataformas: ContenidoPlataforma[];
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
  /** Redes para crear una fila por plataforma por cada una. */
  redes?: string[];
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
  enlace?: string;
  fecha_programada?: string;
  hora_post?: string;
  veredicto?: string;
  evergreen?: boolean;
}

export interface RespuestaContenidoItem {
  contenido: Contenido;
}

export interface RespuestaPlataforma {
  plataforma: ContenidoPlataforma;
}

export interface CuerpoDesdeRadar {
  titulo: string;
  marca?: string;
  redes?: string[];
  prioridad?: PrioridadEvento;
  descripcion?: string;
}

// --- Rota de horarios del equipo (F4 · #144) ---

/** Un miembro del equipo (un usuario de la consola) disponible para la rota.
 *
 * `marcas` viene del organigrama AMX (ola `feat/roles-marcas`): ids canónicos de las
 * verticales a las que pertenece (claro-sports, unotv...). La rota hoy solo cubre
 * ClaroSports; el front filtra por `marcas.includes("claro-sports")`.
 *
 * `cargo` (funcion en el organigrama, p.ej. `community_manager`, `coordinador_redes`) y
 * `cobertura` (¿esta miembro disponible para cubrir turnos?) permiten al frontend
 * restringir la rejilla "Turnos por franja" a los CMs activos sin tener que pedir cada
 * usuario individualmente.
 */
export interface MiembroRota {
  id: string;
  nombre: string;
  marcas?: string[];
  /** Cargo del organigrama (p.ej. `community_manager`). "" si no esta seteado. */
  cargo?: string;
  /** Si el miembro esta disponible para cubrir turnos hoy. */
  cobertura?: boolean;
  /** Candidato a coordinador por celda (ola "coord"). */
  puede_coordinar?: boolean;
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

/**
 * Filtros de la lista de Eventos (pestaña /rota → Eventos). Todo opcional; los
 * arrays vacíos = sin filtro (igual a no enviar el campo). `q` es substring
 * case-insensitive sobre `titulo` y `contenido`. `cambiado=null` = todos.
 */
export interface FiltrosListaEventos {
  desde?: string;
  hasta?: string;
  tipo_cobertura?: TipoCoberturaEvento[];
  prioridad?: PrioridadEvento[];
  /** Tri-estado: `true` solo reprogramados, `false` solo avisados, `null|undefined` todos. */
  cambiado?: boolean | null;
  q?: string;
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

// Nota: el viejo `TurnoRota` (turno ligado a un evento + cobertura persistida) ya
// no existe. Ahora el turno es persona × día × franja (modelo nuevo, ver más abajo).
// La cobertura es DERIVADA (calculada): para cada evento, los turnos cuya
// `(fecha, franja)` lo cubren. Ver `CoberturaEvento` / `RespuestaCoberturaSemana`.

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

/** Franja de un turno LEGACY: literal mañana / tarde / descanso. Se mantiene como
 * derivada en la respuesta para retrocompat con UI vieja; codigo nuevo usa
 * `franja_id` + `franja_nombre` (modelo "franjas por semana"). */
export type FranjaTurno = "matutino" | "vespertino" | "descanso" | string;

/**
 * Una franja de la semana (modelo "franjas por semana" / Mundial). Cada lunes tiene
 * sus propias franjas (nombre libre, rangos `HH:MM`, solapes permitidos, soporte a
 * franjas que cruzan medianoche con `fin <= inicio`). Una franja con `es_descanso=true`
 * marca un turno explicito de "no laboral" (la persona no trabaja ese día); no cubre
 * ningún evento en la vista de cobertura.
 */
export interface FranjaSemana {
  id: string;
  /** Lunes ISO (AAAA-MM-DD) de la semana a la que pertenece. */
  lunes: string;
  nombre: string;
  /** "HH:MM" inclusivo. */
  inicio: string;
  /** "HH:MM" exclusivo. Si `fin <= inicio`, cruza medianoche. Para franjas de
   * descanso suele ser "00:00" (decorativo: ni cubren eventos). */
  fin: string;
  /** Orden ascendente en la rejilla (la franja Descanso usa 999 por convencion). */
  orden: number;
  /** Si `true`, esta franja NO es laboral: el turno marca "descanso explicito". */
  es_descanso: boolean;
}

/**
 * Un turno: una persona × un día × una franja. NO está ligado a un evento — un turno
 * es un horario. La cobertura se calcula DERIVADA: para cada evento, qué turnos lo
 * cubren via las franjas vivas de la semana activas a su hora (UNION si solapan).
 */
export interface TurnoRota {
  id: string;
  /** Lunes ISO de la semana. */
  semana: string;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  miembro_id: string;
  miembro_nombre: string;
  /** Modelo nuevo: id de `FranjaSemana` viva (UNIQUE por semana). */
  franja_id: string;
  /** Nombre legible de la franja (lo emite el backend para evitar joins en el cliente). */
  franja_nombre: string;
  /** Retrocompat: literal `matutino`/`vespertino`/`descanso` derivado del nombre de la
   * franja para UI vieja. Codigo nuevo lee `franja_id`/`franja_nombre`. */
  franja: FranjaTurno;
  estado: EstadoTurnoRota;
  /** Cobertura forzada que rompe la rotación de sábados (la decide Elías). */
  override: boolean;
  motivo: string;
  /** Reporte de fin de turno: qué queda pendiente para el siguiente. */
  nota_relevo: string;
  es_sabado: boolean;
}

/** La rota (horario) de una semana: turnos + rango + si está publicada. */
export interface RotaSemana {
  /** Lunes ISO. */
  lunes: string;
  inicio: string;
  fin: string;
  /** Las 7 fechas ISO (lunes->domingo) de la semana. */
  dias: string[];
  turnos: TurnoRota[];
  /** Franjas vivas de la semana (modelo "franjas por semana"). El backend siembra
   * por defecto Mañana/Tarde/Descanso si la semana esta vacia. */
  franjas: FranjaSemana[];
  /** `true` => todos los turnos aprobados (publicado al equipo). */
  aprobada: boolean;
  total: number;
  /** Mensaje de confirmación (p. ej. tras aprobar). */
  mensaje?: string;
}

/** Respuesta de `GET /api/rota/semana/{lunes}/franjas`. */
export interface RespuestaFranjasSemana {
  franjas: FranjaSemana[];
}

/** Cuerpo de `POST /api/rota/semana/{lunes}/franjas`. */
export interface CuerpoCrearFranjaSemana {
  nombre: string;
  /** "HH:MM". */
  inicio: string;
  /** "HH:MM". */
  fin: string;
  orden?: number;
  es_descanso?: boolean;
}

/** Cuerpo de `PATCH /api/rota/franjas/{id}`. `es_descanso` NO se edita despues de crear. */
export interface CuerpoActualizarFranjaSemana {
  nombre?: string;
  inicio?: string;
  fin?: string;
  orden?: number;
}

export interface CuerpoAprobarRota {
  /** Lunes (o cualquier día) de la semana a aprobar. */
  lunes: string;
}

/**
 * Cuerpo `POST /api/rota/turnos`: crea un turno (persona × día × franja_id).
 * `lunes` opcional: si falta, la semana se deriva del lunes que contiene `fecha`.
 */
export interface CuerpoCrearTurnoRota {
  /** Lunes ISO de la semana; opcional (se deriva de `fecha`). */
  lunes?: string;
  fecha: string;
  miembro_id: string;
  /** Id de la franja viva de la semana (modelo "franjas por semana"). */
  franja_id: string;
  override?: boolean;
  motivo?: string;
  nota_relevo?: string;
  estado?: EstadoTurnoRota;
}

/** Edición parcial de un turno (todo opcional; se manda lo que cambia). */
export interface CuerpoActualizarTurnoRota {
  fecha?: string;
  miembro_id?: string;
  franja_id?: string;
  override?: boolean;
  motivo?: string;
  nota_relevo?: string;
  estado?: EstadoTurnoRota;
}

export interface RespuestaTurnoRota {
  turno: TurnoRota;
}

/** "Mis turnos": la rota + los turnos del usuario actual en esa semana. */
export interface MisTurnosRota extends RotaSemana {
  miembro_id: string;
  miembro_nombre: string;
  mis_turnos: TurnoRota[];
  /** Aviso si no hay sesión (token de mantenimiento). */
  aviso?: string;
}

// --- Cobertura DERIVADA (no persistida): para cada evento, qué turnos lo cubren

/** Un turno que cubre un evento. */
export interface TurnoCobertura {
  turno_id: string;
  miembro_id: string;
  miembro_nombre: string;
  /** Id de la franja viva que aplicaba a la hora del evento. */
  franja_id: string;
  /** Nombre legible de la franja (servido por el backend). */
  franja_nombre: string;
  override: boolean;
}

/** Un evento con su cobertura derivada (lista de turnos que lo cubren). */
export interface CoberturaEvento extends EventoRota {
  cobertura: TurnoCobertura[];
}

export interface RespuestaCoberturaSemana {
  /** Lunes ISO de la semana. */
  lunes: string;
  inicio: string;
  fin: string;
  /** Rangos de franja vigentes (cabecera del cálculo legado). */
  franjas_config: ConfigFranjas;
  /** Franjas vivas de la semana (modelo "franjas por semana"). */
  franjas: FranjaSemana[];
  /** Eventos de la semana (sin `no_cubrir`) con su cobertura derivada. */
  eventos: CoberturaEvento[];
}

export interface RespuestaCoberturaEvento {
  evento: CoberturaEvento;
  franjas_config: ConfigFranjas;
  /** Franjas vivas de la semana del evento. */
  franjas: FranjaSemana[];
}

// --- Coordinador por turno (ola "coord") -----------------------------------
//
// Cada celda del calendario (combinación fecha + franja_id) puede tener UN coordinador
// asignado. Los candidatos son usuarios con `puede_coordinar=true`. La coordinación es
// INDEPENDIENTE de los turnos de CM: cambiar el turno NO toca la coordinación.

/** Coordinador asignado a una celda (fecha, franja_id) del calendario. */
export interface CoordinacionTurno {
  fecha: string;
  franja_id: string;
  coordinador_id: string;
  /** Nombre legible resuelto por el backend (puede quedar vacío si el usuario desapareció). */
  coordinador_nombre: string;
}

export interface RespuestaCoordinacionSemana {
  lunes: string;
  coordinacion: CoordinacionTurno[];
}

/** Cuerpo `PUT /api/rota/coordinacion`: UPSERT del coordinador en (fecha, franja_id). */
export interface CuerpoSetCoordinador {
  lunes: string;
  fecha: string;
  franja_id: string;
  coordinador_id: string;
}

/** Cuerpo `DELETE /api/rota/coordinacion`: borra el coordinador de la celda. */
export interface CuerpoQuitarCoordinador {
  fecha: string;
  franja_id: string;
}

/** Cuerpo `POST /api/rota/turnos/{id}/duplicar`: overrides opcionales del clon. */
export interface CuerpoDuplicarTurnoRota {
  fecha?: string;
  miembro_id?: string;
  franja_id?: string;
}

/** Cuerpo `POST /api/rota/turnos/lote`: crea N turnos en una sola petición. */
export interface CuerpoCrearTurnosLote {
  turnos: CuerpoCrearTurnoRota[];
}

export interface RespuestaCrearTurnosLote {
  creados: number;
  turnos: TurnoRota[];
}

// --- Solicitudes de cambio de turno entre compañeros (#175) ----------------
//
// Flujo: A (solicitante) crea -> B (destinatario) acepta/rechaza -> admin
// aprueba (ejecuta el swap sobre `rota_turnos_trabajo`) o rechaza. A puede
// cancelar mientras el estado no sea terminal. Estados terminales: `aplicado`,
// `rechazado`, `rechazado_admin`, `cancelado`.

/** Estados del ciclo de vida de una solicitud de cambio de turno. */
export type EstadoSwap =
  | "propuesto"
  | "aceptado"
  | "rechazado"
  | "aprobado"
  | "aplicado"
  | "rechazado_admin"
  | "cancelado";

/** Una solicitud de cambio de turno entre dos compañeros (snapshot de un swap).
 *
 * Tras el modelo "franjas por semana", los campos `franja_a`/`franja_b` ahora son
 * `franja_id` (id de la franja viva de la semana del turno), no literales. Nombre de
 * campo conservado por inercia (cambio de SEMANTICA del dato, no de columna). */
export interface SwapTurno {
  id: string;
  solicitante_id: string;
  solicitante_nombre: string;
  destinatario_id: string;
  destinatario_nombre: string;
  /** ISO (AAAA-MM-DD): día del turno del solicitante. */
  fecha_a: string;
  /** `franja_id` del turno del solicitante. */
  franja_a: string;
  /** ISO (AAAA-MM-DD): día del turno del destinatario. */
  fecha_b: string;
  /** `franja_id` del turno del destinatario. */
  franja_b: string;
  motivo: string;
  estado: EstadoSwap;
  respuesta_destinatario: string;
  respuesta_admin: string;
  /** Timestamp ISO de la creación. */
  creado: string;
  /** Timestamp ISO de la última actualización. */
  actualizado: string;
  /** Timestamp ISO cuando el destinatario aceptó/rechazó. "" si aún no. */
  decidido_destinatario: string;
  /** Timestamp ISO cuando el admin aprobó/rechazó. "" si aún no. */
  decidido_admin: string;
  /** Timestamp ISO cuando el swap se aplicó sobre el horario. "" si no. */
  aplicado: string;
}

/** Cuerpo de `POST /api/rota/swaps`: A pide un cambio con B. `franja_a`/`franja_b` son
 * `franja_id` reales (modelo "franjas por semana"). */
export interface CuerpoCrearSwap {
  destinatario_id: string;
  fecha_a: string;
  franja_a: string;
  fecha_b: string;
  franja_b: string;
  motivo?: string;
}

/** Cuerpo opcional para las transiciones (aceptar/rechazar/aprobar): nota libre. */
export interface CuerpoDecidirSwap {
  respuesta?: string;
}

/** Filtros combinables del listado `/api/rota/swaps`. */
export interface FiltrosSwaps {
  estado?: EstadoSwap;
  solicitante_id?: string;
  destinatario_id?: string;
  /** Si `true` y hay sesión, filtra a swaps donde el usuario es A o B. */
  mio?: boolean;
}

export interface RespuestaSwap {
  swap: SwapTurno;
}

export interface RespuestaSwaps {
  swaps: SwapTurno[];
}

// --- Piezas de la parrilla (#150 PARRILLA 2026.xlsx) -----------------------
//
// Cada fila del Excel de Tescu es UNA pieza (un post individual), no un evento.
// Una transmisión genera varias piezas; hay piezas SUELTAS (campañas evergreen
// sin evento, p. ej. "Álvaro Fidalgo", "MUNDIAL"). Workflow del Excel:
// material/contenido entregado → publicado + enlace.

/** Estados del ciclo de producción de una pieza. */
export type EstadoPieza = "pendiente" | "en_curso" | "listo" | "publicado";

/** Una pieza/post de la parrilla. */
export interface PiezaRota {
  id: string;
  /** FK textual a `rota_eventos.id`; "" si es pieza suelta (campaña evergreen). */
  evento_id: string;
  /** Campaña / programa libre ("Álvaro Fidalgo", "MUNDIAL", "Paty Cantú"…). */
  programa: string;
  /** Red social libre ("FB, IG, X" / "HISTORIA" / "IG, TK (REEL)" / "WEB"…). */
  red_social: string;
  /** Tipo libre ("IMAGEN" / "VIDEO" / "REEL" / "NOTA" / "FIJAR"…). */
  tipo_pieza: string;
  contenido_sugerido: string;
  /** ISO AAAA-MM-DD; "" si la pieza aún no se ha fechado. */
  dia: string;
  /** "HH:MM" o etiqueta libre ("5:15 LINK VIVO", "TBD"). */
  hora_post: string;
  estado: EstadoPieza;
  material_entregado: boolean;
  contenido_entregado: boolean;
  publicado: boolean;
  enlace: string;
  responsable_id: string;
  responsable_nombre: string;
  notas: string;
  /** Canal amplio o salida ("REDES", "WEB", "TV", "OTROS"). Texto libre. */
  salida: string;
  /** Comentarios de coordinación pre/durante (notas internas del equipo). */
  comentarios: string;
  /** Deadline interno para entregar el material; ISO AAAA-MM-DD o "". */
  fecha_entrega_material: string;
  /** `true` si la pieza es perenne (always-on, sin fecha fija). */
  always_on: boolean;
}

export interface RespuestaPiezasRota {
  piezas: PiezaRota[];
}

export interface RespuestaPiezaRota {
  pieza: PiezaRota;
}

/** Filtros combinables del listado `/api/rota/piezas`. */
export interface FiltrosPiezasRota {
  /** "" → solo piezas sueltas (sin evento); undefined → no filtra por evento. */
  evento_id?: string;
  desde?: string;
  hasta?: string;
  red?: string;
  tipo?: string;
  estado?: EstadoPieza;
  responsable_id?: string;
  programa?: string;
}

/** Cuerpo POST `/api/rota/piezas`: todos los campos opcionales (el back valida que al
 * menos uno entre `evento_id`, `programa` o `contenido_sugerido` esté relleno). */
export interface CuerpoCrearPiezaRota {
  evento_id?: string;
  programa?: string;
  red_social?: string;
  tipo_pieza?: string;
  contenido_sugerido?: string;
  dia?: string;
  hora_post?: string;
  estado?: EstadoPieza;
  material_entregado?: boolean;
  contenido_entregado?: boolean;
  publicado?: boolean;
  enlace?: string;
  responsable_id?: string;
  notas?: string;
  /** Canal amplio o salida ("REDES", "WEB", "TV"). */
  salida?: string;
  /** Comentarios de coordinación pre/durante. */
  comentarios?: string;
  /** Deadline interno para entregar el material; ISO AAAA-MM-DD. */
  fecha_entrega_material?: string;
  /** Marca la pieza como perenne (always-on, sin fecha fija). */
  always_on?: boolean;
}

/** Cuerpo PATCH `/api/rota/piezas/{id}`: cualquier subconjunto editable. */
export type CuerpoActualizarPiezaRota = CuerpoCrearPiezaRota;

/** Cuerpo opcional para `POST /api/rota/piezas/{id}/duplicar`. */
export interface CuerpoDuplicarPiezaRota {
  /** Sobrescribe el dia del clon (ISO AAAA-MM-DD). */
  dia?: string;
  /** Sobrescribe el evento del clon (debe existir; "" lo deja como pieza suelta). */
  evento_id?: string;
}

/** Cuerpo `POST /api/rota/turnos/lote/borrar` y `/api/rota/piezas/lote/borrar`. */
export interface CuerpoBorrarLoteIds {
  ids: string[];
}

/** Respuesta de los borrados en lote: cuántos se fueron y cuáles no existían. */
export interface RespuestaBorrarLote {
  borrados: number;
  no_encontrados: string[];
}

/** Cuerpo opcional `POST /api/rota/eventos/{id}/duplicar`. */
export interface CuerpoDuplicarEventoRota {
  fecha?: string;
  hora?: string;
  titulo?: string;
}

// --- Catálogo de programas (#150, PARRILLA 2026.xlsx) ----------------------
//
// Cada hoja EVERGREEN del Excel es un PROGRAMA ("Álvaro Fidalgo", "Real Oviedo",
// "MUNDIAL"...). Se cataloga con color y fechas; las piezas referencian POR NOMBRE
// (no por id) para que una pieza huérfana siga apareciendo con su texto. Renombrar
// hace cascada sobre `rota_piezas.programa` (transaccional).

/** Un programa/campaña del catálogo editorial. */
export interface ProgramaRota {
  id: string;
  nombre: string;
  descripcion: string;
  /** Color en formato libre (la UI suele usar hex `#RRGGBB`). */
  color: string;
  /** Fecha de inicio (ISO) o "" si es indefinido. */
  inicio: string;
  /** Fecha de fin (ISO) o "" si es indefinido / always-on. */
  fin: string;
  activo: boolean;
  creado: string;
  actualizado: string;
}

export interface RespuestaProgramasRota {
  programas: ProgramaRota[];
}

export interface RespuestaProgramaRota {
  programa: ProgramaRota;
}

/** Cuerpo `POST /api/rota/programas`. */
export interface CuerpoCrearProgramaRota {
  nombre: string;
  descripcion?: string;
  color?: string;
  inicio?: string;
  fin?: string;
  activo?: boolean;
}

/** Cuerpo `PATCH /api/rota/programas/{id}`: cualquier subconjunto editable. */
export interface CuerpoActualizarProgramaRota {
  nombre?: string;
  descripcion?: string;
  color?: string;
  inicio?: string;
  fin?: string;
  activo?: boolean;
}

// --- Configuración editorial de franjas (rangos horarios) ------------------

/** Rangos vigentes de las dos franjas de trabajo (los usa la cobertura derivada). */
export interface ConfigFranjas {
  matutino_inicio: string;
  matutino_fin: string;
  vespertino_inicio: string;
  vespertino_fin: string;
  actualizado?: string;
}

export interface RespuestaConfigFranjas {
  franjas: ConfigFranjas;
}

export interface CuerpoGuardarConfigFranjas {
  matutino_inicio: string;
  matutino_fin: string;
  vespertino_inicio: string;
  vespertino_fin: string;
}

/**
 * Cuerpo de `PATCH /api/rota/turnos/lote`: edita varios turnos a la vez.
 * Todos los campos del cambio son opcionales (al menos uno requerido).
 * `miembro_id=""` desasigna; el backend acepta vacío explícito.
 */
export interface CuerpoActualizarLoteTurnos {
  ids: string[];
  miembro_id?: string;
  franja_id?: string;
  /** Override de rotación de sábados; si falta y hay sábados que la requieren -> 409. */
  override?: boolean;
  motivo?: string;
  nota_relevo?: string;
}

export interface RespuestaActualizarLoteTurnos {
  actualizados: number;
  turnos: TurnoRota[];
}

/**
 * Cuerpo de `POST /api/rota/copiar-semana`: replica turnos de una semana en otra.
 * Simplificado tras ola back3: ya NO hay `alcance` (solo se copian turnos, los
 * eventos son por semana y no se duplican).
 */
export interface CuerpoCopiarSemana {
  de_lunes: string;
  a_lunes: string;
  /** Si `true`, primero borra los turnos existentes de `a_lunes`. */
  reemplazar?: boolean;
}

export interface RespuestaCopiarSemana {
  copiados: number;
}

/** Carga del equipo: cuánto trabajo lleva cada persona esta semana. */
export interface CargaMiembroRota {
  miembro_id: string;
  nombre: string;
  /** Eventos de cobertura asignados al miembro esta semana. */
  eventos: number;
  /** Días distintos en que el miembro entra a trabajar (no descanso). */
  dias_trabajados: number;
  /** True si entra a trabajar el sábado o cubre un evento del sábado. */
  sabado: boolean;
  /** Días distintos con franja "descanso". */
  descansos: number;
}

export interface RespuestaCargaRota {
  lunes: string;
  miembros: CargaMiembroRota[];
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

/** Estado de conexión de Metricool para UNA marca (sin exponer el token). */
export interface MarcaMetricool {
  marca: string;
  etiqueta: string;
  conectado: boolean;
  /** Pista no sensible del user_id (solo si está conectada). */
  user_id_pista?: string;
  /** blogId de Metricool (solo si está conectada; no es secreto). */
  blog_id?: string;
}

export interface RespuestaMetricool {
  marcas: MarcaMetricool[];
}

/** Cuerpo para descubrir las marcas (blogId) de un token de Metricool. */
export interface CuerpoPerfilesMetricool {
  user_token: string;
  user_id: string;
}

/** Una marca de Metricool descubierta vía simpleProfiles (sin token). */
export interface PerfilMetricool {
  blog_id: string;
  label: string;
}

/** Respuesta al descubrir marcas: lista de {blog_id, label}. */
export interface RespuestaPerfilesMetricool {
  marcas: PerfilMetricool[];
}

/** Cuerpo para guardar las credenciales de Metricool de una marca. */
export interface CuerpoGuardarMetricool {
  user_token: string;
  user_id: string;
  blog_id: string;
}

/** Respuesta al guardar una credencial de Metricool. */
export interface RespuestaGuardarMetricool {
  conectado: boolean;
  mensaje: string;
}

/** Respuesta de la prueba en vivo de una credencial de Metricool. */
export interface RespuestaProbarMetricool {
  ok: boolean;
  detalle: string;
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

/**
 * Cargo (función) de un usuario en el equipo. Ortogonal al rol de permisos: describe
 * QUÉ hace la persona (community manager, director, coordinador de redes...). Allowlist
 * sincronizada con `keni_consola.estados.CARGOS_USUARIO`; cadena vacía = sin
 * clasificar (usuarios legados antes de la migración). Tras la ola
 * `feat/roles-marcas` (organigrama AMX dictado por Bernardo) se añaden cargos
 * específicos por vertical/función; los valores viejos se conservan por retrocompat.
 */
export type CargoUsuario =
  // Catalogo original (retrocompat):
  | "director"
  | "gerente"
  | "coordinador"
  | "content_manager"
  | "community_manager"
  | "redactor"
  | "guionista"
  | "editorial"
  | "estrategia"
  | "fotografia"
  // Ampliacion del organigrama AMX:
  | "coordinador_redes"
  | "coordinador_youtube"
  | "gerente_podcast"
  | "creativo_vertical"
  | "editorial_youtube"
  | "coordinador_invitados"
  | "coordinador_operativo"
  | "fotografia_qa"
  | "editor_video"
  | "disenador"
  | "";

/** Etiqueta legible para cada cargo (para selects/badges/listados). */
export const ETIQUETA_CARGO: Record<Exclude<CargoUsuario, "">, string> = {
  // Catalogo original:
  director: "Director",
  gerente: "Gerente",
  coordinador: "Coordinador",
  content_manager: "Content manager",
  community_manager: "Community manager",
  redactor: "Redactor",
  guionista: "Guionista",
  editorial: "Editorial",
  estrategia: "Estrategia digital",
  fotografia: "Fotografía",
  // Ampliacion organigrama AMX:
  coordinador_redes: "Coordinador de redes",
  coordinador_youtube: "Coordinador de YouTube",
  gerente_podcast: "Gerente de podcast",
  creativo_vertical: "Creativo de vertical",
  editorial_youtube: "Editorial YouTube",
  coordinador_invitados: "Coordinador de invitados",
  coordinador_operativo: "Coordinador operativo",
  fotografia_qa: "Fotografía + QA",
  editor_video: "Editor de video",
  disenador: "Diseñador",
};

/**
 * Orden estable de los cargos para los selectores (agrupa primero los del organigrama
 * AMX y deja al final los del catalogo legado por si quedan usuarios sin migrar).
 */
export const CARGOS_ORDENADOS: Exclude<CargoUsuario, "">[] = [
  "director",
  "coordinador_redes",
  "coordinador_youtube",
  "coordinador_operativo",
  "coordinador_invitados",
  "gerente_podcast",
  "content_manager",
  "community_manager",
  "creativo_vertical",
  "editorial_youtube",
  "redactor",
  "fotografia_qa",
  "editor_video",
  "disenador",
  // Catalogo legado (al final):
  "gerente",
  "coordinador",
  "editorial",
  "guionista",
  "estrategia",
  "fotografia",
];

/** Etiqueta legible de un cargo (vacío => "Sin cargo"). */
export function etiquetaCargo(cargo: CargoUsuario): string {
  if (!cargo) return "Sin cargo";
  return ETIQUETA_CARGO[cargo];
}

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
  /** Cargo (función en el equipo). Cadena vacía si aún sin clasificar. */
  cargo?: CargoUsuario;
  /** `true` => esta persona entra en la rota de turnos (cobertura). */
  cobertura?: boolean;
  /** `true` => candidato a coordinador por celda en el calendario (ola "coord"). */
  puede_coordinar?: boolean;
  /**
   * Verticales/marcas a las que pertenece (relación N:M con `keni_shared.marcas`).
   * Una persona puede estar en varias (Yustine: claro-sports + unotv + piso-15).
   * Solo llega por `GET /api/auth/me`; el login no lo incluye.
   */
  marcas?: string[];
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
  /** Cargo (función en el equipo). Cadena vacía si aún sin clasificar. */
  cargo?: CargoUsuario;
  /** `true` => esta persona entra en la rota de turnos. */
  cobertura?: boolean;
  /** `true` => candidato a coordinador por celda en el calendario (ola "coord"). */
  puede_coordinar?: boolean;
  /**
   * Nombre HUMANO (organigrama): lo que se pinta en las tarjetas. Cadena vacía en
   * usuarios sin nombre asignado (la UI cae al `usuario`/login).
   */
  nombre?: string;
  /**
   * Id del usuario SUPERIOR al que reporta (organigrama). Cadena vacía = raíz (sin
   * superior, p.ej. el director). Define el árbol del organigrama; es ORTOGONAL a
   * `marcas` (una persona puede trabajar en una vertical y reportar a otra área).
   */
  manager_id?: string;
  /**
   * Verticales/marcas a las que pertenece (relación N:M; ids canónicos del catálogo).
   * Siempre llega (lista vacía si no tiene marcas asignadas). Ola `feat/roles-marcas`.
   */
  marcas?: string[];
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
  /** Nombre humano opcional (organigrama). Si se omite, queda vacío. */
  nombre?: string;
}

/**
 * Cuerpo de `PATCH /api/usuarios/{id}`: cambiar rol, resetear contraseña, o editar
 * cargo/cobertura/marcas del organigrama AMX. Todos opcionales (se manda solo lo que
 * cambia). `marcas` reemplaza el conjunto entero (lista vacía = desasignar todas).
 */
export interface CuerpoActualizarUsuario {
  rol?: RolUsuario;
  password?: string;
  /** Cargo del catálogo (`CARGOS_USUARIO`); "" desclasifica. */
  cargo?: CargoUsuario;
  /** Cobertura: entra o no en la rota de turnos. */
  cobertura?: boolean;
  /** Candidato a coordinador por celda en el calendario (ola "coord"). */
  puede_coordinar?: boolean;
  /** Nombre humano (organigrama); "" lo limpia. */
  nombre?: string;
  /**
   * Id del superior al que reporta (organigrama); "" desliga (vuelve a raíz). Debe
   * apuntar a un usuario existente, distinto de uno mismo y sin cerrar ciclos.
   */
  manager_id?: string;
  /** Lista de ids canónicos del catálogo de marcas; reemplaza el conjunto. */
  marcas?: string[];
}

// --- Catálogo de apps (ADR 0005 · GET /api/catalogo) ------------------------
// El sidebar se hidrata de aquí: el backend declara las apps ACTIVAS (según flags)
// y sus entradas de navegación. El icono llega como STRING (nombre de icono lucide)
// y el frontend lo resuelve a un componente vía un mapa en `navegacion.ts`.

/** Una entrada de navegación del sidebar tal como llega del catálogo. */
export interface ItemNavCatalogo {
  ruta: string;
  etiqueta: string;
  /** Nombre del icono lucide (p. ej. "Sparkles"); se mapea a un componente. */
  icono: string;
  descripcion: string;
}

/** Un bloque del sidebar (sin encabezado si `etiqueta` es ""). */
export interface GrupoNavCatalogo {
  etiqueta: string;
  items: ItemNavCatalogo[];
}

/** Una entrada de nav de una app, tal como llega anidada en `AppCatalogo.nav`. */
export interface ItemNavApp {
  ruta: string;
  etiqueta: string;
  icono: string;
  descripcion: string;
  grupo: string;
  grupo_orden: number;
  orden: number;
}

/** Una app de catálogo activa (sin el shell). */
export interface AppCatalogo {
  id: string;
  etiqueta: string;
  icono: string;
  /** Frase corta para la tarjeta del launcher (cajón de apps). */
  descripcion: string;
  permisos: string[];
  rutas_frontend: string[];
  /**
   * Entradas de nav de ESTA app (ordenadas). El launcher deriva de aquí la ruta
   * primaria (primer item) y el sidebar con scope muestra solo estos items.
   */
  nav: ItemNavApp[];
}

/** Respuesta de `GET /api/catalogo`: apps activas + navegación data-driven. */
export interface RespuestaCatalogo {
  apps: AppCatalogo[];
  navegacion: GrupoNavCatalogo[];
}
