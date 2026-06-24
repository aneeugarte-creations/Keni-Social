/**
 * GENERADO — NO EDITAR A MANO.
 *
 * Tipos DERIVADOS del backend (subconjunto estable del contrato `/api/*`).
 * Fuente: `keni_consola.esquema_api` (Python). Regenerar con `npm run gen:types`.
 * El guard `npm run gen:types:check` (y el test del backend) falla si esto se
 * desincroniza del backend. El resto de tipos vive a mano en `types.ts`.
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
  piezas: number;
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
 * Una red (plataforma) del reporte con sus métricas agregadas entre marcas.
 *
 * Agrega el `por_plataforma` de TODAS las cuentas del reporte por plataforma. `red`
 * es el id de plataforma (el frontend lo traduce a nombre). `alcance` es `null` si
 * NINGUNA cuenta mide esa red (no se inventa un 0).
 */
export interface RedMetrica {
  red: string;
  visualizaciones: number;
  alcance: number | null;
  interacciones: number;
  engagement_pct: number;
}
/**
 * Estado de UNA red social para una marca en el rango (auditoría de cobertura).
 *
 * Responde a la pregunta "¿por qué esta red no muestra datos?" sin esconder las
 * redes vacías. `estado` ∈ {"con_datos", "sin_metricas", "sin_lectura",
 * "no_configurada", "sin_credenciales", "presupuesto_agotado"}:
 *
 *   - con_datos:        respondió con métricas en el rango.
 *   - sin_metricas:     conectada, pero sin actividad/métricas en el periodo.
 *   - sin_lectura:      no se pudo leer (red no conectada en Metricool o métrica
 *                       no disponible en el plan / error de la API).
 *   - no_configurada:   la marca no tiene esta red dada de alta en Metricool.
 *   - sin_credenciales / presupuesto_agotado: motivos de omisión heredados.
 *
 * Las métricas son `null` cuando la red NO respondió (no se inventa un 0 falso);
 * `motivo` es el texto legible que la UI muestra como explicación.
 */
export interface RedCobertura {
  red: string;
  estado: string;
  visualizaciones: number | null;
  alcance: number | null;
  interacciones: number | null;
  engagement_pct: number | null;
  stories: number | null;
  motivo: string | null;
}
/**
 * Cobertura de TODAS las redes auditables de una marca (auditoría por marca).
 *
 * `redes` lista SIEMPRE el universo completo de redes sociales medibles (aunque no
 * tengan datos), cada una con su `estado` y `motivo`, para que el operador vea de un
 * vistazo qué falta y por qué.
 */
export interface MarcaCobertura {
  marca_id: string;
  marca: string;
  redes: RedCobertura[];
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
  por_red: RedMetrica[];
  cobertura_redes: MarcaCobertura[];
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
 * Sugerencia accionable que cierra el loop a la acción.
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
 * Capa narrativa sobre las métricas: top movimientos con la(s) pieza(s)
 * que los explican y un siguiente paso. `fuente` marca la procedencia de los
 * datos.
 */
export interface AnalisisDiario {
  rango: string;
  etiqueta_rango: string;
  marca: string;
  fuente: string;
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
 *
 * El servicio de métricas serializa cada `Pieza` con el desglose GRANULAR (likes,
 * comentarios, compartidos, guardados, video_views, tiempo medio de visualización,
 * clics de enlace) además del agregado. Esos campos son `null` cuando la fuente no
 * los expone para esa pieza (no se inventa un 0): la UI distingue "0" de "sin dato".
 * `formato`/`cuenta` y `rendimiento_relativo` (vs la media de su grupo) también vienen
 * del servicio; `null` cuando no aplican.
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
  alcance: number | null;
  likes: number | null;
  comentarios: number | null;
  compartidos: number | null;
  guardados: number | null;
  video_views: number | null;
  tiempo_medio_vis_s: number | null;
  clics_enlace: number | null;
  formato: string | null;
  cuenta: string | null;
  rendimiento_relativo: number | null;
}
/**
 * Un intervalo del histograma de engagement (cuántas piezas caen en [inicio, fin)).
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
 * desde la Consola, leído de Metricool por su `id_post_metricool`. `publicacion_id` enlaza
 * a la pieza en el tablero (`/operacion/feed/lista`). `encontrado=False` => Metricool aún
 * no tiene datos (recién publicada): la UI muestra "sin datos todavía", no ceros falsos.
 */
export interface PiezaRendimiento {
  publicacion_id: string;
  pieza_id: string;
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
 * Una pieza del listado COMPLETO del periodo (tabla "Todas las piezas").
 *
 * Misma forma que `PiezaMetrica` (granulares incluidos) MÁS `linea`: el nombre de la
 * LÍNEA editorial (etiqueta clase `categoria`) a la que pertenece la pieza, resuelto
 * cruzándola con su contenido de la Consola. `linea` es `null` cuando la pieza no tiene
 * línea atribuible (la mayoría de piezas que no nacieron en la Consola): la UI muestra
 * "Sin línea". Se separa de `PiezaMetrica` para no forzar `linea` en top/peores.
 */
export interface PiezaListado {
  id: string;
  plataforma: string;
  titulo: string;
  publicado: string;
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
  url: string | null;
  alcance: number | null;
  likes: number | null;
  comentarios: number | null;
  compartidos: number | null;
  guardados: number | null;
  video_views: number | null;
  tiempo_medio_vis_s: number | null;
  clics_enlace: number | null;
  formato: string | null;
  cuenta: string | null;
  rendimiento_relativo: number | null;
  linea: string | null;
}
/**
 * Respuesta de `GET /api/metricas/piezas-listado`: listado COMPLETO de piezas del periodo.
 *
 * TODAS las piezas de la(s) cuenta(s) del periodo tal como las emite la fuente única
 * (`servicio.construir_listado_piezas`), no solo top/peores. Cada `PiezaListado` trae
 * su `id` (de Metricool), granulares, url y su `linea` editorial. Es el insumo de la
 * tabla "Todas las piezas del periodo" (filtros + orden + paginación por día + detalle
 * por pieza). Coste 0 de API: reúsa lo que el dashboard ya descarga.
 */
export interface PiezasListado {
  rango: string;
  etiqueta_rango: string;
  marca: string;
  periodo: PeriodoMetricas;
  fuente: string;
  piezas: PiezaListado[];
  total: number;
  generado_en: string;
}
/**
 * Un snapshot acumulado de UNA pieza en el histórico (ADR 0007).
 *
 * El daemon de refresco escribe un punto por pieza seguida cada N horas. Todas las
 * métricas son los valores ACUMULADOS en ese instante (`ts`, ISO). Las granulares
 * valen 0 cuando la fuente no las trajo en ese snapshot (no se distingue de un 0 real
 * en la serie persistida; la honestidad está a nivel de pieza: si no se sigue, no hay
 * puntos).
 */
export interface PuntoHistorico {
  ts: string;
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
  alcance: number;
  likes: number;
  comentarios: number;
  compartidos: number;
  guardados: number;
  video_views: number;
  tiempo_medio_vis_s: number;
  clics_enlace: number;
}
/**
 * Resumen de cómo CRECE una pieza, derivado de sus snapshots (honesto, sin inventar).
 *
 * `null` (la respuesta entera) cuando hay menos de 2 snapshots: sin dos puntos no hay
 * velocidad medible. Dentro, cada campo puede ser `null` si su cálculo no aplica
 * (p. ej. `pct_en_primeras_24h` cuando las visualizaciones finales son 0).
 */
export interface VelocidadPieza {
  pct_en_primeras_24h: number | null;
  delta_medio_por_dia: number | null;
  n_snapshots: number;
}
/**
 * Respuesta de `GET /api/metricas/pieza-historico`: serie histórica + velocidad de una pieza.
 *
 * `puntos` vacío = la pieza aún NO se está siguiendo (no hay snapshots): la UI lo dice
 * honestamente ("sin histórico todavía"), nunca dibuja una curva inventada. `velocidad`
 * es `null` con menos de 2 puntos.
 */
export interface HistoricoPieza {
  pieza_id: string;
  puntos: PuntoHistorico[];
  velocidad: VelocidadPieza | null;
}
/**
 * Un día de la serie de seguidores: total + desglose por red.
 */
export interface PuntoSeguidores {
  fecha: string;
  total: number;
  por_red: {
    [k: string]: number;
  };
}
/**
 * Respuesta de `GET /api/metricas/seguidores`: evolución de seguidores del periodo.
 *
 * `cuenta` es `null` cuando agrega todas las marcas. `puntos` vacío = la fuente activa
 * no expone serie de seguidores (degradación honesta). `neto`/`neto_por_red` resumen la
 * ganancia/pérdida del periodo.
 */
export interface SerieSeguidores {
  cuenta: string | null;
  rango: string;
  etiqueta_rango: string;
  periodo: PeriodoMetricas;
  fuente: string;
  puntos: PuntoSeguidores[];
  neto: number;
  generado_en: string;
  neto_por_red: {
    [k: string]: number;
  };
}
/**
 * Una celda marca×red del desglose de interacciones (suma del periodo).
 */
export interface CeldaDesglose {
  marca: string;
  red: string;
  likes: number;
  comentarios: number;
  compartidos: number;
  guardados: number;
  video_views: number;
  interacciones: number;
  visualizaciones: number;
  engagement_pct: number;
  n_piezas: number;
}
/**
 * Respuesta de `GET /api/metricas/desglose`: interacciones por marca×red.
 *
 * Cada celda detalla likes/comentarios/compartidos/guardados/video_views y los
 * agregados; `totales` cierra la tabla con la suma global (misma forma que una celda
 * sin `marca`/`red`).
 */
export interface DesgloseInteracciones {
  rango: string;
  etiqueta_rango: string;
  periodo: PeriodoMetricas;
  fuente: string;
  celdas: CeldaDesglose[];
  generado_en: string;
  totales: {
    [k: string]: number;
  };
}
/**
 * Una celda marca×red×formato del crosstab de rendimiento.
 */
export interface CeldaCrosstab {
  marca: string;
  red: string;
  formato: string | null;
  n_piezas: number;
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
  rendimiento_relativo_medio: number | null;
}
/**
 * Respuesta de `GET /api/metricas/crosstab`: rendimiento cruzado marca×red×formato.
 */
export interface Crosstab {
  rango: string;
  etiqueta_rango: string;
  periodo: PeriodoMetricas;
  fuente: string;
  celdas: CeldaCrosstab[];
  generado_en: string;
}
/**
 * La pieza que mejor rindió de una marca×red×fecha (apuntala la correlación).
 */
export interface PostEstrella {
  id: string;
  titulo: string;
  engagement_pct: number;
  url: string | null;
}
/**
 * Un punto de la correlación seguidores ganados ↔ piezas publicadas.
 */
export interface ItemCorrelacion {
  marca: string;
  red: string;
  fecha: string;
  seguidores_ganados: number;
  n_posts: number;
  seguidores_por_post: number | null;
  post_estrella: PostEstrella | null;
}
/**
 * Respuesta de `GET /api/metricas/correlacion`: seguidores ganados ↔ piezas.
 *
 * `nota` explica la lectura (correlación, no causalidad) para la UI.
 */
export interface CorrelacionSeguidores {
  rango: string;
  etiqueta_rango: string;
  periodo: PeriodoMetricas;
  fuente: string;
  items: ItemCorrelacion[];
  nota: string;
  generado_en: string;
}
/**
 * Envelope ADITIVO de paginacion (offset-based).
 *
 * Lo añaden los listados pesados (piezas/runs/generaciones) junto a su
 * clave de lista. `total` = filas existentes sin paginar; `limite` = tamaño de
 * pagina efectivo (igual a `total` si no se paginó); `desplazamiento` = offset.
 *
 * `cursor_siguiente` (KEYSET, feed de scroll infinito): clave `"<creado>|<id>"` para
 * pedir la SIGUIENTE pagina. Solo lo emite el feed cuando pagina por `?cursor=` y hay
 * mas filas; se OMITE en la ultima pagina y en los modos offset/completo (opcional).
 */
export interface Paginacion {
  total: number;
  limite: number;
  desplazamiento: number;
  cursor_siguiente?: string;
}
/**
 * Metricas de monitorizacion de un run/generacion IA (las que reporta el CLI).
 *
 * El handler las omite (clave a `null`) si el run no produjo metricas (interactivo
 * o CLI sin JSON). `ttft_ms` (time-to-first-token, ms) y `tokens_por_s` (tokens de
 * salida por segundo) son de rendimiento y vienen `null` cuando el CLI no los reporta.
 */
export interface MetricasRun {
  tokens_in: number;
  tokens_out: number;
  num_turns: number;
  total_cost_usd: number;
  duration_ms: number;
  modelo: string;
  ttft_ms: number | null;
  tokens_por_s: number | null;
}
/**
 * Una pieza serializada (`dominio.piezas.pieza_a_dict`).
 *
 * `marca_nombre`/`red_nombre` se resuelven en servidor. `imagen` es el nombre de
 * archivo ("" si no hay) e `imagen_url` su ruta servible ("" si no hay).
 * `autor_id`/`autor_nombre` (atribucion por usuario, Fase 1) identifican a quien
 * creo la pieza; "" en piezas legadas/anonimas (la UI las muestra como "desconocido").
 *
 * Flujo de aprobacion de equipo (#9, Fase 3): `enviado_a_revision_en`/`revisor_id`/
 * `revisor_nombre`/`revisado_en` registran quien la envio/reviso y cuando; "" mientras
 * no haya pasado por revision (incluidas las piezas legadas). `preparado_en` se estampa
 * cuando la pieza se publica de verdad en redes (botón manual, gated por
 * `KENI_PUBLICAR_REAL`); "" mientras no se haya publicado.
 */
export interface Pieza {
  id: string;
  publicacion_id: string;
  pipeline_id: string;
  titulo: string;
  marca: string;
  marca_nombre: string;
  red: string;
  red_nombre: string;
  contenido: string;
  copy_in: string;
  estado: "borrador" | "en_revision" | "programado" | "publicado";
  revision: string;
  autor_id: string;
  autor_nombre: string;
  responsable_id: string;
  responsable_nombre: string;
  enviado_a_revision_en: string;
  revisor_id: string;
  revisor_nombre: string;
  revisado_en: string;
  preparado_en: string;
  id_post_metricool: string;
  tipo_contenido: string;
  formato: string;
  variante?: string;
  espejo?: boolean;
  imagen_fuente: string;
  video: string;
  foto: string;
  imagen_origen?: string;
  imagen_proveedor?: string;
  imagen_autor?: string;
  imagen_licencia?: string;
  imagen_credito_url?: string;
  imagen_autorizada?: boolean;
  imagen_clave?: string;
  falta_copy: boolean;
  falta_imagen: boolean;
  falta_revision: boolean;
  falta_publicar: boolean;
  falta_video: boolean;
  etapa_ia:
    | "generando_copy"
    | "generando_arte"
    | "falta_copy_in"
    | "falta_hashtags"
    | "falta_hashtag_editorial"
    | "lista_para_revisar"
    | "programada"
    | "publicada";
  fecha_creacion: string;
  fecha_actualizacion: string;
  fecha_programada: string;
  fecha_fuente: string;
  fuente_original: string;
  origen: string;
  categoria: string;
  imagen: string;
  imagen_url: string;
  evergreen: boolean;
  hashtags_sugeridos?: string[];
  hashtags_linea?: string[];
  falta_hashtags?: boolean;
  falta_hashtag_editorial?: boolean;
  copy_in_exento?: boolean;
  placa_oculta?: boolean;
  plantilla_diseno_id?: string;
  foto_encuadre?: string;
  fotos?: string;
  carrusel?: string;
}
/**
 * Listado de `GET /api/piezas` con el envelope de paginacion.
 */
export interface RespuestaPiezas {
  piezas: Pieza[];
  paginacion: Paginacion;
}
/**
 * Respuesta de los endpoints que devuelven UNA pieza (`{pieza}`).
 */
export interface RespuestaPieza {
  pieza: Pieza;
}
/**
 * Cola de aprobacion (`GET /api/aprobacion/cola`): piezas en revision, FIFO.
 *
 * Cada item es una `Pieza` completa (incluye `autor_nombre`/
 * `enviado_a_revision_en`: quien la envio y desde cuando espera). `total` = nº en cola.
 */
export interface RespuestaColaAprobacion {
  cola: Pieza[];
  total: number;
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
