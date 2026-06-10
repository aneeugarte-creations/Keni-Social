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

/** Respuesta de `POST /api/investigacion/correr`. Async: devuelve la generación a sondear. */
export interface RespuestaInvCorrer {
  generacion: Generacion | null;
}

// --- Motor de ingesta persistente (Ola A): archivo a nivel de artículo --------
// Contrato: docs/maquina-contenido/A-motor-ingesta.md

// --- Motor de ingesta: Ola B — Clustering de historias ---

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
    frescura?: number;
    viralidad?: number;
    marca?: number;
    rendimiento?: number;
    breaking?: number;
    palabras?: string[];
  };
  /** true si supera el LISTÓN de producción automática (la misma evaluación que el pipeline). */
  promovible?: boolean;
  /** Motivo legible del listón (por qué supera, o por qué no). */
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
  contenido_id: string;
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
  /** Hasta ~8 artículos corroborantes del cluster. */
  enlaces: { titulo: string; url: string; fuente: string }[];
  // ── Ola D: verificación + traducción ─────────────────────────────────────
  /** Nivel de verificación por corroboración (Ola D). */
  verificacion?: "corroborada" | "unica_fuente" | "dudosa";
  /** true si el título/resumen ya fueron traducidos al ES por el daemon (Ola D). */
  traducido?: boolean;
  /** Título en el idioma original, antes de la traducción (solo si `traducido`). */
  titulo_original?: string;
  /** Código de idioma del cluster antes de traducir (p. ej. 'en', 'pt'). */
  idioma?: string;
}

/** Respuesta paginada de `GET /api/noticias/historias`. */
export interface RespuestaHistorias {
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
  contenido_id: string;
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
