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

// --- Economía por proceso (`GET /api/actividad/economia?dias=`) ---
//
// Gasto GLOBAL del ledger `gasto_ia` desglosado por motor (investigación/producción) y
// zero-filled a `dias`. NO se filtra por marca, así que cuadra EXACTO con la cola. En la
// página Economía sustituye al cruce de `actividad/agregados` (por marca) + `cola/series`
// (global) que no casaban entre sí.

/** Celda de gasto (items · tokens · coste) compartida por días y etapas. Los tokens van
 *  SEPARADOS en entrada (`tokens_in`) y salida (`tokens_out`) porque su coste es distinto (el
 *  output cuesta ~5x el input); `tokens` (=in+out) se mantiene para los consumidores que lo suman. */
export interface EconomiaCelda {
  items: number;
  tokens_in: number;
  tokens_out: number;
  tokens: number;
  coste_usd: number;
}

/** Gasto de una ETAPA (fase del pipeline: Redactar/Verificar/Ilustrar…) dentro de un día o de
 *  una pestaña. La deriva el back con `etapa_economia` (varios tipos del job colapsan en una
 *  fase), así que es un nombre legible, no el `tipo` crudo. */
export interface EconomiaEtapa extends EconomiaCelda {
  etapa: string;
}

/** Gasto de un día (`YYYY-MM-DD`, zero-filled), con su desglose por ETAPA (prompt) ese día. */
export interface EconomiaDia extends EconomiaCelda {
  dia: string;
  /** Desglose por etapa/prompt de ESE día (ordenado por coste desc). Para el colapsable. */
  por_etapa: EconomiaEtapa[];
}

/** Gasto de una ETAPA del periodo, con su desglose por DÍA (zero-filled, len == `dias`). */
export interface EconomiaEtapaConDias extends EconomiaEtapa {
  /** Desglose por día de ESA etapa (antiguo→reciente). Para el colapsable de la tabla por etapa. */
  por_dia: (EconomiaCelda & { dia: string })[];
}

/** Economía de UNA pestaña de Contexto: total del periodo + serie por día (con su desglose por
 *  etapa) + desglose por etapa (con su serie por día). */
export interface EconomiaProcesoBloque {
  total: EconomiaCelda;
  por_dia: EconomiaDia[];
  por_etapa: EconomiaEtapaConDias[];
}

/** Pestaña de Contexto que agrupa el gasto en la página Economía: los dos motores (ADR 0011) más
 *  Herramientas (agentes sueltos) y Desarrollo (auto-desarrollo). */
export type PestanaEconomia = "investigacion" | "produccion" | "herramientas" | "desarrollo";

/** Respuesta de `GET /api/actividad/economia`: un bloque por pestaña de Contexto. `marca` vacía =
 *  AGREGADO de todas; una marca acota el desglose a sus filas. */
export interface EconomiaPorProceso {
  dias: number;
  por_proceso: Partial<Record<PestanaEconomia, EconomiaProcesoBloque>>;
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
  /** A qué loop pertenece el job: investigación (verificación/verificación) o producción (copy/arte). */
  proceso: Proceso;
  gen_estado: string;
  fase: string;
  /** Prioridad de despacho (mayor = adelanta en la cola; manual > lote del pipeline). */
  prioridad: number;
  encolado_hace_s: number | null;
  corriendo_hace_s: number | null;
  /** Etapa legible del job (Verificar/Redactar/Ilustrar/Decisor/…). */
  etapa: string;
  /** Tamaño exacto del prompt en caracteres. */
  prompt_chars: number;
  /** Media histórica de tokens (in+out) de la etapa (null si aún no hay histórico). */
  tokens_estimados: number | null;
  /** Tokens IN reales EN VIVO (null si el job no corre o aún no ha reportado). */
  tokens_in: number | null;
  /** Tokens OUT reales EN VIVO (null si el job no corre o aún no ha reportado). */
  tokens_out: number | null;
  /** Coste USD real EN VIVO (null si el job no corre o aún no ha reportado). */
  coste_usd: number | null;
  /** `true` si el job es HUÉRFANO: su generación ya no existe, así que no se procesa. Opcional
   *  para compatibilidad con backs anteriores. */
  huerfano?: boolean;
}

/** Conteo pendientes/reclamados de un segmento de la cola (una marca, los huérfanos o una etapa).
 *  `reclamados` = jobs con `claude -p` corriendo (en curso); `pendientes` = esperando slot. */
export interface ConteoCola {
  pendientes: number;
  reclamados: number;
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

/** Economía de tokens de UN motor (investigación/producción): gasto del día desglosado in/out,
 *  con un tope diario INDEPENDIENTE por dirección (IN y OUT) y el % usado contra cada tope. */
export interface PresupuestoProcesoIA {
  tokens_in: number;
  tokens_out: number;
  /** in + out. */
  tokens: number;
  coste_usd: number;
  generaciones: number;
  /** Tope de tokens IN/día del motor (0 = sin límite). */
  presupuesto_tokens_in_dia: number;
  /** Tope de tokens OUT/día del motor (0 = sin límite). */
  presupuesto_tokens_out_dia: number;
  /** Tokens IN que restan del tope (null si tope IN = 0). */
  restante_in: number | null;
  /** % del tope IN consumido (null si tope IN = 0). */
  pct_in: number | null;
  /** Tokens OUT que restan del tope (null si tope OUT = 0). */
  restante_out: number | null;
  /** % del tope OUT consumido (null si tope OUT = 0). */
  pct_out: number | null;
  /** Nivel de corte del motor ("normal" | "solo_manual" | "agotado" | …). */
  nivel: string;
}

/** Gate DIARIO por % del límite SEMANAL POR CUENTA de Claude (hay dos cuentas, A/B; cada una con su
 *  cupo semanal). Pausa la generación de las marcas de SU cuenta (auto y manual) cuando el consumo
 *  del día de esa cuenta alcanza su umbral vigente; aceptar +10% sube el umbral del día de la cuenta
 *  y reanuda sus marcas. Es la razón de un `nivel == "pausado"` (en la vista de una marca de esa
 *  cuenta) con `pausada` (kill switch) en false. */
export interface GateDiarioIA {
  /** Cuenta de Claude a la que pertenece este bloque ("a" | "b"): a quién aplica el aviso y el
   *  «Aceptar +10%». */
  cuenta: string;
  /** Puntos porcentuales del límite semanal de la cuenta consumidos HOY (UTC). null mientras la
   *  fuente del % no exista (rollout): con null el gate está inerte y `pausado_por_pct` es false. */
  consumo_hoy_pct: number | null;
  /** Umbral vigente del día (puntos porcentuales del semanal): base ~14,3 + 10 por cada aceptar. */
  umbral_pct: number;
  /** Cuántos "+10%" se han aceptado HOY (UTC). */
  aceptados_hoy: number;
  /** True si el consumo del día alcanza el umbral => generación pausada por consumo del día. */
  pausado_por_pct: boolean;
  /** Umbral base del día (un séptimo del semanal, ~14,3). */
  base_umbral_pct: number;
  /** Cuánto sube el umbral cada aceptar (10). */
  paso_pct: number;
  /** Día UTC del estado (YYYY-MM-DD). */
  dia: string;
}

/** Economía de tokens (`presupuesto_ia.estado()`): presupuesto diario, gasto y nivel. */
export interface PresupuestoIA {
  /** Ámbito del snapshot: "" = GLOBAL (todas las marcas); un id = controles PROPIOS de esa marca. */
  marca?: string;
  /** Nivel de corte vigente: "normal" | "solo_manual" | "agotado" | "pausado". */
  nivel: string;
  /** Kill switch humano (KENI_GENERACION_PAUSADA, editable en caliente). */
  pausada: boolean;
  /** Ritmo de producción (%) del ÁMBITO de marca (10..100; 100 = normal). */
  ritmo: number;
  /** Ritmo de producción (%) GLOBAL (10..100; 100 = normal). */
  ritmo_global: number;
  /** Presupuesto de tokens/día (0 = sin límite). */
  presupuesto_tokens_dia: number;
  /** Presupuesto de coste (USD)/día (0 = sin límite). Corta el más restrictivo de tokens/coste. */
  presupuesto_usd_dia: number;
  margen_manual_pct: number;
  gastado: GastoIADia;
  /** null si no hay presupuesto de tokens configurado. */
  restante_tokens: number | null;
  /** % del presupuesto de tokens consumido (null sin presupuesto de tokens). */
  pct_usado: number | null;
  /** % del presupuesto de coste (USD) consumido (null sin presupuesto de USD). */
  pct_usado_usd: number | null;
  /** Proyección de gasto (USD) a fin de día (coste actual / fracción del día transcurrida).
   *  null al arranque del día (fracción <= 1%), cuando extrapolar dispararía la cifra. */
  proyeccion_usd_dia: number | null;
  /** % del cap de USD que la proyección alcanzaría (null sin cap o sin proyección). */
  pct_proyectado_usd: number | null;
  /** Día UTC del acumulado (YYYY-MM-DD). */
  dia: string;
  /** Desglose por motor (investigación/producción): gasto in/out + tope propio. Opcional para
   *  compatibilidad con backs anteriores (durante el rollout puede no venir). */
  por_proceso?: Partial<Record<Proceso, PresupuestoProcesoIA>>;
  /** Gate diario por % del límite semanal de la CUENTA de esta marca (su aviso/«Aceptar +10%»).
   *  null en la vista global ("Todas", sin cuenta concreta). Opcional para compatibilidad con backs
   *  anteriores (durante el rollout puede no venir). */
  gate_diario?: GateDiarioIA | null;
  /** Gate diario por % de TODAS las cuentas (`{a, b}`): lo usa el modo "Todas" del selector para
   *  pintar el aviso de cada cuenta que esté gateada. Opcional para compatibilidad con backs
   *  anteriores. */
  gate_diario_cuentas?: Record<string, GateDiarioIA>;
}

/** Conteo del pool COMPARTIDO atribuible a un proceso (jobs en curso de ese loop). */
export interface ConteoProceso {
  /** Jobs reclamados (claude -p corriendo) de este proceso. */
  procesando: number;
  /** Jobs pendientes (esperando slot) de este proceso. */
  pendientes: number;
}

/** Admisión de verificación: el único límite que Investigación acota aparte de la cola compartida. */
export interface AdmisionVerificacion {
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
  /** Conteo de la MARCA filtrada (cuadra con `len(esperando)`/`len(en_curso)`). Llega solo cuando
   *  la petición lleva `?marca=`; `null` sin filtro (entonces manda `conteo`, que es global).
   *  Opcional para compatibilidad con backs anteriores. */
  conteo_marca?: ConteoCola | null;
  /** Parte del conteo GLOBAL que no pertenece a ninguna marca: jobs cuya generación ya no existe
   *  (no se procesan). Opcional para compatibilidad con backs anteriores. */
  huerfanos?: ConteoCola;
  cola_llena: boolean;
  procesando: number;
  slots_libres: number;
  workers_activos: string[];
  /** Desglose del pool compartido por proceso (ADR 0011): los dos loops sobre la misma cola. */
  por_proceso?: Record<Proceso, ConteoProceso>;
  /** Estado del admision de verificación (Investigación). */
  admision_verificacion?: AdmisionVerificacion;
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

/** Respuesta de priorizar un job esperando (admin). Incluye la prioridad aplicada. */
export interface RespuestaPriorizarCola {
  priorizado: boolean;
  gen_id: string;
  /** Prioridad aplicada al job (presente cuando el back la fija). */
  prioridad?: number;
}

/** Respuesta de eliminar un job de la cola (admin). */
export interface RespuestaEliminarCola {
  eliminado: boolean;
  gen_id: string;
}

/** Desglose de UNA marca en la cola: ambos procesos (siempre presentes) + su total. La marca de
 *  feed (sin id) llega como `marca: ""`. */
export interface ColaDesgloseMarca {
  marca: string;
  por_proceso: Record<Proceso, ConteoCola>;
  total: ConteoCola;
}

/** Foto completa de la cola por marca×proceso×estado (`GET /api/actividad/cola/desglose`, sin
 *  filtro). `marcas` ordenado por id; `huerfanos` es la parte sin marca (generación inexistente). */
export interface ColaDesglose {
  marcas: ColaDesgloseMarca[];
  huerfanos: ConteoCola;
}

/** Preview por marca de cuántos temas entrarían a la etapa Redactar (copy) SI esa marca estuviera ON. */
export interface ColaPreviewMarca {
  marca: string;
  redactar: number;
}

/** Respuesta de `GET /api/actividad/cola/preview` (no encola nada). */
export interface ColaPreview {
  marcas: ColaPreviewMarca[];
}

/** Respuesta de `POST /api/actividad/cola/limpiar-huerfanos` (admin). */
export interface RespuestaLimpiarHuerfanos {
  huerfanos_limpiados: number;
}

/** Una línea del plan editorial diario: generados/publicados vs objetivo en la ventana. */
export interface ProduccionLinea {
  /** Clave del plan: id de línea (etiqueta categoria) o señal del motor ('breaking'/'evergreen'). */
  categoria: string;
  /** Nombre legible de la línea (o "Última hora"/"Evergreen"). */
  etiqueta?: string;
  generados: number;
  publicados: number;
  objetivo: number | null;
}

/** Resumen mínimo de /api/produccion/dia que consume el Monitor (líneas del plan). */
export interface ProduccionDia {
  marca: string;
  objetivo: { plan: Record<string, number> | null };
  por_categoria: ProduccionLinea[];
}

/** Las 6 etapas del backlog en ORDEN DE CADENA (entrada → salida): el embalse que precede a la
 *  cola de jobs. Siempre las 6 presentes. */
export interface BacklogEtapas {
  /** [A] Noticias recolectadas (RSS/radar) aún sin entrar al tablero. */
  pool_sin_admitir: number;
  /** [B] Temas admitidos esperando verificación o copy. */
  pipeline_en_proceso: number;
  /** [C] Temas del tablero SIN copy esperando a «Generar copy»: la cola oculta que entra de golpe. */
  esperando_copy: number;
  /** [D1] Copy encolado o en curso. */
  generando_copy: number;
  /** [D2] Con copy, esperando ilustración. */
  generando_arte: number;
  /** [E] Completas, ya en la parrilla/revisión. */
  lista_para_revisar: number;
}

/** Backlog de UNA marca: las 6 etapas de la cadena + su total (suma de las 6). */
export interface BacklogMarca {
  marca: string;
  /** Nombre legible de la marca. */
  nombre: string;
  etapas: BacklogEtapas;
  total: number;
}

/** Foto completa del backlog por marca × etapa (`GET /api/produccion/backlog`, sin filtro).
 *  `marcas` ordenado por id; el embalse que se acumula ANTES de la cola de jobs. */
export interface Backlog {
  marcas: BacklogMarca[];
}

// --- Pipelines (vista estilo GitLab del pipeline de contenido CI/CD) ---

/** Una etapa de una run del pipeline (CI/CD/verificación/Aprobación). */
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
  revision: string;
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

/** Verificación ESTRUCTURADA de la fuente (pre-copy): `verificado` (✅ confirmada), `requiere_humano`
 *  (⚠️ la IA no pudo confirmar: sin copy, a la mesa) o `rechazado` (❗ falso/de peso: sin copy). */
export interface PipelineVerificacionFuente {
  verificacion_fuente: string;
  verificado: boolean;
  requiere_humano: boolean;
  rechazado: boolean;
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
  verificacion?: PipelineVerificacionFuente | null;
  /** Procedencia IA (historia/cluster) del tema. `null` si no nació de una historia. */
  cluster?: PipelineCluster | null;
  /** Tokens/coste/duración sumados de sus generaciones. Opcional (backs previos). */
  metricas?: PipelineMetricas;
  piezas: PipelinePieza[];
  /** Solo items sueltos: ruta del SPA al resultado de la generación (si su tipo tiene página). */
  resultado_url?: string | null;
}

/** Un tema BLOQUEADO del pipeline (`GET /api/pipelines/problemas`): tras agotar reintentos
 *  (o una verificación de peso) queda con verificacion `problema` y SALE del flujo; esta forma lo hace
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
 *  Lo expone el detalle del pipeline por código de etapa (CI/CD/verificación): `salida` es el texto
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

/** Una generación concreta dentro de una etapa de la línea de tiempo (cronológico, para expandir
 *  intento a intento). `coste_usd`/`tokens` son `null` si la generación no los registró. */
export interface LineaTiempoGen {
  gen_id: string;
  estado: string;
  fecha: string;
  coste_usd: number | null;
  tokens: number | null;
}

/** Una entrada por ETAPA de la línea de tiempo unificada de un post: TODA la actividad real del
 *  mismo `publicacion_id` con los reintentos COLAPSADOS (una entrada por etapa+post). La lista ya
 *  viene ORDENADA por el flujo del pipeline; `fase_previa=true` marca lo ocurrido ANTES del tablero
 *  (pool, a nivel marca). "Decisor · 3 intentos · Error" se arma de `etapa`+`intentos`+`estado_final`. */
export interface LineaTiempoEtapa {
  /** Etiqueta legible de la etapa (Recolectar, Fusionar, Decisor, Admitir, …). */
  etapa: string;
  /** Nº de generaciones colapsadas de esa etapa+post. */
  intentos: number;
  /** Estado de la última generación (terminal de la etapa). */
  estado_final: string;
  ultima_gen_id: string;
  primera_fecha: string;
  ultima_fecha: string;
  /** `true` = antes del tablero (pool, nivel marca). */
  fase_previa: boolean;
  /** Generaciones en orden cronológico, para expandir intento a intento. */
  generaciones: LineaTiempoGen[];
}

export interface RespuestaPipelineDetalle {
  pipeline: Pipeline;
  actividad: PipelineActividad[];
  /** Stream del agente por código de etapa ("FUSION"/"EDITORIAL"/"verificación"/"CD"/"ARTE"). {} si no hay. */
  generaciones_por_etapa?: Record<string, PipelineGeneracion>;
  /** Plantilla del prompt de cada etapa IA (para enseñar el prompt de entrada aunque no haya
   *  corrido aún; cuando corre, se prefiere el prompt real de la generación). */
  prompts_por_etapa?: Record<string, string>;
  /** Línea de tiempo unificada por post: TODA la actividad real (incl. el Decisor) por etapa, con
   *  los reintentos colapsados; ya ordenada por el flujo del pipeline. Aditivo. */
  linea_tiempo?: LineaTiempoEtapa[];
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

/** Estado agregado de un daemon, calculado por el back. `en_espera` = su interruptor propio
 *  está ON pero la máquina de contenido está apagada (no corre, pero no es un fallo). */
export type EstadoDaemon = "ok" | "error" | "inactivo" | "atrasado" | "en_espera";

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
   *  se les ofrece «Barrer ahora». Los bucles legados (metricas/comercial/…) no lo miran. */
  barrible: boolean;
  /** Grupo (motor/papel) al que pertenece el daemon; agrupa el dashboard de Workers. */
  grupo: GrupoDaemon;
  /** Clase afinada del daemon (`ia`|`maquina`|`sistema`); contrato ADITIVO sobre `grupo`. */
  clase: ClaseDaemon;
  /** Motor de la máquina al que pertenece (`investigacion`|`produccion`) o `null` si es infra. */
  motor: MotorDaemon;
  /** `true` si el daemon encola/ejecuta `claude -p` (gasta tokens); `false` el resto. */
  gasta_tokens: boolean;
  /** Nombre humano del daemon para el panel (cae al nombre crudo capitalizado si no está mapeado).
   *  Lo da el backend (`latidos.etiqueta_de`); el front ya no hardcodea el mapeo. */
  etiqueta: string;
  /** Frase de PARA QUÉ SIRVE el daemon (`latidos.descripcion_de`); "" si no está descrito.
   *  La consumen tanto el panel (línea bajo la etiqueta) como el bloque de descripción de la
   *  página de detalle: un solo campo, una sola fuente. */
  descripcion: string;
  /** Resumen del último barrido (qué hizo / nº items) o "" si no aportó: distingue de un vistazo
   *  "corre y TRABAJA" de "corre EN VACIO". Lo da el backend (`daemon_latidos.ultimo_resumen`). */
  ultimo_resumen: string;
  /** Prompts de la Prompts que gobiernan este agente IA (lo que el panel ofrece editar
   *  in-place); `[]` si no es IA. Lo da el backend (`latidos.prompts_de`). */
  prompts: PromptDaemon[];
  /** Clave de ajuste (KENI_*) que enciende/apaga el daemon desde su fila (toggle in-place;
   *  pásala a `POST /api/ajustes`). `null` = SIEMPRE-ON sin toggle (limpiador/metricas/…). */
  clave_gate: string | null;
  /** Valor GUARDADO de ese flag propio (lo que el SWITCH refleja), SIN ANDearlo con la máquina:
   *  así el switch sigue encendido aunque la máquina esté apagada (estado `en_espera`). `null` =
   *  siempre-on (sin gate). Distinto de `activo` (efectivo = flag propio AND máquina). */
  gate_activo: boolean | null;
  /** Ajustes del catálogo que gobiernan el daemon (editables in-place en su detalle); `[]` si ninguno. */
  ajustes: AjusteAdmin[];
}

/** Un prompt de la Prompts que gobierna un agente IA (etiqueta visible + id de documento). */
export interface PromptDaemon {
  etiqueta: string;
  doc: string;
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
  /** "GET /api/publicaciones/{id}" (método + ruta con ids colapsados). */
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

// ── Cuenta de Claude (panel admin: estado de auth + uso + cambio de cuenta) ──────────────
//
// La generación corre `claude -p` con la cuenta de Claude del servidor. Esta sección la
// gestiona desde el panel: ve el estado de auth y el medidor de uso (suscripción), y permite
// CAMBIAR de cuenta (logout + login interactivo: URL → pegar código). El back proxea al
// control del proceso `daemons` (quien tiene `claude`); ver `api/sistema/cuenta.py`.

/** Estado de autenticación (`claude auth status --json`). */
export interface CuentaAuth {
  /** ¿Hay sesión iniciada? null = desconocido (el CLI no respondió como se esperaba). */
  logueado: boolean | null;
  /** Método de auth: "claude.ai" (login de suscripción) | "api_key" | … */
  metodo: string | null;
  /** Proveedor: "firstParty" (suscripción) | "console" (API) | … */
  proveedor: string | null;
  /** Email de la cuenta conectada (solo con login por credenciales; null si no). */
  email?: string | null;
  /** Tipo de suscripción ("max", "pro", …) o null. */
  plan?: string | null;
  /** Organización de la cuenta o null. */
  org?: string | null;
  /** Salida cruda del CLI (diagnóstico). */
  crudo?: string;
  /** Error legible si no se pudo leer el estado. */
  error?: string;
}

/** Un medidor del `/usage` (sesión 5h / semana / …). */
export interface MedidorUso {
  /** Etiqueta tal cual la da el CLI ("Current session", "Current week (all models)", …). */
  etiqueta: string;
  /** Porcentaje usado (0–100). */
  pct: number;
  /** Texto crudo del reset tal cual lo da el CLI ("Jun 15 at 7:39pm (UTC)"), en la zona del
   *  servidor (UTC); fallback si no se pudo parsear a instante. Null si no hay reset. */
  reset: string | null;
  /** Instante UTC ISO del reset ("2026-06-15T01:39:00Z"), parseado por el backend para
   *  mostrarlo en la zona de display del usuario. Null si el CLI no trajo reset o no se parseó. */
  reset_iso?: string | null;
}

/** Medidor de uso de la suscripción (`claude -p /usage`). */
export interface CuentaUso {
  /** `true` si hay medidores que mostrar (frescos o del cache); `false` solo si nunca hubo. */
  disponible: boolean;
  /** Frase de cabecera ("You are currently using your subscription…"). */
  mensaje: string;
  /** Medidores parseados (vacío si `disponible` es false). */
  medidores: MedidorUso[];
  /** `true` si los medidores vienen del CACHE (la lectura actual no traía medidor). */
  cacheado?: boolean;
  /** Epoch (segundos) de cuándo se capturó el medidor mostrado. */
  actualizado?: number | null;
  crudo?: string;
  error?: string;
}

/** Respuesta de `GET /api/sistema/cuenta`. */
export interface RespuestaCuenta {
  /** `false` si la gestión de cuenta no está configurada en este servidor. */
  disponible: boolean;
  auth?: CuentaAuth;
  uso?: CuentaUso;
  error?: string;
}

/** Respuesta de `POST /api/sistema/cuenta/login/iniciar`. */
export interface RespuestaLoginIniciar {
  /** Id de la sesión de login viva (se devuelve al pegar el código). */
  sesion?: string;
  /** URL de autorización a abrir en el navegador. */
  url?: string;
  /** Salida capturada del CLI (diagnóstico). */
  salida?: string;
  /** Error legible si no se obtuvo la URL. */
  error?: string;
}

/** Respuesta de `POST /api/sistema/cuenta/login/codigo` y `/logout`. */
export interface RespuestaCuentaAccion {
  ok: boolean;
  mensaje?: string;
  salida?: string;
}

// ── Reparto de marcas por cuenta de Claude (panel admin) ─────────────────────────────────
//
// Cada marca se sirve desde una de las dos cuentas de Claude del servidor (A/B). Hay un mapeo
// por defecto; el admin puede fijar un override por marca (moverla a la otra cuenta) o limpiarlo
// para volver al defecto. `GET`/`POST /api/sistema/cuenta-marcas` (admin); ver `api/sistema/cuenta_marcas.py`.

/** Una cuenta de Claude en el reparto: su selector ('a'|'b') y su etiqueta legible. */
export interface CuentaMarcaCuenta {
  /** Selector de la cuenta ('a' | 'b'). */
  cuenta: string;
  /** Nombre legible de la cuenta (p. ej. "Claro Sports", "UnoTV · …"). */
  etiqueta: string;
}

/** Asignación efectiva de UNA marca a una cuenta. */
export interface CuentaMarcaAsignacion {
  /** Id canónico de la marca. */
  id: string;
  /** Nombre legible de la marca. */
  nombre: string;
  /** Cuenta efectiva actual de la marca ('a' | 'b'). */
  cuenta: string;
  /** `true` si usa el mapeo por defecto (sin override explícito). */
  por_defecto: boolean;
}

/** Respuesta de `GET`/`POST /api/sistema/cuenta-marcas`: el reparto marca→cuenta. */
export interface RespuestaCuentaMarcas {
  /** Las cuentas disponibles, con su etiqueta. */
  cuentas: CuentaMarcaCuenta[];
  /** Cuenta por defecto (la que sirve lo no repartido). */
  defecto: string;
  /** Asignación efectiva de cada marca. */
  marcas: CuentaMarcaAsignacion[];
}

// ── Proveedor GitHub (panel admin: auth de `gh` del servidor, gemelo de la cuenta de Claude) ──
//
// El motor de auto-desarrollo empuja a GitHub con la credencial `gh` del servidor (volumen
// compartido `/data/gh`). Esta sección la gestiona desde el panel: estado de la sesión y
// conectar/desconectar vía device flow de `gh` (one-time code + URL; gh hace polling solo, no
// hay que pegar el código de vuelta). El back proxea al control del proceso `daemons`; ver
// `api/sistema/github.py`.

/** Estado de autenticación de `gh` (`gh auth status`). */
export interface GithubAuth {
  /** ¿Hay sesión iniciada? */
  logueado: boolean;
  /** Usuario de GitHub conectado, si lo hay. */
  usuario?: string | null;
  /** Scopes del token (`gh auth status` los lista). */
  scopes?: string[];
}

/** Respuesta de `GET /api/sistema/github`. */
export interface RespuestaGithub {
  /** `false` si la gestión de GitHub no está configurada en este servidor. */
  disponible: boolean;
  auth: GithubAuth;
}

/** Respuesta de `POST /api/sistema/github/login/iniciar` (device flow de `gh`). */
export interface RespuestaGithubLoginIniciar {
  /** Id de la sesión de login viva (se pasa a confirmar/cancelar). */
  sesion: string;
  /** One-time code que el usuario teclea en GitHub. */
  codigo: string;
  /** URL a abrir para introducir el código (https://github.com/login/device). */
  url: string;
  /** Salida capturada del CLI (diagnóstico). */
  salida: string;
}
