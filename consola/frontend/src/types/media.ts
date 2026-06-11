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
  publicacion_id?: string;
  contenido_id?: string;
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
 * Un ARTE: una imagen del almacén que el equipo CONSERVA para reutilizar en publicaciones.
 * Catalogarla la protege del GC de media huérfana y la hace seleccionable por marca.
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
