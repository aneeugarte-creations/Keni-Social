import type { Generacion } from "./generaciones";

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

// ── Importador de calendario Excel/CSV (H1) ─────────────────────────────────
// `POST /api/publicaciones/importar` (multipart). Con `previsualizar=1` devuelve las
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

/**
 * Importación AGNÓSTICA (PDF/Word/imagen/captura): el back NO ejecuta `claude`, así que
 * ENCOLA un job de IA al worker y responde con esto. El SPA sondea la `generacion` con
 * `useGeneracion`; al completarse, su `resultado` trae `{creados, omitidos, errores}` y los
 * ítems aterrizan como borradores en el tablero (la superficie de revisión).
 */
export interface RespuestaImportCalendarioPendiente {
  pendiente: true;
  generacion: Generacion;
}

/** Resultado de una generación de importación de calendario por IA (worker). */
export interface ResultadoImportCalendario {
  creados?: number;
  omitidos?: { titulo: string; motivo: string }[];
  errores?: ErrorImportCalendario[];
}

// ── Insumos del día (cajones) ─────────────────────────────────────────────────
// Contrato compartido con el backend (01-insumos-del-dia.md). Todos los campos
// usan snake_case tal como los devuelve la API (verificado en el contrato).

/**
 * Los cajones de insumos diarios. Los 4 primeros son de UnoTV; `notas` y `contexto`
 * son de Claro Sports (`contexto` = guía editorial, nunca se publica).
 */
export type CajonInsumo =
  | "portal"
  | "corresponsales"
  | "reporteros"
  | "eventos_claro"
  | "notas"
  | "contexto";

/** Un lote de insumos (un "drop" en un cajón; el parseo Haiku produce los items). */
export interface InsumoLote {
  id: string;
  fecha: string;
  cajon: CajonInsumo;
  marca: string;
  origen_texto: string;
  origen_archivo: string;
  /** `parseando` mientras el worker corre Haiku; `listo`/`error` al terminar. */
  estado: "parseando" | "listo" | "error";
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
  tipo: "nota" | "cobertura" | "evento" | "contexto";
  idioma: string;
  /** `true` si ya se llevó al tablero. */
  usado: boolean;
  publicacion_id: string;
  orden: number;
  creado: string;
  /** Estado de frescura según la TTL de la línea. "caduco" = ítem vencido. */
  frescura?: "fresco" | "caduco";
  /**
   * Estado REAL de la pieza de cara al feed (solo ítems usados no-evento; lo deriva el
   * backend de la pieza, igual que en el pool de noticias, para que el badge no mienta):
   * 'en_cola' | 'generando' | 'en_feed'. Ausente = sin información (UI cae al texto genérico).
   */
  pieza_estado?: "en_cola" | "generando" | "en_feed" | string;
  /**
   * Vigencia de una Indicación (cajón contexto): el backend marca `false` cuando la guía
   * superó su ventana de 7 días y ya no orienta el copy. OPCIONAL (puede no venir aún): se
   * trata `undefined` como vigente para no romper la UI mientras el back se despliega.
   */
  indicacion_vigente?: boolean;
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
