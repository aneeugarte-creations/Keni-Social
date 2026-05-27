/**
 * GENERADO — NO EDITAR A MANO.
 *
 * Tipos DERIVADOS del backend (subconjunto estable del contrato `/api/*`).
 * Fuente: `keni_consola.esquema_api` (Python). Regenerar con `npm run gen:types`.
 * El guard `npm run gen:types:check` (y el test del backend) falla si esto se
 * desincroniza del backend. El resto de tipos vive a mano en `types.ts`. Ver #101.
 */

export interface ResultadoEstado {
  estado: "ok" | "aviso" | "error";
  nombre: string;
  detalle: string;
  icono: string;
}
export interface RespuestaEstado {
  resultados: ResultadoEstado[];
  resumen: string;
  siguiente_paso: string;
}
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
/**
 * Limite de caracteres canonico de una red (fuente unica, `GET /api/limites`).
 *
 * `limite` es `null` si la red no tiene tope tecnico practico (Facebook/YouTube).
 */
export interface LimiteRed {
  id: string;
  nombre: string;
  limite: number | null;
}
/**
 * Respuesta de `GET /api/limites`: los limites por red, en orden fijo.
 */
export interface RespuestaLimites {
  limites: LimiteRed[];
}
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
/**
 * Respuesta de `GET /api/metricas/reporte`.
 */
export interface ReporteMetricas {
  rango: string;
  etiqueta_rango: string;
  marca: string;
  fuente: string;
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
export interface TotalComparativa {
  metricas: ComparativaMetrica[];
}
/**
 * Respuesta de `GET /api/metricas/comparar`: comparativa A vs B.
 */
export interface CompararMetricas {
  marca: string;
  rango_a: string;
  rango_b: string;
  etiqueta_a: string;
  etiqueta_b: string;
  fuente: string;
  total: TotalComparativa;
  por_marca: ComparativaPorMarca[];
}
/**
 * Envelope ADITIVO de paginacion (offset-based, #121).
 *
 * Lo añaden los listados pesados (publicaciones/runs/generaciones) junto a su
 * clave de lista. `total` = filas existentes sin paginar; `limite` = tamaño de
 * pagina efectivo (igual a `total` si no se paginó); `desplazamiento` = offset.
 */
export interface Paginacion {
  total: number;
  limite: number;
  desplazamiento: number;
}
/**
 * Metricas de monitorizacion de un run/generacion IA (las que reporta el CLI).
 *
 * El handler las omite (clave a `null`) si el run no produjo metricas (interactivo
 * o CLI sin JSON). Cuando vienen, traen estos seis campos.
 */
export interface MetricasRun {
  tokens_in: number;
  tokens_out: number;
  num_turns: number;
  total_cost_usd: number;
  duration_ms: number;
  modelo: string;
}
/**
 * Una publicacion serializada (`dominio.publicaciones.publicacion_a_dict`).
 *
 * `marca_nombre`/`red_nombre` se resuelven en servidor. `imagen` es el nombre de
 * archivo ("" si no hay) e `imagen_url` su ruta servible ("" si no hay).
 */
export interface Publicacion {
  id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  red: string;
  red_nombre: string;
  contenido: string;
  estado: "borrador" | "aprobado" | "programado" | "publicado";
  veredicto: "listo" | "revisar" | "no_publicar" | "";
  fecha_creacion: string;
  fecha_actualizacion: string;
  fecha_programada: string;
  origen: string;
  imagen: string;
  imagen_url: string;
  evergreen: boolean;
}
/**
 * Listado de `GET /api/publicaciones` con el envelope de paginacion (#121).
 */
export interface RespuestaPublicaciones {
  publicaciones: Publicacion[];
  paginacion: Paginacion;
}
/**
 * Respuesta de los endpoints que devuelven UNA publicacion (`{publicacion}`).
 */
export interface RespuestaPublicacion {
  publicacion: Publicacion;
}
/**
 * Un run (ejecucion) de un agente, en su forma publica.
 *
 * Forma CANONICA: la de `agentes._parsear_run` (`GET .../runs/{id}` y el listado
 * `GET .../runs`): `id/prompt/modo/estado/motivo/fecha_inicio/metricas` + la
 * `salida` y `fecha_fin` del run completo. El LISTADO GLOBAL (`GET /api/runs`) y
 * el detalle del agente omiten `salida`/`fecha_fin` y, el global, AÑADE
 * `agente`/`agente_nombre`: por eso esos cuatro van como `NotRequired`. `metricas`
 * es `null` si el run no produjo metricas.
 */
export interface Run {
  id: string;
  prompt: string;
  modo: string;
  estado: string;
  motivo: string;
  fecha_inicio: string;
  metricas: MetricasRun | null;
  salida?: string;
  fecha_fin?: string;
  agente?: string;
  agente_nombre?: string;
}
/**
 * Respuesta de los endpoints que devuelven UN run (`{run}`).
 *
 * `mensaje` solo lo añade el lanzamiento INTERACTIVO (`POST .../runs` con modo
 * `interactivo`): el texto legible del lanzamiento; ausente en el resto.
 */
export interface RespuestaRun {
  run: Run;
  mensaje?: string;
}
/**
 * Listado de runs. El global (`GET /api/runs`) trae `paginacion`; el del agente
 * (`GET /api/agentes/{id}/runs`) no, por eso es `NotRequired`.
 */
export interface RespuestaRuns {
  runs: Run[];
  paginacion?: Paginacion;
}
export interface TotalRuns {
  coste_usd: number;
  tokens: number;
  runs: number;
}
export interface AgregadoPorAgente {
  agente: string;
  agente_nombre: string;
  coste_usd: number;
  tokens: number;
  runs: number;
}
export interface AgregadoPorDia {
  dia: string;
  coste_usd: number;
  tokens: number;
  runs: number;
}
/**
 * Respuesta de `GET /api/runs/agregados`: totales de coste/tokens/runs.
 */
export interface RespuestaRunsAgregados {
  total: TotalRuns;
  por_agente: AgregadoPorAgente[];
  por_dia: AgregadoPorDia[];
}
/**
 * Valor actual de una pieza comercial (del ultimo snapshot).
 */
export interface ActualComercial {
  ts: string;
  interacciones: number;
  alcance: number;
  engagement_pct: number;
}
/**
 * Un punto de la serie temporal de una pieza comercial (acumulado).
 */
export interface SnapshotComercial {
  ts: string;
  interacciones: number;
  alcance: number;
}
/**
 * Una pieza comercial monitoreada (`api/comercial._a_dict`).
 *
 * `fuente`/`es_muestra` (#124) marcan la procedencia de las cifras. `serie` solo
 * viene en el detalle / al crear (`con_serie=True`), por eso es `NotRequired`.
 */
export interface PublicacionComercial {
  id: string;
  url: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  cliente: string;
  campania: string;
  red: string;
  red_nombre: string;
  metrica_objetivo: "interacciones" | "alcance";
  objetivo: number;
  estado: "activa" | "pausada" | "cerrada";
  publicado: string;
  notas: string;
  aviso_en: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
  actual: ActualComercial;
  progreso_pct: number;
  alcanzado: boolean;
  fuente: string;
  es_muestra: boolean;
  serie?: SnapshotComercial[];
}
/**
 * Listado de `GET /api/comercial/publicaciones` con procedencia comun (#124).
 */
export interface RespuestaPublicacionesComercial {
  publicaciones: PublicacionComercial[];
  fuente: string;
  es_muestra: boolean;
}
/**
 * Respuesta de los endpoints que devuelven UNA pieza comercial (`{publicacion}`).
 */
export interface RespuestaPublicacionComercial {
  publicacion: PublicacionComercial;
}
/**
 * Respuesta de `POST /api/comercial/refrescar`: nº de piezas actualizadas.
 */
export interface RespuestaRefrescarComercial {
  actualizadas: number;
}
export interface RespuestaMensaje {
  mensaje: string;
}
/**
 * Forma de error que devuelve el backend (uno u otro campo, en espanol).
 */
export interface ErrorApi {
  error?: string;
  mensaje?: string;
}
