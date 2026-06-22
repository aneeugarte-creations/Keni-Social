import type { Generacion } from "./generaciones";

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
  /** Pieza a la que pertenece la imagen: la generación se correlaciona a su pipeline (etapa Arte). */
  pieza_id?: string;
  publicacion_id?: string;
}

// --- Estudio de imagen ---

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

// --- Galería de artes (objetos de media catalogados para reutilizar) ---

/**
 * Origen de un arte: trabajado en el Estudio, subido por el usuario, generado con IA o la
 * foto ORIGINAL de la nota (RSS de marca propia, auto-catalogada en su carpeta "Originales").
 */
export type TipoArte = "estudio" | "subida" | "ia" | "original";

/**
 * Un ARTE: una imagen del almacén que el equipo CONSERVA para reutilizar en piezas.
 * Catalogarla la protege del GC de media sin dueño y la hace seleccionable por marca.
 */
export interface Arte {
  /** Id del item del catálogo (no del objeto de media). */
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

// --- Fotos de STOCK (ayuda visual NUNCA publicable sin autorizar) ---

/** Estado de un proveedor de fotos de stock (lo declara `GET /api/artes/stock/buscar`). */
export interface ProveedorStock {
  proveedor: string;
  nombre: string;
  /** `false` si el proveedor no se puede usar ahora (falta clave / caído): chip deshabilitado. */
  disponible: boolean;
  /** Motivo de la indisponibilidad, para el tooltip del chip. */
  motivo?: string;
  /** El proveedor exige una clave de API que no está configurada. */
  requiere_clave?: boolean;
}

/** Una foto candidata propuesta por la búsqueda de stock (referencia, aún sin descargar). */
export interface CandidataStock {
  proveedor: string;
  /** URL de la imagen a tamaño completo (lo que se descargaría al adjuntar). */
  url: string;
  /** Miniatura para el grid. */
  thumb: string;
  autor?: string;
  licencia?: string;
  credito_url?: string;
  titulo?: string;
}

/** Respuesta de `GET /api/artes/stock/buscar`. */
export interface RespuestaBuscarStock {
  proveedores: ProveedorStock[];
  candidatos: CandidataStock[];
}

/** Cuerpo de `POST /api/artes/stock/adjuntar`: una candidata elegida o la foto original de la fuente. */
export interface CuerpoAdjuntarStock {
  pieza_id: string;
  url?: string;
  proveedor?: string;
  autor?: string;
  licencia?: string;
  credito_url?: string;
  /** `true` = baja la imagen original del artículo (`imagen_fuente`) en vez de una candidata. */
  usar_fuente?: boolean;
}

/** Cuerpo de `POST /api/artes/stock/autorizar`: confirma/revoca derechos para publicar el stock. */
export interface CuerpoAutorizarStock {
  pieza_id: string;
  autorizar: boolean;
}

/**
 * Subconjunto de campos de la fila por plataforma que devuelven los endpoints de stock
 * (`_plataforma_stock_a_dict`): lo justo para refrescar la imagen y su estado de licencia.
 */
export interface PlataformaStock {
  id: string;
  imagen_url: string;
  foto: string;
  falta_imagen: boolean;
  imagen_origen: string;
  imagen_proveedor: string;
  imagen_autor: string;
  imagen_licencia: string;
  imagen_credito_url: string;
  imagen_autorizada: boolean;
}

/** Respuesta de `POST /api/artes/stock/{adjuntar,autorizar}`. */
export interface RespuestaStock {
  plataforma: PlataformaStock;
}

// --- Lanzamiento manual de ARTE (genera N imágenes a mano para una marca) ---

/** Cuerpo de `POST /api/artes/generar`: lanza N imágenes de arte a mano. */
export interface CuerpoGenerarArte {
  /** Marca del catálogo único (obligatoria). */
  marca: string;
  /** Tema a ilustrar; si falta, se usa el prompt de Ilustrar de la Prompts (`prompt/ilustrar`). */
  prompt?: string;
  /** Id de un modelo de `GET /api/conexiones/imagen`; si falta, el configurado por defecto. */
  modelo?: string;
  /** Nº de alternativas a generar, 1..4. */
  n?: number;
}

/**
 * Coste medio por imagen (USD) para estimar el gasto ANTES de lanzar. El front lo
 * multiplica por N ("~$X por imagen × N"). `por_imagen` es null si aún no hay muestras.
 */
export interface CosteMedioArte {
  /** Media de coste por imagen; `null` si no hay ninguna muestra ni global. */
  por_imagen: number | null;
  moneda: string;
  unidad: string;
  /** Cuántas generaciones se promediaron. */
  muestras: number;
  modelo: string;
  /** `true` si el dato es la media GLOBAL de imagen (no la del modelo pedido). */
  global: boolean;
}

/**
 * Respuesta de `POST /api/artes/generar`: N generaciones de imagen (a sondear con
 * `GET /api/generaciones/{id}`), el modelo efectivo, N y el coste medio por imagen.
 */
export interface RespuestaGenerarArte {
  generaciones: Generacion[];
  modelo: string;
  n: number;
  coste_medio: CosteMedioArte;
}
