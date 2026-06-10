import type { MetricasRun, Paginacion, ResultadoEstado } from "../types.gen";

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

// --- Monitor de cola (`GET /api/actividad/cola` y `/cola/series`) ---

/** Un job EN VUELO (pendiente o reclamado) enriquecido con su registro de generación. */
export interface ColaJob {
  job_id: string;
  gen_id: string;
  estado: string; // "pendiente" | "reclamado"
  worker: string;
  etiqueta: string;
  tipo: string;
  marca: string;
  gen_estado: string;
  fase: string;
  /** Prioridad de despacho (mayor = adelanta en la cola; manual > lote del pipeline). */
  prioridad: number;
  encolado_hace_s: number | null;
  corriendo_hace_s: number | null;
}

/** Estado ON/OFF de un daemon de fondo. `activo: null` = desconocido. */
export interface ColaDaemon {
  clave: string;
  etiqueta: string;
  activo: boolean | null;
  descripcion: string;
  /** Env var del catálogo de ajustes que lo enciende/apaga ("" = sin toggle, p. ej. reaper). */
  clave_ajuste: string;
  /** Si el Monitor puede pintarlo como TOGGLE real (clave en catálogo y no peligrosa). */
  editable: boolean;
}

/** Snapshot en vivo de la cola de generación + workers + daemons. */
export interface ColaMonitor {
  /** Eco del filtro de marca aplicado a las listas en_curso/esperando ("" = todas). */
  marca: string;
  capacidad: { max_jobs: number; max_cola: number; tope: number };
  conteo: { pendientes: number; reclamados: number; terminados: number; activos: number };
  cola_llena: boolean;
  procesando: number;
  slots_libres: number;
  workers_activos: string[];
  en_curso: ColaJob[];
  esperando: ColaJob[];
  daemons: ColaDaemon[];
}

/** Serie por día de la cola: encolados (entrada) y resultados (salida). */
export interface ColaSerie {
  dias: number;
  encolados: { dia: string; n: number }[];
  resultados: { dia: string; completados: number; errores: number; cola_llena: number }[];
}

/** Respuesta de purgar la cola (admin). */
export interface RespuestaPurgarCola {
  purgados: number;
}

/** Respuesta de reencolar un job (admin). */
export interface RespuestaReencolarCola {
  reencolado: boolean;
  gen_id: string;
}

// --- Pipelines (vista estilo GitLab del pipeline de contenido CI/CD) ---

/** Una etapa de una run del pipeline (CI/CD/QA/Aprobación). */
export interface PipelineEtapa {
  clave: string;
  nombre: string;
  estado: string;
  detalle: string;
  ts: string;
  /** `true` si la etapa es una llamada a un LLM (la UI la marca «IA» y enseña prompt+proceso). */
  es_ia: boolean;
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

/** Procedencia IA de un tema: la HISTORIA (cluster) de la que nació, con las señales del
 *  pool de noticias (dedup/fusión + ranking). `null` si el tema se creó a mano o pre-ranking. */
export interface PipelineCluster {
  id: string;
  /** Fuentes distintas que corroboran la historia (corroboración). */
  n_fuentes: number;
  /** Notas agrupadas en la historia (resultado de la fusión semántica + clustering). */
  n_items: number;
  /** Score del ranking [0..1] (jerarquización por ponderación). */
  score: number;
  /** Historia "breaking" (muchas fuentes en poco tiempo). */
  breaking: boolean;
  /** Verificación por corroboración: "corroborada" | "unica_fuente" | "dudosa" | "". */
  verificacion: string;
  /** Señal de viralidad (tráfico aprox. de tendencias); 0 si no aplica. */
  senal: number;
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
  /** Clave de la etapa donde la run está «parada» (1ª no-ok/saltada); "" si todo está hecho. */
  etapa_actual: string;
  etapas: PipelineEtapa[];
  /** Criba de la fuente (⚠️/❗ + hallazgos). Siempre presente desde el back. */
  qa_fuente?: PipelineQaFuente;
  /** Procedencia IA (historia/cluster) del tema. `null` si no nació de una historia. */
  cluster?: PipelineCluster | null;
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
  /** Envelope de paginación offset (`{total, limite, desplazamiento}`). */
  paginacion: Paginacion;
}

/** El STREAM (proceso de pensamiento de `claude -p`) de la generación de una etapa.
 *  Lo expone el detalle del pipeline por código de etapa (CI/CD/QA): `salida` es el texto
 *  del agente en vivo; `fase`/`estado` dicen en qué punto va (razonando/escribiendo/...). */
export interface PipelineGeneracion {
  id: string;
  estado: string;
  fase: string;
  /** Prompt EXACTO enviado a la IA (lo que se le pidió). "" si no se registró. */
  prompt: string;
  /** Stream token a token: el razonamiento del agente + el resultado final. */
  salida: string;
  metricas: MetricasRun | null;
}

export interface RespuestaPipelineDetalle {
  pipeline: Pipeline;
  actividad: PipelineActividad[];
  /** Stream del agente por código de etapa ("FUSION"/"EDITORIAL"/"QA"/"CD"/"ARTE"). {} si no hay. */
  generaciones_por_etapa?: Record<string, PipelineGeneracion>;
  /** Plantilla del prompt de cada etapa IA (para enseñar el prompt de entrada aunque no haya
   *  corrido aún; cuando corre, se prefiere el prompt real de la generación). */
  prompts_por_etapa?: Record<string, string>;
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

// ── Daemons de fondo (GET /api/sistema/daemons) ──────────────────────────────
// Latidos persistidos por cada daemon (tabla `daemon_latidos`): el bucle late en cada
// vuelta (`visto`) y cada barrido deja resultado (`ultimo_ok`/`ultimo_error`). El back
// ya juzga el `estado` (umbral de atraso incluido); el front solo pinta.

/** Estado agregado de un daemon, calculado por el back. */
export type EstadoDaemon = "ok" | "error" | "inactivo" | "atrasado";

/** Latido de un daemon de fondo (una fila de `daemon_latidos` + campos derivados). */
export interface LatidoDaemon {
  /** Nombre estable del daemon ("ingesta", "pipeline", "reaper"…). */
  daemon: string;
  /** Última vuelta del bucle (ISO) — el hilo vive aunque el gate esté OFF. */
  visto: string;
  /** `true` si el gate del daemon estaba ON en la última vuelta. */
  activo: boolean;
  /** Intervalo configurado entre barridos (segundos). */
  intervalo_seg: number;
  /** Cadencia real del bucle (segundos); base del umbral de atraso. */
  tick_seg: number;
  /** Último barrido ejecutado (ISO) o "". */
  ultimo_barrido: string;
  /** Último barrido OK (ISO) o "". */
  ultimo_ok: string;
  /** Último barrido con error (ISO) o "". */
  ultimo_error: string;
  /** Texto del último error (truncado) o "". */
  error_txt: string;
  /** Duración del último barrido (ms). */
  duracion_ms: number;
  /** Barridos totales desde el primer registro. */
  barridos: number;
  /** Barridos fallidos totales. */
  errores: number;
  /** Edad del último latido (segundos) o null si nunca latió. */
  edad_seg: number | null;
  /** Umbral aplicado para juzgar "atrasado" (segundos). */
  umbral_atraso_seg: number;
  /** Estado listo para pintar. */
  estado: EstadoDaemon;
}

/** Respuesta de `GET /api/sistema/daemons`. Degradada: lista vacía + error legible. */
export interface RespuestaDaemons {
  daemons: LatidoDaemon[];
  error: string | null;
}

// ── Backups locales (GET /api/sistema/backups) ───────────────────────────────
// El keni-backup del host escribe estado.json en cada run; el back lo monta :ro.

/** Un volumen incluido en el último backup (estado.json). */
export interface VolumenBackup {
  volumen: string;
  bytes: number;
}

/** estado.json del último run de keni-backup (forma escrita por el script). */
export interface EstadoBackup {
  /** Stamp del run (YYYYmmdd-HHMMSS, UTC). */
  stamp: string;
  /** `true` si el run completó sin fallos. */
  ok: boolean;
  /** Último paso ejecutado (en fallo, el paso que rompió). */
  paso: string;
  /** Texto de error ("" si ok). */
  error: string;
  duracion_seg: number;
  dump_bytes: number;
  /** `true` si dump (pg_restore --list) y tars (gzip -t) verificaron. */
  verificado: boolean;
  volumenes: VolumenBackup[];
}

/** Dump de Postgres más reciente en disco. */
export interface UltimoDump {
  fichero: string;
  bytes: number;
  /** ISO naive-UTC del mtime. */
  modificado: string;
  edad_seg: number;
}

/** Respuesta de `GET /api/sistema/backups`. Degradada: `configurado:false`. */
export interface RespuestaBackups {
  /** `false` si el directorio de backups no está montado en este despliegue. */
  configurado: boolean;
  /** estado.json del último run o null (aún sin run / ilegible). */
  estado: EstadoBackup | null;
  /** Nº de dumps de Postgres retenidos. */
  dumps: number;
  ultimo_dump: UltimoDump | null;
  /** `true` si no hay dump en las últimas 26 h (timer diario + margen). */
  atrasado: boolean;
  error: string | null;
}

// ── Rendimiento de la API (GET /api/sistema/rendimiento) ─────────────────────
// Agregador en memoria del back: ventana deslizante (últimas 256 peticiones por
// ruta normalizada) de la latencia al primer byte. Se reinicia con cada deploy.

/** Latencias agregadas de una ruta de la API. */
export interface RutaRendimiento {
  /** "GET /api/contenido/{id}" (método + ruta con ids colapsados). */
  ruta: string;
  /** Peticiones totales desde el arranque del proceso. */
  n: number;
  /** Respuestas 5xx totales. */
  err_5xx: number;
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
  ultimo_ms: number;
}

/** Respuesta de `GET /api/sistema/rendimiento`. */
export interface RespuestaRendimiento {
  /** ISO del arranque del agregador (deploy del back). */
  desde: string;
  /** Rutas ordenadas por nº de peticiones (desc). */
  rutas: RutaRendimiento[];
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
