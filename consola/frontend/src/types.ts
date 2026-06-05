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
  RedMetrica,
  RedCobertura,
  MarcaCobertura,
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
  PiezaRendimiento,
  PiezasRendimiento,
  PiezaListado,
  PiezasListado,
  PuntoHistorico,
  VelocidadPieza,
  HistoricoPieza,
  PuntoSeguidores,
  SerieSeguidores,
  CeldaDesglose,
  DesgloseInteracciones,
  CeldaCrosstab,
  Crosstab,
  PostEstrella,
  ItemCorrelacion,
  CorrelacionSeguidores,
  Paginacion,
  MetricasRun,
  Publicacion,
  RespuestaPublicaciones,
  RespuestaPublicacion,
  RespuestaColaAprobacion,
  ActualComercial,
  SnapshotComercial,
  PostSeleccionableComercial,
  RespuestaPostsComercial,
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
  ResultadoEstado,
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

// --- Actividad IA unificada (#actividad) ---
//
// Sección AD-HOC (a mano): la página /actividad consume el contrato unificado que
// expone el backend, que fusiona en un solo feed las generaciones de IA en segundo
// plano (`fuente: "generacion"`) y los runs de agentes (`fuente: "run"`). NO se genera
// desde `types.gen.ts`; el backend de esta rama lo construye como dict ad-hoc.

/** Origen de un ítem de actividad: una generación en segundo plano o un run de agente. */
export type FuenteActividad = "generacion" | "run";

/** Métricas (token/coste/duración/turnos) de un ítem de actividad; cualquiera puede faltar. */
export interface MetricasActividad {
  tokens: number | null;
  coste_usd: number | null;
  duration_ms: number | null;
  num_turns: number | null;
}

/** Un ítem del feed unificado de Actividad IA. */
export interface ActividadItem {
  id: string;
  fuente: FuenteActividad;
  tipo: string;
  etiqueta: string;
  marca: string;
  estado: string;
  fecha: string;
  metricas: MetricasActividad;
  /**
   * Ruta del SPA al resultado (solo generaciones COMPLETADAS con página de resultado:
   * copy/rss → tablero, imagen → estudio, verificación/qa → su hoja). `null` si no aplica
   * (en curso, error, tipo sin página, o runs). No es deep-link por id: la página resuelve
   * su propio estado vacío/404.
   */
  resultado_url: string | null;
}

/** Respuesta paginada del feed de Actividad IA (`GET /api/actividad`). */
export interface RespuestaActividad {
  items: ActividadItem[];
  total: number;
}

/** Totales globales del periodo disponible. */
export interface ActividadTotal {
  items: number;
  coste_usd: number;
  tokens: number;
}

/** Desglose de actividad por tipo de trabajo. */
export interface ActividadPorTipo {
  tipo: string;
  items: number;
  coste_usd: number;
  tokens: number;
}

/** Desglose de actividad por día (`YYYY-MM-DD`). */
export interface ActividadPorDia {
  dia: string;
  items: number;
  coste_usd: number;
}

/** Agregados de Actividad IA (`GET /api/actividad/agregados`): totales + desgloses. */
export interface ActividadAgregados {
  total: ActividadTotal;
  por_tipo: ActividadPorTipo[];
  por_dia: ActividadPorDia[];
}

// --- Pipelines (vista estilo GitLab del pipeline de contenido CI/CD) ---

/** Una etapa de una run del pipeline (CI/CD/QA/Aprobación). */
export interface PipelineEtapa {
  clave: string;
  nombre: string;
  estado: string;
  detalle: string;
  ts: string;
}

/** Una pieza por plataforma dentro de una run del pipeline.
 *  Los campos de detalle (copy, observaciones, traza de revisión) solo vienen del endpoint
 *  de detalle (`/api/pipelines/{id}`); en la lista son `undefined`. */
export interface PipelinePieza {
  red: string;
  red_nombre: string;
  estado: string;
  veredicto: string;
  falta_copy: boolean;
  falta_imagen: boolean;
  copy?: string;
  copy_in?: string;
  imagen_url?: string;
  observaciones?: string[];
  revisor_nombre?: string;
  revisado_en?: string;
  enviado_a_revision_en?: string;
  creado?: string;
}

/** Un hallazgo estructurado de la criba de la fuente (lo que está mal en la nota de origen). */
export interface PipelineHallazgo {
  tipo?: string;
  gravedad?: string;
  fragmento?: string;
  explicacion?: string;
  sugerencia?: string;
  no_verificable?: boolean;
}

/** Veredicto ESTRUCTURADO de la criba de la fuente (rediseño QPC, pre-copy):
 *  `no_verificado` (⚠️ apta, no verificada a fondo) o `problema` (❗ algo de peso: sin copy). */
export interface PipelineQaFuente {
  veredicto: string;
  no_verificado: boolean;
  problema: boolean;
  copy_omitido: boolean;
  resumen: string;
  hallazgos: PipelineHallazgo[];
}

/** Una RUN del pipeline: el recorrido de una pieza por sus etapas. */
export interface Pipeline {
  id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  origen?: string;
  descripcion?: string;
  creado: string;
  actualizado: string;
  estado_global: "ok" | "en_curso" | "pendiente" | "revisar" | "fallo";
  etapas: PipelineEtapa[];
  /** Criba de la fuente (⚠️/❗ + hallazgos). Siempre presente desde el back. */
  qa_fuente?: PipelineQaFuente;
  piezas: PipelinePieza[];
}

/** Un evento del log de actividad de una run (etapa registrada). */
export interface PipelineActividad {
  etapa: string;
  etiqueta: string;
  estado: string;
  fecha: string;
}

export interface RespuestaPipelines {
  pipelines: Pipeline[];
}

/** El STREAM (proceso de pensamiento de `claude -p`) de la generación de una etapa.
 *  Lo expone el detalle del pipeline por código de etapa (CI/CD/QA): `salida` es el texto
 *  del agente en vivo; `fase`/`estado` dicen en qué punto va (razonando/escribiendo/...). */
export interface PipelineGeneracion {
  id: string;
  estado: string;
  fase: string;
  salida: string;
  metricas: MetricasRun | null;
}

export interface RespuestaPipelineDetalle {
  pipeline: Pipeline;
  actividad: PipelineActividad[];
  /** Stream del agente por código de etapa ("CI"/"CD"/"QA"). Ausente/{} si no hay. */
  generaciones_por_etapa?: Record<string, PipelineGeneracion>;
}

// --- Generación de copy (resultado compartido) ---

/** Veredicto editorial de una pieza/generación. "" = sin veredicto.
 *  `no_verificado` (rediseño QPC): la pieza nació de una fuente que pasó la criba PERMISIVA
 *  pre-copy sin verificarse a fondo (lleva el aviso ⚠️ hasta que un humano la revise). */
export type Veredicto = "listo" | "revisar" | "no_publicar" | "no_verificado" | "";

/** Una pieza generada para una red concreta. */
export interface PiezaGenerada {
  red: string;
  contenido: string;
  caracteres: number;
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
  /**
   * Imágenes producidas por el estudio de imagen, ya importadas al
   * almacén de media para previsualizarlas. Cada una trae su `nombre` y la `url`
   * (`/api/media/...`). Vacío o ausente si no se generaron imágenes.
   */
  imagenes?: ImagenGenerada[];
  // verificacion (workflow propio: datar un video)
  verificacion?: ReporteVerificacion;
  // qa-editorial (workflow propio: revisar el copy ya escrito por el community)
  informe?: InformeQaEditorial;
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
  /** `true` si el prompt `qa-editorial` está instalado en este equipo. */
  prompt_disponible: boolean;
}

/** Cuerpo de POST /api/qa-editorial/revisar: el copy a revisar + su marca/plataforma. */
export interface CuerpoRevisarQaEditorial {
  marca: string;
  texto: string;
  /** Plataforma del copy (para validar su límite). Vacío = no validar ninguno. */
  plataforma?: string;
  /** Fuente/nota contra la que comprobar datos. Vacío = datos no verificables. */
  contexto?: string;
  /**
   * Pieza concreta (`contenido_plataforma.id`) sobre la que se revisa el copy. Si se indica,
   * el veredicto se ATA a la pieza y resuelve su nivel automático "QA Editorial" en la cadena
   * de aprobación (aprobador automático). Vacío = revisión suelta, no atada a ninguna pieza.
   */
  plataforma_id?: string;
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
  contenido_id: string;
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
  contenido_id: string;
  generacion_id: string;
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
  /** `true` si el prompt `termometro-mundial` está instalado en este equipo. */
  prompt_disponible: boolean;
  marcas: MarcaDisponible[];
  regiones_sugeridas: string[];
  /**
   * Último termómetro generado (o `null`): el resultado PERSISTENTE de la página, leído del
   * historial. Sobrevive a navegaciones y recargas; un termómetro nuevo lo reemplaza y
   * borrarlo del historial lo elimina.
   */
  ultimo: UltimoTermometro | null;
}

/** Último termómetro generado, para repintar el resultado al entrar en la página. */
export interface UltimoTermometro {
  historial_id: string;
  /** Documento Markdown completo de la galería. */
  documento: string;
  titulo: string;
  fecha: string;
  marca: string;
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
  /** Número de slides (5–8) como texto; vacío = el de la config/prompt. */
  numero?: string;
  /** Regiones a cubrir (CSV); vacío = reparto por defecto. */
  regiones?: string;
  /** Fecha de la portada (YYYY-MM-DD); vacío = hoy. */
  fecha?: string;
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
  /** Id de la `fuentes_rss` de la que se sembró (vacío si nació en el hub). */
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

/** Tipo de aportación manual al pipeline desde Fuentes. */
export type TipoAportacion = "idea" | "enlace" | "interna";

/**
 * Cuerpo de `POST /api/fuentes/aportar`: una aportación MANUAL que produce un item REAL
 * en el tablero (Pendientes) con su `origen`. `texto` para idea/interna; `url` para enlace.
 */
export interface CuerpoAportarFuente {
  tipo: TipoAportacion;
  marca?: string;
  redes?: string[];
  /** Lanza copy en segundo plano (def true en backend). */
  generar?: boolean;
  /** Texto libre (idea / contenido interno). */
  texto?: string;
  /** URL pegada (tipo enlace). */
  url?: string;
  titulo?: string;
}

/** Respuesta de `POST /api/fuentes/aportar`. */
export interface RespuestaAportarFuente {
  contenido: Contenido;
  /** `true` si se lanzó la generación de copy en segundo plano. */
  copy_en_proceso: boolean;
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
  /** `true` si ya se propuso a la biblioteca editorial. */
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

export interface RespuestaSembrarAlgoritmos {
  creadas: FuenteAlgoritmo[];
  total: number;
}

export interface RespuestaFuenteAlgoritmo {
  fuente: FuenteAlgoritmo;
}

/** Respuesta de POST /api/algoritmos/{id}/biblioteca: borrador para la ficha. */
export interface RespuestaABibliotecaAlgoritmo {
  noticia: NoticiaAlgoritmo;
  /** Bloque markdown listo para pegar/confirmar en la Biblioteca. */
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

/** Estado de una sugerencia editorial. */
export type EstadoSugerenciaEditorial = "nueva" | "aplicada" | "descartada";

/** Una propuesta de cambio editorial/límite generada por el digest diario. */
export interface SugerenciaEditorial {
  id: string;
  plataforma: string;
  plataforma_nombre: string;
  /** "editorial" (cambio a la ficha) o "limite" (cambio a los límites de caracteres). */
  tipo: string;
  titulo: string;
  /** Markdown: qué cambiar y por qué, con referencia a las noticias. */
  detalle: string;
  /** Doc de biblioteca destino (p. ej. "editorial/plataformas/instagram"). */
  ficha_id: string;
  /** Ids de las noticias que motivaron la sugerencia. */
  noticia_ids: string[];
  estado: EstadoSugerenciaEditorial;
  creado: string;
}

/** Respuesta de GET /api/algoritmos/sugerencias. */
export interface RespuestaSugerenciasAlgoritmo {
  sugerencias: SugerenciaEditorial[];
  total: number;
  /** Nº de sugerencias en estado "nueva" (para el aviso del panel). */
  nuevas: number;
}

/** Respuesta de aplicar una sugerencia. */
export interface RespuestaAplicarSugerencia {
  sugerencia: SugerenciaEditorial;
  /** Doc de biblioteca afectado (vacío para sugerencias de límite). */
  ficha_id: string;
  /** Nota (p. ej. para límites, que son cambio de código). */
  nota: string;
}

export interface RespuestaDescartarSugerencia {
  sugerencia: SugerenciaEditorial | null;
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
  prompt: string;
  prompt_nombre: string;
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
  prompt: string;
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
 * (`POST /api/prompts/historial/{id}/guardar`). Si la entrada no tiene piezas,
 * hay que indicar `red`; si las tiene, `redes` permite acotar cuáles guardar.
 */
export interface CuerpoGuardarHistorial {
  titulo?: string;
  /** Subconjunto de redes a guardar (cuando la entrada tiene piezas). */
  redes?: string[];
  /** Red obligatoria cuando la entrada no tiene piezas. */
  red?: string;
}

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
  es_green: boolean;
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
  es_green?: boolean;
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
  es_green?: boolean;
}

export interface RespuestaEtiqueta {
  etiqueta: Etiqueta;
}

// --- Green: ideas de contenido evergreen (perenne) ---------------------------

/** Estado de una idea Green: propuesta → aprobada / descartada. */
export type EstadoIdeaGreen = "propuesta" | "aprobada" | "descartada" | string;

/** Una idea de contenido evergreen (banco de ideas perennes por marca). */
export interface IdeaGreen {
  id: string;
  marca: string;
  titulo: string;
  descripcion: string;
  estado: EstadoIdeaGreen;
  /** De dónde salió la idea (p. ej. "ia" cuando la propuso el asistente, "manual"). */
  origen: string;
  /** Id del contenido generado a partir de la idea (vacío si aún no se generó). */
  contenido_id: string;
  creado: string;
}

export interface RespuestaIdeasGreen {
  ideas: IdeaGreen[];
  estados: EstadoIdeaGreen[];
  marcas: { id: string; nombre: string }[];
}

export interface CuerpoCrearIdeaGreen {
  marca: string;
  titulo: string;
  descripcion?: string;
}

export interface CuerpoActualizarIdeaGreen {
  estado?: EstadoIdeaGreen;
  titulo?: string;
  descripcion?: string;
}

export interface CuerpoProponerGreen {
  marca: string;
  contexto?: string;
}

export interface CuerpoGenerarIdeaGreen {
  redes?: string[];
}

export interface RespuestaIdeaGreen {
  idea: IdeaGreen;
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
 *   - `galeria`: se sube/elige de la biblioteca de medios.
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
}

export interface RespuestaContenidoItem {
  contenido: Contenido;
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

// --- Webhooks salientes + eventos internos del tablero ---

/** Tipos de evento interno que un webhook puede escuchar (espejo de `dominio/eventos.TIPOS_EVENTO`). */
export type TipoEventoInterno =
  | "pieza.aprobada"
  | "pieza.publicada"
  | "contenido.vencido"
  // Fase 3 auto-operativa: alertas proactivas del barrido `alertas_rendimiento`.
  | "pieza.reciclaje_sugerida"
  | "pieza.bajo_rendimiento";

/** Forma del payload del POST saliente: `generico` (evento crudo) | `slack` (`{text}`). */
export type FormatoWebhook = "generico" | "slack";

/** Una suscripción de webhook. El `secreto` NUNCA se expone: solo `tiene_secreto`. */
export interface Webhook {
  id: string;
  nombre: string;
  url: string;
  /** Eventos escuchados; lista vacía = escucha TODOS. */
  eventos: TipoEventoInterno[];
  formato: FormatoWebhook;
  /** True si tiene secreto (firma HMAC); el valor del secreto no se devuelve. */
  tiene_secreto: boolean;
  activo: boolean;
  /** Resultado de la última entrega (p.ej. "ok: HTTP 200" / "error: timeout"). */
  ultimo_estado: string;
  ultimo_en: string;
  autor_id: string;
  autor_nombre: string;
  creado: string;
  actualizado: string;
}

/** Un evento interno ya emitido (bitácora). */
export interface EventoInterno {
  id: string;
  tipo: TipoEventoInterno;
  contenido_id: string;
  plataforma_id: string;
  payload: Record<string, unknown>;
  creado: string;
}

export interface CatalogoWebhooks {
  eventos: TipoEventoInterno[];
  formatos: FormatoWebhook[];
}

export interface RespuestaWebhooks {
  webhooks: Webhook[];
  catalogo: CatalogoWebhooks;
  eventos_recientes: EventoInterno[];
}

export interface RespuestaWebhook {
  webhook: Webhook;
}

export interface CuerpoCrearWebhook {
  nombre?: string;
  url: string;
  eventos?: TipoEventoInterno[];
  formato?: FormatoWebhook;
  secreto?: string;
  activo?: boolean;
}

export interface CuerpoActualizarWebhook {
  nombre?: string;
  url?: string;
  eventos?: TipoEventoInterno[];
  formato?: FormatoWebhook;
  secreto?: string;
  activo?: boolean;
}

export interface RespuestaProbarWebhook {
  ok: boolean;
  estado: string;
}

// --- Ola COLABORACIÓN: comentarios internos + versiones de copy + aprobación
//     multinivel sobre el tablero de contenido (inspirado en Planable). ---

/** Un comentario del hilo de discusión de una pieza. `plataforma_id` vacío = comentario
 *  del item entero; con valor = atado a una red concreta. `resuelto` marca el hilo cerrado. */
export interface ComentarioContenido {
  id: string;
  contenido_id: string;
  plataforma_id: string;
  autor_id: string;
  autor_nombre: string;
  texto: string;
  resuelto: boolean;
  creado: string;
  actualizado: string;
  /** Ids de usuarios mencionados (@) en el comentario. */
  menciones: string[];
}

export interface RespuestaComentarios {
  comentarios: ComentarioContenido[];
  total: number;
}

export interface RespuestaComentario {
  comentario: ComentarioContenido;
}

// --- Notificaciones in-app (el "cajón" de la campana) ---

/** Tipo de notificación; clasifica el evento que la originó. */
export type TipoNotificacion =
  | "mencion"
  | "comentario"
  | "aprobacion"
  | "rechazo"
  | "publicacion";

/** Una notificación del buzón de un usuario sobre una pieza. */
export interface Notificacion {
  id: string;
  usuario_id: string;
  marca_id: string;
  tipo: TipoNotificacion;
  contenido_id: string;
  plataforma_id: string;
  actor_id: string;
  actor_nombre: string;
  /** Frase ya armada para la UI (p. ej. "Diana te mencionó en «…»"). */
  resumen: string;
  enlace: string;
  leida: boolean;
  creada: string;
}

export interface RespuestaNotificaciones {
  notificaciones: Notificacion[];
  no_leidas: number;
  total: number;
}

export interface RespuestaContadorNotificaciones {
  no_leidas: number;
}

/** Candidato para el autocompletado de menciones (@) en comentarios. */
export interface MencionCandidato {
  id: string;
  nombre: string;
  usuario: string;
}

export interface RespuestaMencionesCandidatos {
  usuarios: MencionCandidato[];
}

/** Un snapshot inmutable del copy de una plataforma (historial de versiones). `version`
 *  es el contador incremental 1-based por plataforma. */
export interface CopyVersion {
  id: string;
  plataforma_id: string;
  contenido_id: string;
  version: number;
  copy: string;
  autor_id: string;
  autor_nombre: string;
  nota: string;
  creado: string;
}

export interface RespuestaCopyVersiones {
  versiones: CopyVersion[];
  total: number;
  copy_actual: string;
}

/** Respuesta al guardar/revertir copy: la plataforma actualizada (+ la versión creada). */
export interface RespuestaCopyGuardado {
  plataforma: ContenidoPlataforma;
  version: CopyVersion | null;
}

export type DecisionAprobacion = "pendiente" | "aprobado" | "rechazado";

/** Un nivel de la cadena de aprobación multinivel de una pieza, con su decisión y traza. */
export interface NivelAprobacion {
  id: string;
  plataforma_id: string;
  contenido_id: string;
  nivel: number;
  etiqueta: string;
  decision: DecisionAprobacion;
  decisor_id: string;
  decisor_nombre: string;
  comentario: string;
  creado: string;
  decidido_en: string;
  /** Cargo del organigrama exigido para decidir este nivel ("" = sin requisito). Item C. */
  cargo_requerido: string;
}

/** Estado GLOBAL de una cadena: sin_cadena | pendiente | aprobado | rechazado. */
export type EstadoCadenaAprobacion =
  | "sin_cadena"
  | "pendiente"
  | "aprobado"
  | "rechazado";

export interface CadenaAprobacion {
  niveles: NivelAprobacion[];
  estado: EstadoCadenaAprobacion;
  /** Id del nivel que toca decidir ("" si la cadena no espera decisión). */
  nivel_actual: string;
  /** Niveles ya aprobados (gate A: cuántas firmas lleva). */
  aprobados: number;
  /** Mínimo de aprobaciones exigido para programar (gate A; 0 = gate desactivado). */
  minimo_aprobaciones: number;
  /** Comentarios sin resolver que bloquean publicar (gate B). */
  comentarios_sin_resolver: number;
}

/** Respuesta de decidir un nivel: el nivel actualizado + el estado global y la cadena. */
export interface RespuestaDecisionAprobacion {
  nivel: NivelAprobacion;
  estado: EstadoCadenaAprobacion;
  niveles: NivelAprobacion[];
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

/** Cuerpo `POST /api/rota/turnos/lote/borrar`. */
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

// --- Importar documento a la parrilla (turnos + eventos) ---
//
// Flujo: el usuario sube un documento (PDF/imagen/docx/xlsx/txt) + la semana destino;
// un `claude -p` lo analiza en 2º plano y produce una PROPUESTA: un diff de operaciones
// que, al aceptarse, se mergea sobre el calendario real. La propuesta se SONDEA hasta que
// `estado != "generando"`; en estado `pendiente` se previsualiza superpuesta al calendario.

/** Estado del ciclo de vida de una propuesta de import. */
export type EstadoPropuestaParrilla =
  | "generando"
  | "pendiente"
  | "aplicada"
  | "descartada"
  | "error";

/** Crear un evento del calendario (verde = nuevo). */
export interface OperacionCrearEvento {
  tipo: "crear_evento";
  /** `true` si el server detectó un conflicto con el calendario actual (rojo). */
  conflicto: boolean;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  hora: string;
  titulo: string;
  contenido?: string;
  nota?: string;
  tipo_cobertura?: TipoCoberturaEvento;
  prioridad?: PrioridadEvento;
}

/** Crear un turno (persona × día × franja) (verde = nuevo). */
export interface OperacionCrearTurno {
  tipo: "crear_turno";
  conflicto: boolean;
  /** ISO (AAAA-MM-DD). */
  fecha: string;
  /**
   * NOMBRE de la franja (p. ej. "Mañana"/"Tarde"/"Descanso"), no su id: una propuesta
   * abarca muchas semanas y los `franja_id` son por-semana, así que el modelo emite el
   * nombre y la previsualización lo casa contra las filas-plantilla (normalizado).
   */
  franja: string;
  miembro_id: string;
  miembro_nombre: string;
  nota_relevo?: string;
  motivo?: string;
}

/** Forma de los valores `actual` de un `modificar_turno` (el "antes" de la fila).
 *  `franja` es el NOMBRE de la franja (no su id), por la misma razón multi-semana. */
export interface ActualTurnoPropuesta {
  fecha?: string;
  franja?: string;
  miembro_id?: string;
  miembro_nombre?: string;
  [k: string]: unknown;
}

/** Modificar un turno existente (ámbar = cambio). Trae los valores actuales de la fila. */
export interface OperacionModificarTurno {
  tipo: "modificar_turno";
  conflicto: boolean;
  turno_id: string;
  /** Campos a cambiar (parcial). */
  cambios: Partial<CuerpoActualizarTurnoRota> & Record<string, unknown>;
  /** Valores actuales de la fila referenciada (para mostrar el "antes").
   *  `franja` es el NOMBRE de la franja, no `franja_id` (placement multi-semana). */
  actual: ActualTurnoPropuesta;
}

/** Una operación propuesta del diff. El `tipo` discrimina la forma. */
export type OperacionPropuesta =
  | OperacionCrearEvento
  | OperacionCrearTurno
  | OperacionModificarTurno;

/** Una propuesta de import: el diff staged que produjo el `claude -p`. */
export interface PropuestaParrilla {
  id: string;
  estado: EstadoPropuestaParrilla;
  /** Lunes ISO de la semana destino. */
  semana: string;
  /** Resumen legible de lo que propone (lo emite el modelo). */
  resumen: string;
  /** Mensaje de error legible cuando `estado === "error"`. */
  error: string;
  operaciones: OperacionPropuesta[];
  /**
   * Rango que abarca la propuesta (puede cubrir muchas semanas, hasta un año). `semanas`
   * son los lunes ISO con cambios, ordenados ascendente; `desde`/`hasta` son ISO de la
   * primera/última fecha con operaciones; `total` es el nº de operaciones. Opcional:
   * propuestas legadas (de una sola semana) pueden no traerlo. */
  rango?: { desde: string; hasta: string; semanas: string[]; total: number };
  /** Id de la generación `claude -p` que la produjo (opcional). */
  gen_id?: string;
  /** Nombre del objeto en el almacén de media (uuid+ext; NO es el nombre original). Opcional. */
  doc_nombre?: string;
  /** Extensión/tipo del documento subido (p.ej. "pdf"). Opcional. */
  doc_tipo?: string;
  /** ISO de creación (para ordenar la lista de pendientes). Opcional. */
  creado?: string;
}

/** Respuesta de `POST /api/parrilla/importar`. */
export interface RespuestaImportarParrilla {
  propuesta_id: string;
  gen_id: string;
}

/** Respuesta de `GET /api/parrilla/propuestas`. */
export interface RespuestaPropuestasParrilla {
  propuestas: PropuestaParrilla[];
}

/**
 * Payload de un 409 al aplicar: el calendario cambió desde que se generó la propuesta.
 * Best-effort: solo nos importa mostrar el mensaje y que el usuario reabra/refresque.
 */
export interface ConflictoAplicarParrilla {
  /** El backend manda la clave `error`; `mensaje` se mantiene por compatibilidad. */
  mensaje?: string;
  error?: string;
  /** Operaciones que chocan con una celda ocupada / turno desaparecido. */
  conflictos?: OperacionPropuesta[];
  /** Errores de re-validación contra el estado vivo (índice + motivo). */
  errores?: { indice: number; error: string }[];
}

// --- Metricas ---
//
// Los tipos de métricas (`RangoMetrica`, `OpcionesMetricas`, `TotalMetricas`,
// `CuentaMetrica`, `ReporteMetricas`, `ComparativaMetrica`, `ComparativaPorMarca`,
// `CompararMetricas`) se GENERAN desde el backend y se re-exportan arriba. Ver #101.
// NOTA: `fuente` ahora es REQUERIDO (el backend siempre lo emite, cae a "muestra").

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

/** Una línea editorial = etiqueta de clase `vertical` (la LÍNEA de contenido de una marca). */
export interface LineaEditorialOpcion {
  id: string;
  nombre: string;
  /** Marca dueña; "" = línea global (visible en todas las marcas). */
  marca: string;
}

export interface OpcionesPublicaciones {
  redes: RedPublicacion[];
  estados: EstadoOpcion[];
  marcas: MarcaDisponible[];
  /** Líneas editoriales (etiquetas verticales) para el filtro de Lista/Calendario/Feed. */
  lineas: LineaEditorialOpcion[];
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
  /** Texto que va DENTRO de la imagen (copy-in), distinto del contenido. */
  copy_in?: string;
  estado?: EstadoPublicacion;
  fecha_programada?: string | null;
  /** Marca/desmarca la publicación como perenne. */
  evergreen?: boolean;
  /** Nombre del archivo de imagen adjunto (`""` para quitarla). */
  imagen?: string;
  /** Media id de la FOTO CRUDA de fondo (separada de la placa compuesta `imagen`). */
  foto?: string;
  /** "Quitar plantilla": publicar solo la foto, sin la placa de marca encima. */
  placa_oculta?: boolean;
  /** Plantilla del estudio elegida ("" para volver a la placa de marca por defecto). */
  plantilla_diseno_id?: string;
  /** Reencuadre manual de la foto dentro del marco 4:5 (JSON `{"foco":[x,y],"zoom":z}`; "" = sin reencuadre). */
  foto_encuadre?: string;
  /** COLLAGE: JSON array `[{objeto,foco,zoom}, …]`, una foto por hueco. "" = sin collage. */
  fotos?: string;
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

/** Motivo por el que el archivo sugiere retomar una pieza (heurística explicable).
 *
 * `rendimiento`: la pieza YA rindió bien (engagement real medido en Metricool) → repostear.
 * Es la señal más fuerte (datos reales, no solo contexto). El resto son contextuales.
 */
export type MotivoReciclaje = "rendimiento" | "efemeride" | "perenne" | "recurrente";

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
  /** Rendimiento real (Metricool) cuando el motivo es `rendimiento`; `null` si no aplica. */
  rendimiento: MetricaPieza | null;
}

/** Parámetros (días/umbral) de la heurística, para que la UI los pueda mostrar. */
export interface ParametrosReciclaje {
  ventana_efemeride_dias: number;
  edad_minima_perenne_dias: number;
  edad_minima_antiguedad_dias: number;
  /** Engagement (%) mínimo para considerar que una pieza "rindió bien". */
  umbral_engagement_rendimiento: number;
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
 * Respuesta de generar copy desde un item (auto-guarda como Publicaciones).
 * Misma forma que ejecutar un prompt.
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

// --- Estudio de imagen ---

/** Una imagen del almacén de media (objeto + URL), tal como vive en el lienzo del Estudio. */
export interface ImagenActiva {
  /** Nombre del objeto de media (lo que se manda a los endpoints y se persiste en la pieza). */
  id: string;
  /** URL para servir la imagen (`/api/media/...` o nombre que `urlMedia` resuelve). */
  url: string;
  /**
   * Foto BASE de la que se compuso esta imagen al "Aplicar marca". Permite REAPLICAR la
   * plantilla siempre desde la foto original (no apila ni duplica el logo) y "quitar marca"
   * volviendo a la base. Indefinido en fotos crudas (subidas/generadas) y ediciones.
   */
  origen?: string;
}

/** Formatos de red soportados por el Estudio (vertical 9:16, feed 4:5, cuadrado 1:1, horizontal 16:9). */
export type FormatoImagen = "vertical" | "feed" | "cuadrado" | "horizontal";

/** Operaciones deterministas de edición (sin coste). */
export type OpEditarImagen =
  | "recortar"
  | "redimensionar"
  | "comprimir"
  | "extender"
  | "placa";

/** Cuerpo de `POST /api/imagenes/generar`: genera N variantes (IA). */
export interface CuerpoImagenesGenerar {
  prompt: string;
  marca?: string;
  formato?: FormatoImagen;
  /** Número de variantes a generar (1..4, def. 2). */
  variantes?: number;
  prompt_id?: string;
}

/** Cuerpo de `POST /api/imagenes/editar`: operación determinista sobre un objeto de media. */
export interface CuerpoImagenesEditar {
  /** Nombre del objeto de media sobre el que operar. */
  imagen: string;
  op: OpEditarImagen;
  formato?: FormatoImagen;
  /** redimensionar: lado máximo en px. */
  max?: number;
  /** comprimir: peso máximo en MB (def. 2). */
  peso_max_mb?: number;
  /** comprimir: formato de archivo de salida. */
  formato_archivo?: "jpg" | "webp";
  /** extender: método de relleno. */
  metodo?: "borde" | "color";
  /** extender: fuerza el relleno aunque el formato ya coincida. */
  forzar?: boolean;
  /** placa: texto de la placa. */
  texto?: string;
  /** placa: marca visual (solo `unotv` | `claro-sports`). */
  marca?: string;
  /** placa: crédito/fuente de la cita. */
  fuente_cita?: string;
}

/** Cuerpo de `POST /api/imagenes/expandir`: outpainting generativo (IA, con coste). */
export interface CuerpoImagenesExpandir {
  imagen: string;
  formato?: FormatoImagen;
  marca?: string;
  /** Fidelidad al sujeto original (0..1). */
  strength?: number;
  lado?: "auto" | "arriba" | "abajo" | "izquierda" | "derecha";
}

/**
 * Cuerpo de `POST /api/imagenes/retocar`: retoque GENERATIVO por instrucción (IA, con coste).
 * Reinterpreta toda la imagen según la indicación ("oscurece el cielo"); distinto de expandir
 * (outpainting fiel al sujeto).
 */
export interface CuerpoImagenesRetocar {
  imagen: string;
  /** Qué cambiar, en lenguaje natural. */
  instruccion: string;
  /** Cuánto cambia respecto al original (0..1; alto = cambia más). */
  strength?: number;
}

/** Cuerpo de `POST /api/imagenes/revisar`: revisión legal/editorial (gate humano, no bloquea). */
export interface CuerpoImagenesRevisar {
  /** Nombre del objeto de media a revisar. */
  imagen: string;
  marca?: string;
}

/** Posición del logo dentro del lienzo al estampar la plantilla de marca. */
export type PosicionLogo =
  | "superior-izquierda"
  | "superior-derecha"
  | "inferior-izquierda"
  | "inferior-derecha";

/**
 * Plantilla de marca: la identidad visual con la que se "estampa" una imagen
 * (logo/pleca/titular + colores). El logo es un objeto de media (`logo` = su id,
 * `logo_url` la URL para servirlo); si no hay logo se usa el texto `wordmark`.
 */
export interface PlantillaMarca {
  marca: string;
  /** Colores de marca (hex, p. ej. `#E10600`). */
  rojo: string;
  tinta: string;
  blanco: string;
  /** Etiqueta/pleca por defecto (p. ej. "ÚLTIMA HORA"). */
  etiqueta_default: string;
  titular_mayusculas: boolean;
  titular_condensada: boolean;
  /** Id del objeto de media del logo (PNG con transparencia), o "" si no hay. */
  logo: string;
  /** URL para servir el logo (vacía si no hay logo). */
  logo_url: string;
  logo_posicion: PosicionLogo;
  /** Texto de respaldo cuando no hay logo. */
  wordmark: string;
}

/** Respuesta de `GET /api/plantillas-marca`: mapa de plantillas por marca. */
export interface RespuestaPlantillasMarca {
  plantillas: Record<string, PlantillaMarca>;
}

/** Respuesta de `GET`/`PUT /api/plantillas-marca/{marca}`. */
export interface RespuestaPlantillaMarca {
  plantilla: PlantillaMarca;
}

/** Cuerpo de `POST /api/imagenes/componer`: estampa la plantilla de marca sobre una imagen. */
export interface CuerpoImagenesComponer {
  /** Nombre del objeto de media sobre el que componer. */
  imagen: string;
  marca: string;
  formato?: FormatoImagen;
  /** Titular corto opcional. */
  titular?: string;
  /** Etiqueta/pleca opcional (vacía = usa la de la plantilla). */
  etiqueta?: string;
}

// --- Biblioteca de artes (objetos de media catalogados para reutilizar) ---

/** Origen de un arte: trabajado en el Estudio, subido por el usuario o generado con IA. */
export type TipoArte = "estudio" | "subida" | "ia";

/**
 * Un ARTE: una imagen del almacén que el equipo CONSERVA para reutilizar en publicaciones.
 * Catalogarla la protege del GC de media huérfana y la hace seleccionable por marca.
 */
export interface Arte {
  /** Id del item de biblioteca (no del objeto de media). */
  id: string;
  /** Nombre del objeto de media (lo que se persiste en la pieza y resuelve `urlMedia`). */
  objeto: string;
  /** URL para servir la imagen (`/api/media/{objeto}`). */
  url: string;
  marca: string;
  marca_nombre: string;
  tipo: TipoArte;
  titulo: string;
  etiquetas: string[];
  creado: string;
}

/** Cuerpo de `POST /api/artes`: cataloga un objeto de media ya existente. */
export interface CuerpoGuardarArte {
  /** Id del objeto de media a catalogar. */
  objeto: string;
  marca?: string;
  tipo?: TipoArte;
  titulo?: string;
  etiquetas?: string[];
}

/** Respuesta de `GET /api/artes`. */
export interface RespuestaArtes {
  artes: Arte[];
}

/** Respuesta de `POST /api/artes`. */
export interface RespuestaArte {
  arte: Arte;
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

// --- Cadencia por red (margen entre posts) ---

/**
 * Una cadencia: scheduling por margen mínimo entre publicaciones de una red,
 * dentro de una ventana horaria y unos días, opcionalmente acotada a marca/red.
 */
export interface Cadencia {
  id: string;
  /** Marca asociada (`""` si aplica a todas). */
  marca: string;
  marca_nombre: string;
  /** Red asociada (`""` si aplica a todas). */
  red: string;
  red_nombre: string;
  /** Minutos mínimos entre posts. */
  margen_min: number;
  /** Hora de inicio de la ventana, formato "HH:MM". */
  hora_inicio: string;
  /** Hora de fin de la ventana, formato "HH:MM". */
  hora_fin: string;
  /** Días activos: 0=lunes .. 6=domingo. */
  dias: number[];
  activo: boolean;
}

export interface RespuestaCadencias {
  cadencias: Cadencia[];
}

export interface RespuestaCadencia {
  cadencia: Cadencia;
}

/** Cuerpo para crear o actualizar (UPSERT por marca+red) una cadencia. */
export interface CuerpoGuardarCadencia {
  marca?: string;
  red?: string;
  margen_min: number;
  hora_inicio: string;
  hora_fin: string;
  dias: number[];
  activo?: boolean;
}

export interface FiltrosPublicaciones {
  marca?: string;
  red?: string;
  estado?: string;
  /** Id de la línea editorial (etiqueta vertical) por la que filtrar. */
  linea?: string;
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
export type MetricaComercial = "interacciones" | "visualizaciones" | "alcance";

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
  /** Identidad preferida: el post real de Metricool elegido en el selector. */
  id_post_metricool?: string;
  /** Derivada del post (opcional); legado para el alta por enlace en demo. */
  url?: string;
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

export type CuerpoActualizarComercial = Partial<
  Omit<CuerpoCrearComercial, "url" | "id_post_metricool">
>;

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
  /**
   * MFA (segundo factor, passkeys/WebAuthn). Solo llegan por `GET /api/auth/me`:
   *   - `mfa_habilitado`: el flag del servidor (`KENI_CONSOLA_MFA`). Si es `false`/ausente,
   *     la UI NO muestra nada de MFA (la sección de "Mi cuenta" se oculta).
   *   - `mfa_activo`: si ESTA cuenta ya tiene ≥1 llave de acceso registrada.
   */
  mfa_habilitado?: boolean;
  mfa_activo?: boolean;
}

/** Respuesta de `POST /api/auth/login` cuando el usuario necesita el segundo factor (MFA). */
export interface RespuestaLoginMfa {
  mfa_required: true;
}

/**
 * Opciones de una ceremonia WebAuthn (registro o login). El backend las arma con py_webauthn
 * (`options_to_json`) y son JSON spec-compliant: se pasan TAL CUAL a `@simplewebauthn/browser`
 * (`startRegistration`/`startAuthentication`) como `optionsJSON`. No las tipamos campo a campo:
 * son opacas para nuestro código (la librería conoce su forma).
 */
export type OpcionesCeremoniaWebauthn = Record<string, unknown>;

/**
 * Respuesta de `POST /api/auth/mfa/registro/verificar`. `recovery_codes` solo llega la PRIMERA
 * vez (al registrar la primera passkey); se muestran una sola vez.
 */
export interface RespuestaMfaRegistro {
  ok: true;
  recovery_codes?: string[];
}

/** Una passkey en la lista de `GET /api/auth/mfa/credenciales` (sin secretos). */
export interface CredencialPasskey {
  id: string;
  nombre: string;
  creada: string;
  ultimo_uso: string;
}

/** Respuesta de `GET /api/auth/mfa/credenciales`. */
export interface RespuestaMfaCredenciales {
  credenciales: CredencialPasskey[];
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

// --------------------------------------------------------------------------- //
// Biblioteca de documentos (prompts + línea editorial)                         //
// --------------------------------------------------------------------------- //

export type TipoDocumento = "prompt" | "editorial";

/** Un documento de la biblioteca (prompt o pieza editorial). */
export interface DocumentoBiblioteca {
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
  /** Solo prompt: rol que ata el prompt a un pipeline (copy | qa | green | arte | ""). */
  rol?: string;
  /** Orden de ensamblaje del auto-adjunto (menor = antes). */
  prioridad?: number;
}

/** Resumen de facetas para poblar los filtros de navegación. */
export interface FacetasBiblioteca {
  etiquetas: { valor: string; total: number }[];
  estados: Record<string, number>;
  pipelines: Record<string, number>;
}

/** Un pipeline de generación (registro): su prompt base efectivo y rol esperado. */
export interface PipelineBiblioteca {
  id: string;
  titulo: string;
  descripcion: string;
  rol: string;
  prompt_base_id: string;
}

export interface RespuestaPipelinesBiblioteca {
  pipelines: PipelineBiblioteca[];
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
export interface VersionBiblioteca {
  sha: string;
  sha_corto: string;
  fecha: string;
  autor: string;
  mensaje: string;
}

export interface RespuestaHistorialBiblioteca {
  historial: VersionBiblioteca[];
}

/** `GET /api/biblioteca`: documentos filtrados + carpetas existentes + facetas. */
export interface RespuestaBiblioteca {
  documentos: DocumentoBiblioteca[];
  carpetas: string[];
  facetas?: FacetasBiblioteca;
}

export interface RespuestaDocumento {
  documento: DocumentoBiblioteca;
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
  editoriales: DocumentoBiblioteca[];
}

/** Diagnóstico de los 4 pilares de la línea editorial de una marca (GET /biblioteca/validacion). */
export interface ValidacionEditorial {
  completa: boolean;
  faltan: string[];
  recomendacion: string;
  pilares: Record<string, boolean>;
}

export interface AreaBiblioteca {
  id: string;
  nombre: string;
}

export interface RespuestaAreas {
  areas: AreaBiblioteca[];
}

export interface RespuestaMarcasBiblioteca {
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

export interface CuerpoLanzarBiblioteca {
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

/** Tipo de alerta de rendimiento (subconjunto de eventos internos de la bitácora). */
export type TipoAlerta = "pieza.bajo_rendimiento" | "pieza.reciclaje_sugerida";

/**
 * Una alerta de rendimiento leída de la bitácora (`GET /api/alertas`): aviso proactivo
 * que el daemon `alertas_rendimiento` emite sobre las piezas publicadas.
 */
export interface AlertaRendimiento {
  id: string;
  /** Uno de `TipoAlerta`; se deja `string` por tolerancia ante tipos nuevos del backend. */
  tipo: string;
  contenido_id: string;
  plataforma_id: string;
  /** Payload genérico del evento (`{evento, emitido_en, resumen, datos}`). */
  payload: {
    resumen?: string;
    datos?: Record<string, unknown>;
    [clave: string]: unknown;
  };
  creado: string;
}

/** Respuesta de `GET /api/alertas`. */
export interface RespuestaAlertas {
  alertas: AlertaRendimiento[];
}

// ── Importador de calendario Excel/CSV (H1) ─────────────────────────────────
// `POST /api/contenido/importar` (multipart). Con `previsualizar=1` devuelve las
// filas parseadas; sin él, importa y devuelve el resumen. Dicts ad-hoc (a mano).
export interface FilaCalendarioImport {
  titulo: string;
  fecha: string;
  marca: string;
  redes: string[];
  prioridad: string;
  compromiso: boolean;
  notas: string;
}

export interface ErrorImportCalendario {
  fila?: number;
  motivo: string;
}

export interface RespuestaImportPreview {
  previsualizacion: true;
  filas: FilaCalendarioImport[];
  errores: ErrorImportCalendario[];
}

export interface RespuestaImportCalendario {
  creados: number;
  omitidos: { titulo: string; motivo: string }[];
  errores: ErrorImportCalendario[];
}

// ── Ajustes de funcionalidad (admin, toggles + tuning en caliente) ──────────
// `GET/POST /api/ajustes`: store editable que `config` consulta (store > env >
// defecto). Dicts ad-hoc (a mano, no `types.gen.ts`).
export interface OpcionAjuste {
  id: string;
  etiqueta: string;
}

export interface AjusteAdmin {
  clave: string;
  tipo: "bool" | "int" | "float" | "select";
  etiqueta: string;
  ayuda: string;
  grupo: string;
  peligroso: boolean;
  valor: boolean | number | string;
  fuente: "store" | "env" | "defecto";
  defecto: boolean | number | string;
  opciones?: OpcionAjuste[];
  min?: number;
  max?: number;
}

export interface GrupoAjustes {
  id: string;
  titulo: string;
  ajustes: AjusteAdmin[];
}

export interface RespuestaAjustes {
  grupos: GrupoAjustes[];
}

export interface RespuestaAjusteGuardado {
  ajuste: AjusteAdmin;
}

// ── Sistema (panel de admin: CPU/RAM/disco + S3/Garage) ──────────────────────
// `GET /api/sistema/recursos` y `GET /api/sistema/s3`. Solo admin (403 si no).
// Bytes en crudo (el front formatea GB/%). Campos null = degradado (sonda no
// disponible), nunca un error que tumbe la página.

/** Uso de un volumen de disco. Bytes en crudo. */
export interface DiscoSistema {
  /** Etiqueta legible ("Estado", "Sistema"). */
  etiqueta: string;
  /** Ruta sondeada (p.ej. `/data` o `/`). */
  ruta: string;
  usado: number;
  total: number;
  /** Porcentaje de uso (0–100, 1 decimal). */
  porcentaje: number;
}

/** Respuesta de `GET /api/sistema/recursos`. CPU/RAM null si psutil no está. */
export interface RespuestaRecursos {
  cpu: { porcentaje: number | null; cores: number | null };
  ram: { usado: number | null; total: number | null; porcentaje: number | null };
  discos: DiscoSistema[];
  /** `true` si psutil estaba disponible para CPU/RAM. */
  psutil: boolean;
}

/** Respuesta de `GET /api/sistema/s3`. `configurado:false` = media en disco local. */
export interface RespuestaS3 {
  configurado: boolean;
  endpoint: string | null;
  bucket: string | null;
  region: string | null;
  /** Salud del bucket (head_bucket): "ok" | "err" | null (sin configurar). */
  salud: "ok" | "err" | null;
  /** Nº de objetos del bucket (null si no se pudo medir). */
  objetos: number | null;
  /** Bytes totales del bucket (null si no se pudo medir). */
  bytes: number | null;
  /** `true` si el conteo se truncó por tope (es un mínimo). */
  truncado: boolean;
  /** Mensaje de error legible si la sonda falló; null si todo bien. */
  error: string | null;
}

/** Respuesta de `POST /api/sistema/s3/probar` (test de conexión). */
export interface RespuestaProbarS3 {
  salud: "ok" | "err";
  error: string | null;
}

// ── S3 Navegador de objetos (GET /api/sistema/s3/objetos) ────────────────────

/** Una miga del breadcrumb del explorador S3 ({nombre, prefijo}). */
export interface MigaS3 {
  /** Nombre legible del nivel ("Raiz", "videos", "2024"…). */
  nombre: string;
  /** Prefijo acumulado hasta este nivel (p.ej. "videos/2024/"). Vacío = raíz. */
  prefijo: string;
}

/** Un objeto (archivo) del bucket S3. */
export interface ObjetoS3 {
  /** Clave completa del objeto en el bucket. */
  key: string;
  /** Nombre legible (basename). */
  nombre: string;
  /** Tamaño en bytes. */
  tamano: number;
  /** Fecha de última modificación (ISO) o null. */
  modificado: string | null;
}

/** Respuesta de `GET /api/sistema/s3/objetos?prefijo=<p>`. */
export interface RespuestaS3Objetos {
  /** `false` si S3 no está configurado en este servidor. */
  configurado: boolean;
  /** Prefijos de subcarpetas bajo el prefijo actual. */
  carpetas: string[];
  /** Objetos del nivel actual. */
  objetos: ObjetoS3[];
  /** Prefijo activo (normalizado, termina en "/" o vacío para raíz). */
  prefijo: string;
  /** Breadcrumb desde la raíz hasta el nivel actual. */
  migas: MigaS3[];
  /** Error legible si la sonda falló; null si todo bien. */
  error: string | null;
}

/** Respuesta de `POST /api/sistema/s3/borrar`. */
export interface RespuestaBorrarS3 {
  /** `true` si el objeto se borró. */
  borrado: boolean;
  /** Key del objeto borrado. */
  key: string;
}

/** Un objeto que no se pudo borrar en un borrado en masa. */
export interface FalloBorradoS3 {
  /** Key del objeto que falló. */
  key: string;
  /** Mensaje de error devuelto por el almacenamiento. */
  error: string;
}

/** Respuesta de `POST /api/sistema/s3/borrar-lote`. */
export interface RespuestaBorrarLoteS3 {
  /** Keys borradas correctamente. */
  borrados: string[];
  /** Keys que fallaron, con su motivo. */
  fallidos: FalloBorradoS3[];
}

/** Un grupo (valor de un eje) con su rendimiento agregado. */
export interface GrupoPorEtiqueta {
  /** Valor del eje (p. ej. "reel", "Mundial 2026", "Sin clasificar"). */
  valor: string;
  /** Nº de piezas del periodo en este grupo. */
  n: number;
  /** Suma de visualizaciones de las piezas del grupo. */
  visualizaciones: number;
  /** Engagement medio (%) de las piezas del grupo. */
  engagement_pct: number;
}

/** Una serie graficable: un eje de agrupación con sus grupos. */
export interface SeriePorEtiqueta {
  /** Clave del eje (tipo|campania|vertical|etiqueta_tipo). */
  eje: string;
  /** Etiqueta legible del eje para el tab/título. */
  etiqueta: string;
  grupos: GrupoPorEtiqueta[];
}

/** Respuesta de `GET /api/metricas/piezas-por-etiqueta` (Item C). */
export interface PiezasPorEtiqueta {
  marca: string;
  rango: string;
  etiqueta_rango: string;
  series: SeriePorEtiqueta[];
  /** Piezas del periodo (Metricool). */
  total: number;
  /** Enlazadas a un `contenido` por id_post_metricool. */
  enlazadas: number;
  /** Enlazadas por fuzzy-match de título (heurístico). */
  enlazadas_titulo: number;
  /** Sin enlace (caen en "Sin clasificar"). */
  sin_enlace: number;
  fuente: string;
}

// ── Insumos del día (cajones) ─────────────────────────────────────────────────
// Contrato compartido con el backend (01-insumos-del-dia.md). Todos los campos
// usan snake_case tal como los devuelve la API (verificado en el contrato).

/** Los cuatro cajones de insumos diarios. */
export type CajonInsumo = "portal" | "corresponsales" | "reporteros" | "eventos_claro";

/** Un lote de insumos (un "drop" en un cajón; el parseo Haiku produce los items). */
export interface InsumoLote {
  id: string;
  fecha: string;
  cajon: CajonInsumo;
  marca: string;
  origen_texto: string;
  origen_archivo: string;
  estado: "listo" | "error";
  error: string;
  total_items: number;
  creado: string;
}

/** Un ítem parseado dentro de un lote de insumos. */
export interface InsumoItem {
  id: string;
  lote_id: string;
  fecha: string;
  cajon: CajonInsumo;
  marca: string;
  /** Nombre legible de la marca (resuelto por el backend). */
  marca_nombre: string;
  linea: string;
  titulo: string;
  resumen: string;
  hora: string;
  lugar: string;
  estado_material: "tengo" | "espero" | "";
  tipo: "nota" | "cobertura" | "evento";
  idioma: string;
  /** `true` si ya se llevó al tablero. */
  usado: boolean;
  contenido_id: string;
  orden: number;
  creado: string;
  /** Estado de frescura según la TTL de la línea. "caduco" = ítem vencido. */
  frescura?: "fresco" | "caduco";
}

/** Un cajón con sus lotes e ítems para un día concreto. */
export interface CajonConItems {
  cajon: CajonInsumo;
  lotes: InsumoLote[];
  items: InsumoItem[];
}

/** Respuesta de `GET /api/insumos?fecha=`. */
export interface RespuestaInsumos {
  fecha: string;
  cajones: CajonConItems[];
}

/** Resumen de un día con insumos (para el selector de historial). */
export interface DiaInsumos {
  fecha: string;
  total: number;
  por_cajon: Record<CajonInsumo, number>;
}

/** Respuesta de `GET /api/insumos/dias`. */
export interface RespuestaDiasInsumos {
  dias: DiaInsumos[];
}

// ── Agentes de investigación (Ola 6) ─────────────────────────────────────────
// Contrato: docs/maquina-contenido/06-agentes-investigacion.md

/** Un encargo de investigación reutilizable (brief). */
export interface InvBrief {
  id: string;
  nombre: string;
  marca: string;
  linea: string;
  instrucciones: string;
  /** CSV de idiomas a rastrear ("" = cualquiera). */
  idiomas: string;
  activo: number; // 1 = activo, 0 = inactivo
  creado: string;
}

/** Un candidato propuesto por un agente de investigación. */
export interface InvCandidato {
  id: string;
  brief_id: string;
  fecha: string;
  marca: string;
  /** Nombre legible de la marca (puede estar ausente en respuestas minimalistas). */
  marca_nombre?: string;
  linea: string;
  titulo: string;
  resumen: string;
  /** Por qué es relevante hoy. */
  por_que: string;
  /** Medio/origen de la noticia. */
  fuente: string;
  enlace: string;
  idioma: string;
  /** Estado del candidato: "nuevo" | "aceptado" | "descartado". */
  estado: "nuevo" | "aceptado" | "descartado" | string;
  /** Id del contenido en el tablero (si fue aceptado). */
  contenido_id: string;
  creado: string;
}

// ── Respuestas de la API de investigación ─────────────────────────────────────

export interface RespuestaInvBriefs {
  briefs: InvBrief[];
}

export interface RespuestaInvBrief {
  brief: InvBrief;
}

export interface RespuestaInvCandidatos {
  candidatos: InvCandidato[];
}

export interface RespuestaInvCandidato {
  candidato: InvCandidato;
  /** Id del contenido en el tablero (para aceptar). */
  contenido_id?: string;
}

export interface RespuestaInvCorrer {
  candidatos: InvCandidato[];
  errores: unknown[];
}
