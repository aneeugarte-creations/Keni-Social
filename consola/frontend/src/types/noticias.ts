import type { Generacion } from "./generaciones";

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
  publicacion_id: string;
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
  publicacion_id?: string;
}

/** Respuesta de `POST /api/investigacion/correr`. Async: devuelve la generación a sondear. */
export interface RespuestaInvCorrer {
  generacion: Generacion | null;
}

// --- Motor de ingesta persistente (Ola A): archivo a nivel de artículo --------
// Contrato: docs/maquina-contenido/A-motor-ingesta.md

// --- Motor de ingesta: Ola B — Clustering de historias ---

/** Una entrada del TIMELINE de outlets de una historia (quién la abrió, quién se sumó). */
export interface FuenteHistoria {
  /** Nombre humano de la fuente (p. ej. "Reuters"). */
  fuente: string;
  fuente_id: string;
  /** Peso editorial de la fuente (potente 2.0 / normal 1.0 / baja 0.5). */
  peso: number;
  /** Tier legible del peso. */
  tier: "potente" | "normal" | "baja" | string;
  /** ISO de cuándo este outlet se sumó a la historia ('' si sin timestamp). */
  primer_visto: string;
  /** Cuántos artículos aportó este outlet. */
  n_items: number;
}

/**
 * Un cluster de noticias (misma historia contada por varias fuentes).
 * Espejo de `noticias_clusters` + cálculo de `Ola B`.
 */
export interface Historia {
  id: string;
  titulo: string;
  resumen: string;
  /** Id de la marca dominante del cluster ('' = sin marca). */
  marca: string;
  marca_nombre: string;
  categoria: string;
  geo: string;
  /** Nº de artículos en el cluster. */
  n_items: number;
  /** Nº de fuentes distintas (corroboración). */
  n_fuentes: number;
  /** Idiomas presentes en el cluster. */
  idiomas: string[];
  /** Señal agregada. */
  senal: number;
  /** Score de ranking. */
  score: number;
  /** Razón humana del score (qué señales lo explican; la persiste el daemon al puntuar). */
  score_razon?: string;
  /**
   * Desglose por señal del score, cada una cruda en [0,1] + las palabras del vocabulario
   * de la marca que casaron. {} si el daemon aún no puntuó esta historia.
   */
  score_desglose?: {
    corroboracion?: number;
    /** Masa ponderada que se sumó en la ventana actual (señal de última hora; decae sola). */
    velocidad?: number;
    frescura?: number;
    viralidad?: number;
    marca?: number;
    rendimiento?: number;
    /** Masa de corroboración ponderada (Σ peso por outlet). */
    peso_fuentes?: number;
    breaking?: number;
    palabras?: string[];
  };
  /**
   * Los PESOS vivos de la fórmula del ranking (editables en ajustes). Con las señales
   * crudas del desglose, la UI reconstruye el cálculo: señal × peso = aporte, Σ = score.
   */
  score_pesos?: Record<string, number>;
  /** true si supera el UMBRAL de producción automática (la misma evaluación que el pipeline). */
  promovible?: boolean;
  /** Motivo legible del umbral (por qué supera, o por qué no). */
  promovible_motivo?: string;
  /** 1 si la historia está en modo breaking (aceleración de fuentes). */
  breaking: number;
  /** ISO del artículo más antiguo del cluster. */
  primer_visto: string;
  /** ISO del artículo más reciente del cluster. */
  ultimo_visto: string;
  /** Estado editorial: 'nuevo' | 'usado' | 'descartado'. */
  estado: "nuevo" | "usado" | "descartado" | string;
  /** Id del contenido en el tablero cuando `estado='usado'`. '' si no. */
  publicacion_id: string;
  /**
   * Estado REAL de cara al feed (derivado de la PIEZA, no solo del cluster). El badge se
   * pinta con esto para no mentir: `estado='usado'` solo significa "promovida".
   *  - 'en_pool'    → aún no promovida
   *  - 'en_cola'    → promovida pero SIN pieza en el feed todavía (dedup, sin redes, o copy
   *                   aún por encolar / etapa de copy detenida)
   *  - 'generando'  → pieza creada, copy en proceso
   *  - 'en_feed'    → pieza con copy: visible REAL en el feed
   *  - 'descartada' → descartada
   */
  pieza_estado?: "en_pool" | "en_cola" | "generando" | "en_feed" | "descartada" | string;
  /** Hasta ~8 artículos corroborantes del cluster (con su hora y el tier de su fuente). */
  enlaces: { titulo: string; url: string; fuente: string; publicado_en?: string; tier?: string }[];
  // ── Tracking de fuentes (ranking ponderado) ───────────────────────────────
  /** Masa de corroboración PONDERADA (Σ peso editorial por outlet distinto). */
  peso_fuentes?: number;
  /** Señal de velocidad [0,1] persistida (masa sumada en la ventana actual). */
  velocidad?: number;
  /** Nombre de la fuente que ABRIÓ la historia (publicó primero). */
  primera_fuente_nombre?: string;
  /** Timeline cronológico de outlets (el primero abrió la historia). */
  fuentes?: FuenteHistoria[];
  // ── Etapas de Investigación visibles por historia (ADR 0011) ─────────────
  /** Verificación de la fuente (verificación de la fuente) del contenido asociado, si lo hay:
   *  'no_verificado' | 'problema' | ''. Vacío si la historia aún no se promovió/verificó. */
  verificacion_fuente?: string;
  /** true si la MARCA de la historia la asignó el clasificador IA (breaking sin marca). */
  marca_clasificada_por_ia?: boolean;
  // ── Ola D: verificación + traducción ─────────────────────────────────────
  /** Nivel de verificación por corroboración (Ola D). */
  verificacion?: "corroborada" | "unica_fuente" | "dudosa";
  /** true si el título/resumen ya fueron traducidos al ES por el daemon (Ola D). */
  traducido?: boolean;
  /** Extranjera aún sin traducir: la mesa la muestra con un placeholder "Traduciendo…" en
   * `titulo` (nunca el original) hasta que el daemon la pase a ES (cada ~30 s, por score). */
  traduciendo?: boolean;
  /** Título en el idioma original, antes de la traducción (solo si `traducido`). */
  titulo_original?: string;
  /** Código de idioma del cluster antes de traducir (p. ej. 'en', 'pt'). */
  idioma?: string;
  /**
   * Nombre del MACRO-EVENTO al que pertenece la historia (p. ej. "Cumbre del G7").
   * Cuando varias historias comparten el mismo valor son sub-historias de un mismo gran
   * evento y la UI las agrupa. '' o ausente = sin macro-evento (se muestra suelta).
   */
  tema_macro?: string;
  /**
   * Grupo de navegación de la historia (el chip de la barra: "Fútbol", "Motor", "Boxeo"…).
   * Lo asigna el clasificador léxico en la Mesa para marcas con grupos (p. ej. Claro Sports);
   * '' o ausente para marcas sin grupos o candidatas sin clasificar.
   */
  grupo?: string;
  /**
   * Línea de navegación de la historia (el 2º nivel bajo el grupo: id de la etiqueta vertical,
   * p. ej. "fut-bundesliga"). Lo asigna el mismo clasificador léxico que el grupo en la Mesa;
   * '' o ausente para marcas sin grupos o candidatas sin clasificar.
   */
  linea?: string;
}

/** Respuesta paginada de `GET /api/noticias/historias`. */
export interface RespuestaHistorias {
  historias: Historia[];
  total: number;
}

// ── Mesa de redacción (GET /api/noticias/mesa) ────────────────────────────────

/** Una línea del plan editorial diario en la Mesa: cupo + progreso + top candidatas. */
export interface MesaLinea {
  /** Clave de la línea: id de etiqueta vertical o señal del motor ('breaking'/'evergreen'). */
  linea: string;
  /** Nombre legible de la línea (o "Última hora"/"Evergreen"). */
  etiqueta?: string;
  /** Objetivo diario de la línea según el plan. */
  cupo: number;
  /** Temas generados en 24 h móviles (el mismo conteo que la admisión). */
  generados: number;
  publicados: number;
  /** Cuántos faltan para el objetivo de hoy. */
  restante: number;
  /** Candidatas (`estado='nuevo'`) de esta línea en el pool. */
  en_pool: number;
  /** Top-N candidatas rankeadas (contrato Historia completo). */
  historias: Historia[];
}

/** Una línea del 2º nivel de navegación, colgada de su grupo (id + nombre + candidatas). */
export interface LineaGrupo {
  /** Id de la etiqueta vertical (p. ej. "fut-bundesliga"). Es lo que filtra `historias_grupo`. */
  linea: string;
  /** Nombre visible de la línea ("Bundesliga"). */
  nombre: string;
  /** Candidatas (`estado='nuevo'`) clasificadas en esta línea. */
  en_pool: number;
}

/** Un chip de la barra de navegación por grupo (su nombre + candidatas + sus líneas). */
export interface GrupoMesa {
  /** Nombre del grupo (= el chip): "Fútbol", "Motor", "Boxeo"… */
  grupo: string;
  /** Candidatas (`estado='nuevo'`) clasificadas en este grupo. */
  en_pool: number;
  /**
   * Líneas del grupo (2º nivel de navegación), con candidatas arriba y las vacías al final.
   * Ausente en payloads sin grupos; la UI degrada a la barra de grupos a secas.
   */
  lineas?: LineaGrupo[];
  /**
   * Solo en chips DERIVADOS de líneas del plan (marca sin grupos): la CLAVE de reparto de la
   * línea ('breaking'/id de etiqueta/'__fuera__') para paginar TODO su pool. No la trae el back;
   * la rellena `chipsDeLineas`. No dispara el desplegable (eso es `lineas`).
   */
  lineaId?: string;
}

/** Respuesta de `GET /api/noticias/mesa?marca=`: el pool segmentado por el plan. */
export interface RespuestaMesa {
  marca: string;
  /** false si la marca no tiene plan configurado (todo va en `fuera_de_plan`). */
  plan: boolean;
  lineas: MesaLinea[];
  fuera_de_plan: { en_pool: number; historias: Historia[] };
  /** Σ cupos del plan (el objetivo del día, p. ej. 12). */
  total_objetivo: number;
  /** Σ generados de las líneas del plan en 24 h. */
  total_generados: number;
  /**
   * Barra de navegación por GRUPO, ordenada por prioridad editorial. Vacía para marcas sin
   * grupos (UnoTV): en ese caso la Mesa mantiene su layout por plan. Cuando trae grupos, la
   * lista visible es `historias_grupo` (el front ignora `fuera_de_plan`).
   */
  grupos?: GrupoMesa[];
  /** Candidatas (top por score) con su `grupo`, para navegar por la barra. */
  historias_grupo?: Historia[];
}

/**
 * Respuesta de `GET /api/noticias/mesa/linea?marca=&linea=`: la página de candidatas de UNA
 * línea (rankeadas por score) + el TOTAL real de la línea (no el de la página).
 */
export interface RespuestaMesaLinea {
  historias: Historia[];
  total: number;
}

/**
 * Un artículo ingerido del archivo persistente (`noticias_items`).
 * Todos los campos de texto son '' si el feed no los entregó.
 */
export interface NoticiaItem {
  id: string;
  fuente_id: string;
  fuente_nombre: string;
  /** Categoría del feed: mx | internacional | deportes | ciencia-tech | gaming | tendencias | '' */
  categoria: string;
  /** Id canónico de la marca del feed ('' = global/sin marca). */
  marca: string;
  marca_nombre?: string;
  titulo: string;
  resumen: string;
  url: string;
  url_canonica: string;
  idioma: string;
  autor: string;
  imagen: string;
  /** pubDate del feed (ISO) o '' si no hay. */
  publicado_en: string;
  /** Cuándo lo ingestó el daemon (ISO). */
  capturado_en: string;
  /** Señal/score numérico (0 = sin señal). */
  senal: number;
  /** Código geográfico (ISO o '' si no aplica). */
  geo: string;
  /** Estado editorial: 'nuevo' | 'usado' | 'descartado'. */
  estado: "nuevo" | "usado" | "descartado" | string;
  /** Id del contenido en el tablero cuando `estado='usado'`. '' si no. */
  publicacion_id: string;
}

/** Respuesta paginada de `GET /api/noticias`. */
export interface RespuestaNoticias {
  items: NoticiaItem[];
  total: number;
}

/**
 * Resumen de salud del motor de ingesta.
 * Todos los campos son opcionales: el back puede arrancar vacío hasta el primer barrido.
 */
export interface ResumenCobertura {
  /** Nº de fuentes RSS activas y sin error sostenido. */
  feeds_activos?: number;
  /** Nº de fuentes con error sostenido (backoff / pausadas). */
  feeds_con_error?: number;
  /** Artículos ingeridos en las últimas 24 h. */
  items_24h?: number;
  /** Desglose de `items_24h` por categoría de feed. */
  por_categoria?: Record<string, number>;
  /** ISO del último barrido completado ('') si aún no hay. */
  ultimo_sondeo?: string;
  /** Nº total de artículos en el archivo (todos los estados). */
  total_items?: number;
}

// ── Rendimiento por fuente (GET /api/noticias/fuentes/stats) ─────────────────

/** Rendimiento editorial de una fuente en la ventana: qué aporta de verdad. */
export interface RendimientoFuente {
  fuente_id: string;
  fuente_nombre: string;
  /** Peso editorial observado (máx de sus items). */
  peso: number;
  tier: "potente" | "normal" | "baja" | string;
  /** Artículos aportados en la ventana. */
  items: number;
  /** Historias distintas en las que participó. */
  historias: number;
  /** Historias que ABRIÓ (publicó primero). */
  primeras: number;
  /** Historias suyas que acabaron usadas (promovidas al tablero). */
  usadas: number;
  /** usadas / historias (0..1). */
  tasa_uso: number;
}

export interface RespuestaStatsFuentes {
  fuentes: RendimientoFuente[];
  dias: number;
}

// ── Descubrimiento: Google Trends (GET /api/noticias/descubrimiento) ─────────

/** Estado + rendimiento del canal AUTOMÁTICO (Google Trends), paralelo a las fuentes manuales. */
export interface RespuestaDescubrimiento {
  /** El daemon de Trends está ingiriendo tendencias al pool. */
  activo: boolean;
  /** Geografías que ingiere (ej. ["MX"]). */
  geos: string[];
  /** Cada cuántos minutos hace un barrido. */
  intervalo_min: number;
  /** Nº de noticias que conserva por tema en tendencia (el resto son casi-duplicados). */
  max_por_tema: number;
  dias: number;
  /** Rendimiento editorial agregado del canal en la ventana (null si aún no aportó nada). */
  stats: RendimientoFuente | null;
}

/** Una noticia de muestra que explica un término en tendencia. */
export interface NoticiaTendencia {
  titulo: string;
  url: string;
  fuente: string;
}

/** Un término en tendencia AHORA (en vivo desde Google Trends), con su tráfico y muestra. */
export interface TerminoTendencia {
  /** El tema en tendencia (la búsqueda que sube). */
  termino: string;
  /** Tráfico aproximado crudo, tal cual lo da Trends (ej. "200 mil+"). */
  trafico: string;
  /** Tráfico normalizado a entero, para ordenar. */
  senal: number;
  /** Geografía de la tendencia (ej. "MX"). */
  geo: string;
  /** Muestra de noticias que explican el término. */
  noticias: NoticiaTendencia[];
}

export interface RespuestaTerminosTendencia {
  geos: string[];
  terminos: TerminoTendencia[];
  /** Avisos por geo que falló (best-effort); vacío si todo fue bien. */
  errores: string[];
}

// ── Ola D: salud de fuentes (GET /api/noticias/salud) ────────────────────────

/**
 * Estado detallado de un feed individual.
 * Espejo de la fila `fuentes_rss` + métricas calculadas.
 */
export interface SaludFeed {
  id: string;
  nombre: string;
  categoria: string;
  marca: string;
  marca_nombre: string;
  /** 1 si el feed está activo (columna activo). */
  activo: number;
  /** 1 si fue desactivado automáticamente por errores sucesivos. */
  desactivado_auto: number;
  /** ISO del último sondeo exitoso ('' si nunca). */
  ultima_actualizacion: string;
  /** Mensaje del último error ('' si no hay). */
  ultimo_error: string;
  /** Nº de errores consecutivos actuales. */
  errores_seguidos: number;
  /** Artículos ingeridos en las últimas 24 h desde este feed. */
  items_24h: number;
  /** Minutos desde el último ítem nuevo (null si nunca tuvo ítems). */
  frescura_min: number | null;
  /** Artículos descartados por el filtro de entrada (agenda de marca) en el último sondeo. */
  ultimo_filtrados?: number;
}

/**
 * Respuesta de `GET /api/noticias/salud`.
 * Resumen global + detalle por feed.
 */
export interface SaludCobertura {
  resumen: {
    /** Nº total de feeds conocidos. */
    feeds_total: number;
    /** Nº de feeds activos y no desactivados-auto. */
    activos: number;
    /** Nº de feeds desactivados automáticamente por errores. */
    auto_desactivados: number;
    /** Nº de feeds activos con errores seguidos > 0 (sin llegar al máximo). */
    fallando: number;
    /** Nº de feeds activos cuya frescura supera `KENI_FEED_SLA_MIN`. */
    stale: number;
    /** Artículos ingeridos en las últimas 24 h (todas las fuentes). */
    items_24h: number;
    /** Desglose de items_24h por categoría de feed. */
    por_categoria: Record<string, number>;
    /** Desglose de items_24h por idioma. */
    por_idioma: Record<string, number>;
    /** Categorías/regiones esperadas sin ítems frescos en 24 h. */
    huecos: string[];
    /** Frescura global (mín de todos los feeds activos, en minutos). */
    frescura_global_min: number;
  };
  feeds: SaludFeed[];
}
