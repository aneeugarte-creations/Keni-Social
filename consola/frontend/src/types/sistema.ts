import type { MetricasRun, Paginacion, ResultadoEstado } from "../types.gen";

// --- Estado (autodiagnostico del sistema) ---

/** Nivel de un chequeo del autodiagnóstico (derivado del tipo generado). */
export type NivelEstado = ResultadoEstado["estado"];

/** Un chequeo del doctor (`GET /api/estado`): el tipo generado más los campos del contrato
 *  que el subconjunto estable (`types.gen.ts`) aún no recoge — id estable del chequeo,
 *  visibilidad por rol y paso accionable cuando no está ok. */
export interface ChequeoEstado extends ResultadoEstado {
  /** Id estable "dominio:chequeo" (p. ej. `maquina:cola`, `infra:disco`). */
  id: string;
  /** `true` = chequeo de operador (infra/metricas): solo se muestra a admins. */
  admin: boolean;
  /** Qué hacer para arreglarlo; null cuando el chequeo está ok. */
  siguiente_paso: string | null;
}

/** Respuesta del doctor (`GET /api/estado`) con los chequeos enriquecidos. */
export interface RespuestaDoctor {
  resultados: ChequeoEstado[];
  resumen: string;
  siguiente_paso: string;
}

// --- Actividad IA unificada (agregados; hoy la consume la página Producción) ---
//
// Sección AD-HOC (a mano): agregados del registro unificado que expone el backend
// (generaciones de IA en segundo plano + runs de agentes). NO se genera desde
// `types.gen.ts`; el backend lo construye como dict ad-hoc. (El feed por items
// `GET /api/actividad` se retiró: la actividad se mira en Pipelines.)

/** Totales globales del periodo disponible. */
export interface ActividadTotal {
  items: number;
  coste_usd: number;
  tokens: number;
  /** Tiempo de cómputo IA sumado (ms). Opcional para compatibilidad con backs previos. */
  duration_ms?: number;
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
  /** Tokens IA del día (sumados de las generaciones + runs). */
  tokens: number;
}

/** Desglose de actividad de UN proceso (loop de la máquina, ADR 0011): misma forma que el
 * agregado global, pero SOLO generaciones de ese proceso (los runs de agente quedan fuera). */
export interface ActividadProcesoBloque {
  total: ActividadTotal;
  por_tipo: ActividadPorTipo[];
  por_dia: ActividadPorDia[];
}

/** Agregados de actividad IA (`GET /api/actividad/agregados`): totales + desgloses (los KPIs de Producción). */
export interface ActividadAgregados {
  total: ActividadTotal;
  por_tipo: ActividadPorTipo[];
  por_dia: ActividadPorDia[];
  /** Desglose ADITIVO por proceso (SOLO generaciones; investigación/producción). Opcional
   * para compatibilidad con backs anteriores. Cada bloque tiene la misma forma que el global. */
  por_proceso?: Record<Proceso, ActividadProcesoBloque>;
}

// --- Monitor de cola (`GET /api/actividad/cola` y `/cola/series`) ---

/** Un job EN CURSO (pendiente o reclamado) enriquecido con su registro de generación. */
/** Proceso de la máquina (ADR 0011): los dos loops que comparten la misma cola/pool. */
export type Proceso = "investigacion" | "produccion";

export interface ColaJob {
  job_id: string;
  gen_id: string;
  estado: string; // "pendiente" | "reclamado"
  worker: string;
  etiqueta: string;
  tipo: string;
  marca: string;
  /** A qué loop pertenece el job: investigación (verificación/QA) o producción (copy/arte). */
  proceso: Proceso;
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
  /** Env var del catálogo de ajustes que lo enciende/apaga ("" = sin toggle, p. ej. limpiador). */
  clave_ajuste: string;
  /** Si el Monitor puede pintarlo como TOGGLE real (clave en catálogo y no peligrosa). */
  editable: boolean;
}

/** Gasto de IA acumulado del día UTC (ledger `gasto_ia`). */
export interface GastoIADia {
  tokens: number;
  tokens_in: number;
  tokens_out: number;
  coste_usd: number;
  generaciones: number;
}

/** Economía de tokens (`presupuesto_ia.estado()`): presupuesto diario, gasto y nivel. */
export interface PresupuestoIA {
  /** Nivel de corte vigente: "normal" | "solo_manual" | "agotado" | "pausado". */
  nivel: string;
  /** Kill switch humano (KENI_GENERACION_PAUSADA, editable en caliente). */
  pausada: boolean;
  /** Presupuesto de tokens/día (0 = sin límite). */
  presupuesto_tokens_dia: number;
  margen_manual_pct: number;
  gastado: GastoIADia;
  /** null si no hay presupuesto configurado. */
  restante_tokens: number | null;
  /** % del presupuesto consumido (null sin presupuesto). */
  pct_usado: number | null;
  /** Día UTC del acumulado (YYYY-MM-DD). */
  dia: string;
}

/** Conteo del pool COMPARTIDO atribuible a un proceso (jobs en curso de ese loop). */
export interface ConteoProceso {
  /** Jobs reclamados (claude -p corriendo) de este proceso. */
  procesando: number;
  /** Jobs pendientes (esperando slot) de este proceso. */
  pendientes: number;
}

/** Admisión de QA: el único límite que Investigación acota aparte de la cola compartida. */
export interface AdmisionQa {
  /** Clusters en el admision de verificación (en proceso + pendientes + saltados), sumados. */
  en_proceso: number;
  /** Tope en proceso POR MARCA (cuánta verificación cabe a la vez por marca). */
  tope_por_marca: number;
  marcas: { marca: string; en_proceso: number; tope: number }[];
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
  /** Desglose del pool compartido por proceso (ADR 0011): los dos loops sobre la misma cola. */
  por_proceso?: Record<Proceso, ConteoProceso>;
  /** Estado del admision de QA (Investigación). */
  admision_qa?: AdmisionQa;
  en_curso: ColaJob[];
  esperando: ColaJob[];
  daemons: ColaDaemon[];
  /** Economía de tokens (opcional para compatibilidad con backs anteriores). */
  presupuesto?: PresupuestoIA;
}

/** Gasto/throughput de un proceso en un día (desde las generaciones reales, sin marcadores). */
export interface ResultadoProceso {
  completados: number;
  errores: number;
  tokens: number;
  coste_usd: number;
}

/** Resultados de un día: totales + desglose por proceso (marcadores de etapa EXCLUIDOS). */
export interface ResultadoDia {
  dia: string;
  completados: number;
  errores: number;
  cola_llena: number;
  por_proceso?: Record<Proceso, ResultadoProceso>;
}

/** Serie por día de la cola: encolados (entrada) y resultados (salida). */
export interface ColaSerie {
  dias: number;
  encolados: { dia: string; n: number }[];
  resultados: ResultadoDia[];
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

/** Respuesta de priorizar un job esperando (admin). */
export interface RespuestaPriorizarCola {
  priorizado: boolean;
  gen_id: string;
}

/** Una línea del plan editorial diario: generados/publicados vs objetivo en la ventana. */
export interface ProduccionLinea {
  categoria: string;
  generados: number;
  publicados: number;
  objetivo: number | null;
}

/** Resumen mínimo de /api/produccion/dia que consume el Monitor (líneas del plan). */
export interface ProduccionDia {
  marca: string;
  objetivo: { dia: number | null; plan: Record<string, number> | null };
  por_categoria: ProduccionLinea[];
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

/** Un hallazgo estructurado de la verificación de la fuente (lo que está mal en la nota de origen). */
export interface PipelineHallazgo {
  tipo?: string;
  gravedad?: string;
  fragmento?: string;
  explicacion?: string;
  sugerencia?: string;
  no_verificable?: boolean;
}

/** Veredicto ESTRUCTURADO de la verificación de la fuente (rediseño QPC, pre-copy):
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

/** Métricas sumadas de las generaciones de un item del feed de Producción. */
export interface PipelineMetricas {
  /** Nº de generaciones correlacionadas (1 en los items sueltos). */
  items: number;
  tokens: number | null;
  coste_usd: number | null;
  duration_ms: number | null;
}

/** Un item del feed UNIFICADO de Producción: una RUN del pipeline (el recorrido de una
 *  pieza por sus etapas) o un trabajo SUELTO de IA (`clase: "actividad"`: generación
 *  manual/lote o run de agente), presentado con la misma forma y UNA etapa. */
export interface Pipeline {
  /** "run" (run del pipeline) | "actividad" (trabajo suelto). Ausente en backs previos = run. */
  clase?: "run" | "actividad";
  id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  origen?: string;
  /** Solo items sueltos: el tipo de trabajo (copy/rss/imagen/investigacion/run/…). */
  tipo?: string;
  descripcion?: string;
  creado: string;
  actualizado: string;
  estado_global: "ok" | "en_curso" | "pendiente" | "revisar" | "fallo";
  /** Clave de la etapa donde la run está «parada» (1ª no-ok/saltada); "" si todo está hecho. */
  etapa_actual: string;
  etapas: PipelineEtapa[];
  /** Verificación de la fuente (⚠️/❗ + hallazgos). `null` en items sueltos. */
  qa_fuente?: PipelineQaFuente | null;
  /** Procedencia IA (historia/cluster) del tema. `null` si no nació de una historia. */
  cluster?: PipelineCluster | null;
  /** Tokens/coste/duración sumados de sus generaciones. Opcional (backs previos). */
  metricas?: PipelineMetricas;
  piezas: PipelinePieza[];
  /** Solo items sueltos: ruta del SPA al resultado de la generación (si su tipo tiene página). */
  resultado_url?: string | null;
}

/** Un tema BLOQUEADO del pipeline (`GET /api/pipelines/problemas`): tras agotar reintentos
 *  (o una verificación de peso) queda con veredicto `problema` y SALE del flujo; esta forma lo hace
 *  visible para que un humano decida (relanzar a mano / descartar). */
export interface ProblemaPipeline {
  id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  /** Etapa donde se bloqueó ("Verificar" o el fragmento del último hallazgo de sistema). */
  etapa: string;
  /** Reintentos quemados por etapa (verificación de la fuente / redacción). */
  intentos: { verificar: number; redactar: number };
  /** Motivo legible del bloqueo (explicación del último hallazgo o resumen de la verificación). */
  error: string;
  resumen: string;
  hallazgos: PipelineHallazgo[];
  creado: string;
  actualizado: string;
}

/** Respuesta de `GET /api/pipelines/problemas` (recientes primero; `total` sin recortar). */
export interface RespuestaProblemas {
  problemas: ProblemaPipeline[];
  total: number;
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
  /** SUMATORIO de métricas de TODOS los items que casan el filtro (no solo la página):
   *  tokens/coste/duración; `items` = generaciones sumadas. Opcional (backs previos). */
  totales?: PipelineMetricas;
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
  tipo: "bool" | "int" | "float" | "select" | "texto";
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
// iteración (`visto`) y cada barrido deja resultado (`ultimo_ok`/`ultimo_error`). El back
// ya juzga el `estado` (umbral de atraso incluido); el front solo pinta.

/** Estado agregado de un daemon, calculado por el back. */
export type EstadoDaemon = "ok" | "error" | "inactivo" | "atrasado";

/** Grupo (motor/papel) de un daemon para el dashboard de Workers, calculado por el back. */
export type GrupoDaemon = "investigacion" | "produccion" | "flujo" | "infra";

/** Clase AFINADA de un daemon (cuánta IA de cara adentro): `ia` corre `claude -p`, `maquina`
 *  es máquina NO-IA del loop de contenido, `sistema` es pura infraestructura. */
export type ClaseDaemon = "ia" | "maquina" | "sistema";

/** Motor (loop de la máquina, ADR 0011) al que pertenece el daemon, o `null` si es infra. */
export type MotorDaemon = "investigacion" | "produccion" | null;

/** Latido de un daemon de fondo (una fila de `daemon_latidos` + campos derivados). */
export interface LatidoDaemon {
  /** Nombre estable del daemon ("ingesta", "pipeline", "limpiador"…). */
  daemon: string;
  /** Última iteración del bucle (ISO) — el hilo vive aunque el gate esté OFF. */
  visto: string;
  /** `true` si el gate del daemon estaba ON en la última iteración. */
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
  /** ISO de la solicitud de barrido forzado pendiente, o "" si no hay ninguna. */
  barrido_solicitado: string;
  /** `true` si su bucle consume el flag de barrido forzado (`bucle_gateado`): solo a esos
   *  se les ofrece «Barrer ahora». Los bucles legados (programador/metricas/…) no lo miran. */
  barrible: boolean;
  /** Grupo (motor/papel) al que pertenece el daemon; agrupa el dashboard de Workers. */
  grupo: GrupoDaemon;
  /** Clase afinada del daemon (`ia`|`maquina`|`sistema`); contrato ADITIVO sobre `grupo`. */
  clase: ClaseDaemon;
  /** Motor de la máquina al que pertenece (`investigacion`|`produccion`) o `null` si es infra. */
  motor: MotorDaemon;
  /** `true` si el daemon encola/ejecuta `claude -p` (gasta tokens); `false` el resto. */
  gasta_tokens: boolean;
  /** Clave de ajuste (KENI_*) que enciende/apaga el daemon desde su fila (toggle in-place;
   *  pásala a `POST /api/ajustes`). `null` = SIEMPRE-ON sin toggle (limpiador/programador/…). */
  clave_gate: string | null;
}

/** Respuesta de `GET /api/sistema/daemons`. Degradada: lista vacía + error legible. */
export interface RespuestaDaemons {
  daemons: LatidoDaemon[];
  error: string | null;
}

/** Respuesta de `POST /api/sistema/daemons/{daemon}/barrer` (200). */
export interface RespuestaBarrerDaemon {
  solicitado: boolean;
  daemon: string;
}

// ── Historial de barridos de un daemon (GET /api/sistema/daemons/{daemon}/barridos) ──────
// Una fila de `daemon_barridos`: el LOG por barrido (nuevo primero). El bucle deja un registro
// cada vez que barre (con su duración, si fue OK, un resumen y el error si lo hubo).

/** Un barrido registrado de un daemon (una fila de `daemon_barridos`). */
export interface BarridoDaemon {
  /** Id del registro. */
  id: string;
  /** Daemon al que pertenece el barrido. */
  daemon: string;
  /** Inicio del barrido (ISO). */
  ts_inicio: string;
  /** Duración del barrido (ms). */
  duracion_ms: number;
  /** `true` si el barrido terminó bien. */
  ok: boolean;
  /** Resumen de lo que hizo el barrido (puede venir vacío). */
  resumen: string;
  /** Texto del error si el barrido falló, o "". */
  error_txt: string;
}

/** Respuesta de `GET /api/sistema/daemons/{daemon}/barridos?limite=`. */
export interface RespuestaBarridosDaemon {
  daemon: string;
  barridos: BarridoDaemon[];
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
