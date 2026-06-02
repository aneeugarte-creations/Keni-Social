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
  generado_en: string;
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
  generado_en: string;
}
/**
 * Pieza que explica un movimiento (o que apuntala el siguiente paso).
 */
export interface PiezaAnalisis {
  titulo: string;
  plataforma: string;
  engagement_pct: number;
  url: string | null;
}
/**
 * Un movimiento del periodo: qué se movió y la pieza que lo explica.
 */
export interface MovimientoAnalisis {
  marca_id: string;
  marca: string;
  variacion_vis_pct: number;
  direccion: string;
  visualizaciones: number;
  engagement_pct: number | null;
  pieza: PiezaAnalisis | null;
}
/**
 * Sugerencia accionable que cierra el loop a la acción (UX-roadmap #11).
 */
export interface SiguientePasoAnalisis {
  marca_id: string;
  marca: string;
  engagement_pct: number | null;
  pieza: PiezaAnalisis | null;
  texto: string;
}
/**
 * Respuesta de `GET /api/metricas/analisis`: lectura "qué cambió y por qué".
 *
 * Capa narrativa (F6/#146) sobre las métricas: top movimientos con la(s) pieza(s)
 * que los explican y un siguiente paso. `es_muestra`/`fuente` marcan cuando los
 * datos son de muestra y no reales (issue #131).
 */
export interface AnalisisDiario {
  rango: string;
  etiqueta_rango: string;
  marca: string;
  fuente: string;
  es_muestra: boolean;
  movimientos: MovimientoAnalisis[];
  movimientos_resto: number;
  marcas_estables: number;
  cobertura_parcial: string[];
  siguiente_paso: SiguientePasoAnalisis | null;
  generado_en: string;
}
/**
 * Respuesta de `GET /api/metricas/estado` y `POST /api/metricas/refrescar`.
 *
 * Estado del refresco de la cache de métricas (en 2º plano) + "última actualización"
 * del combo consultado. La UI lo usa para el botón Actualizar (spinner mientras
 * `corriendo`) y para el polling (deja de pollear cuando `corriendo` pasa a false).
 */
export interface EstadoMetricas {
  corriendo: boolean;
  iniciado_en: string;
  terminado_en: string;
  ultimo_error: string;
  generado_en: string;
}
/**
 * Ventana de fechas (ISO) de un periodo de métricas.
 */
export interface PeriodoMetricas {
  desde: string;
  hasta: string;
}
/**
 * Resumen estadístico de una serie (engagement o visualizaciones por pieza).
 *
 * Todos los campos salvo `n` son `null` cuando no hay datos suficientes (la
 * desviación necesita n>=2): la UI distingue "0" de "sin dato".
 */
export interface EstadisticasNumericas {
  n: number;
  media: number | null;
  mediana: number | null;
  p25: number | null;
  p75: number | null;
  minimo: number | null;
  maximo: number | null;
  desviacion: number | null;
}
/**
 * Una pieza/video del periodo (fila de top/peores).
 */
export interface PiezaMetrica {
  id: string;
  plataforma: string;
  titulo: string;
  publicado: string;
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
  url: string | null;
}
/**
 * Un tramo del histograma de engagement (cuántas piezas caen en [inicio, fin)).
 */
export interface DistribucionBucket {
  etiqueta: string;
  inicio: number;
  fin: number | null;
  n: number;
}
/**
 * Respuesta de `GET /api/metricas/piezas`: estadísticas + top/peores + distribución.
 *
 * `cuenta` es `null` cuando agrega todas las marcas (tab "Todas"). Coste 0 de API:
 * se construye sobre las piezas que el reporte ya descarga del periodo.
 */
export interface AnaliticaPiezas {
  cuenta: string | null;
  rango: string;
  etiqueta_rango: string;
  periodo: PeriodoMetricas;
  total: number;
  fuente: string;
  engagement: EstadisticasNumericas;
  visualizaciones: EstadisticasNumericas;
  top: PiezaMetrica[];
  peores: PiezaMetrica[];
  distribucion: DistribucionBucket[];
  generado_en: string;
}
/**
 * Un día de la serie temporal: totales del día.
 */
export interface PuntoSerie {
  fecha: string;
  visualizaciones: number;
  interacciones: number;
}
/**
 * Respuesta de `GET /api/metricas/tendencia`: evolución diaria del periodo.
 *
 * `puntos` vacío = la fuente activa no expone serie diaria (degradación honesta).
 */
export interface TendenciaDiaria {
  cuenta: string | null;
  rango: string;
  etiqueta_rango: string;
  periodo: PeriodoMetricas;
  fuente: string;
  puntos: PuntoSerie[];
  generado_en: string;
}
/**
 * Una pieza YA PUBLICADA del tablero con su rendimiento REAL (drill-down marca->pieza).
 *
 * A diferencia de `PiezaMetrica` (mejores/peores del periodo descubiertas desde la
 * lista de posts), esto es el rendimiento de una pieza CONCRETA que el equipo publicó
 * desde la Consola, leído de Metricool por su `id_post_metricool`. `contenido_id` enlaza
 * a la pieza en el tablero (`/parrilla/pendientes`). `encontrado=False` => Metricool aún
 * no tiene datos (recién publicada): la UI muestra "sin datos todavía", no ceros falsos.
 */
export interface PiezaRendimiento {
  contenido_id: string;
  plataforma_id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  red: string;
  id_post_metricool: string;
  encontrado: boolean;
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
  url: string | null;
  publicado: string | null;
  fuente: string;
  generado_en: string;
}
/**
 * Respuesta de `GET /api/metricas/piezas-rendimiento`: drill-down marca -> pieza.
 *
 * Lista las piezas publicadas (con `id_post_metricool`) y su rendimiento REAL, leído de
 * la MISMA fuente única (Metricool) que el dashboard y las tarjetas del tablero, sin
 * desfase. Ordenadas por engagement desc (las "sin datos" al final).
 */
export interface PiezasRendimiento {
  marca: string;
  fuente: string;
  total: number;
  piezas: PiezaRendimiento[];
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
 * `autor_id`/`autor_nombre` (atribucion por usuario, #130 Fase 1) identifican a quien
 * creo la pieza; "" en piezas legadas/anonimas (la UI las muestra como "desconocido").
 *
 * Flujo de aprobacion de equipo (#9, Fase 3): `enviado_a_revision_en`/`revisor_id`/
 * `revisor_nombre`/`revisado_en` registran quien la envio/reviso y cuando; "" mientras
 * no haya pasado por revision (incluidas las piezas legadas). `preparado_en` es la marca
 * DRY-RUN del programador (instante en que quedo "lista para publicar"; el posteo real
 * via Metricool esta gated por `KENI_PUBLICAR_REAL`); "" hasta que vence su `fecha_programada`.
 */
export interface Publicacion {
  id: string;
  contenido_id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  red: string;
  red_nombre: string;
  contenido: string;
  copy_in: string;
  estado: "borrador" | "en_revision" | "aprobado" | "programado" | "publicado";
  veredicto: string;
  autor_id: string;
  autor_nombre: string;
  enviado_a_revision_en: string;
  revisor_id: string;
  revisor_nombre: string;
  revisado_en: string;
  preparado_en: string;
  id_post_metricool: string;
  tipo_contenido: string;
  imagen_fuente: string;
  foto: string;
  falta_copy: boolean;
  falta_imagen: boolean;
  falta_revision: boolean;
  falta_publicar: boolean;
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
 * Cola de aprobacion (`GET /api/aprobacion/cola`): piezas en revision, FIFO.
 *
 * Cada item es una `Publicacion` completa (incluye `autor_nombre`/
 * `enviado_a_revision_en`: quien la envio y desde cuando espera). `total` = nº en cola.
 */
export interface RespuestaColaAprobacion {
  cola: Publicacion[];
  total: number;
}
/**
 * Total consolidado de metricas para el panel (mismas 4 metricas que el reporte).
 */
export interface TotalPanel {
  visualizaciones: number;
  alcance: number;
  interacciones: number;
  engagement_pct: number;
}
/**
 * Un movimiento destacado ('pico') del periodo en el panel.
 */
export interface PicoPanel {
  marca: string;
  direccion: string;
  variacion_vis_pct: number;
  visualizaciones: number;
  pieza_titulo: string;
}
/**
 * Resumen de metricas del panel (REUSA `keni_metricas.servicio`, solo lectura).
 *
 * `disponible` es False si la fuente de metricas falló (el resto del panel sigue útil);
 * en ese caso `total` es `null` y `picos` viene vacío. `rango` solo está cuando hay
 * datos, por eso es `NotRequired`. `fuente` marca muestra vs real (badge en la UI).
 */
export interface MetricasPanel {
  disponible: boolean;
  fuente: string;
  total: TotalPanel | null;
  picos: PicoPanel[];
  rango?: string;
}
/**
 * Bloque 'cola de aprobacion' del panel: cuántas piezas esperan revisión.
 */
export interface ColaPanel {
  total: number;
}
/**
 * Una pieza programada próxima (vista mínima del panel, nombres resueltos).
 *
 * `preparado_en` viene con el instante DRY-RUN si el programador ya la preparó (venció);
 * "" si aún no vence. El posteo real vía Metricool está gated por `KENI_PUBLICAR_REAL`.
 */
export interface ProximaPanel {
  id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  red: string;
  red_nombre: string;
  fecha_programada: string;
  preparado_en: string;
}
/**
 * Bloque 'próximas programadas' del panel: las más inminentes + el total.
 */
export interface ProximasPanel {
  items: ProximaPanel[];
  total: number;
}
/**
 * Aviso de frontera del producto: el sistema NO publica solo (gated por `KENI_PUBLICAR_REAL`).
 */
export interface GatingPanel {
  publicacion_real_activa: boolean;
  nota: string;
}
/**
 * Respuesta de `GET /api/panel`: dashboard ligero de un vistazo (#9, Fase 3).
 *
 * Agrega métricas/picos (reusa los caminos de lectura de Metricas, sin tocar su
 * página), el contador de la cola de aprobación y las próximas piezas programadas.
 * `gating` recuerda que el posteo real (vía Metricool) está gated por `KENI_PUBLICAR_REAL`.
 */
export interface RespuestaPanel {
  metricas: MetricasPanel;
  cola: ColaPanel;
  proximas: ProximasPanel;
  gating: GatingPanel;
}
/**
 * Valor actual de una pieza comercial (del ultimo snapshot).
 */
export interface ActualComercial {
  ts: string;
  interacciones: number;
  visualizaciones: number;
  alcance: number;
  engagement_pct: number;
}
/**
 * Un punto de la serie temporal de una pieza comercial (acumulado).
 */
export interface SnapshotComercial {
  ts: string;
  interacciones: number;
  visualizaciones: number;
  alcance: number;
}
/**
 * Un post real de Metricool elegible para monitorizar (`GET /api/comercial/posts`).
 */
export interface PostSeleccionableComercial {
  id: string;
  red: string;
  titulo: string;
  publicado: string;
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
  url?: string | null;
}
/**
 * Listado de posts seleccionables + procedencia (muestra vs real).
 */
export interface RespuestaPostsComercial {
  posts: PostSeleccionableComercial[];
  fuente: string;
  es_muestra: boolean;
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
  id_post_metricool: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  cliente: string;
  campania: string;
  red: string;
  red_nombre: string;
  metrica_objetivo: "interacciones" | "visualizaciones" | "alcance";
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
