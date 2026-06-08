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
}

// --- Estudio de imagen ---

/** Una imagen del almacén de media (objeto + URL), tal como vive en el lienzo del Estudio. */
export interface ImagenActiva {
  /** Nombre del objeto de media (lo que se manda a los endpoints y se persiste en la pieza). */
  id: string;
  /** URL para servir la imagen (`/api/media/...` o nombre que `urlMedia` resuelve). */
  url: string;
  /**
   * Foto BASE de la que se compuso esta imagen al "Aplicar marca". Permite REAPLICAR la
   * plantilla siempre desde la foto original (no apila ni duplica el logo) y "quitar marca"
   * volviendo a la base. Indefinido en fotos crudas (subidas/generadas) y ediciones.
   */
  origen?: string;
}

/** Formatos de red soportados por el Estudio (vertical 9:16, feed 4:5, cuadrado 1:1, horizontal 16:9). */
export type FormatoImagen = "vertical" | "feed" | "cuadrado" | "horizontal";

/** Operaciones deterministas de edición (sin coste). */
export type OpEditarImagen =
  | "recortar"
  | "redimensionar"
  | "comprimir"
  | "extender"
  | "placa";

/** Cuerpo de `POST /api/imagenes/generar`: genera N variantes (IA). */
export interface CuerpoImagenesGenerar {
  prompt: string;
  marca?: string;
  formato?: FormatoImagen;
  /** Número de variantes a generar (1..4, def. 2). */
  variantes?: number;
  prompt_id?: string;
}

/** Cuerpo de `POST /api/imagenes/editar`: operación determinista sobre un objeto de media. */
export interface CuerpoImagenesEditar {
  /** Nombre del objeto de media sobre el que operar. */
  imagen: string;
  op: OpEditarImagen;
  formato?: FormatoImagen;
  /** redimensionar: lado máximo en px. */
  max?: number;
  /** comprimir: peso máximo en MB (def. 2). */
  peso_max_mb?: number;
  /** comprimir: formato de archivo de salida. */
  formato_archivo?: "jpg" | "webp";
  /** extender: método de relleno. */
  metodo?: "borde" | "color";
  /** extender: fuerza el relleno aunque el formato ya coincida. */
  forzar?: boolean;
  /** placa: texto de la placa. */
  texto?: string;
  /** placa: marca visual (solo `unotv` | `claro-sports`). */
  marca?: string;
  /** placa: crédito/fuente de la cita. */
  fuente_cita?: string;
}

/** Cuerpo de `POST /api/imagenes/expandir`: outpainting generativo (IA, con coste). */
export interface CuerpoImagenesExpandir {
  imagen: string;
  formato?: FormatoImagen;
  marca?: string;
  /** Fidelidad al sujeto original (0..1). */
  strength?: number;
  lado?: "auto" | "arriba" | "abajo" | "izquierda" | "derecha";
}

/**
 * Cuerpo de `POST /api/imagenes/retocar`: retoque GENERATIVO por instrucción (IA, con coste).
 * Reinterpreta toda la imagen según la indicación ("oscurece el cielo"); distinto de expandir
 * (outpainting fiel al sujeto).
 */
export interface CuerpoImagenesRetocar {
  imagen: string;
  /** Qué cambiar, en lenguaje natural. */
  instruccion: string;
  /** Cuánto cambia respecto al original (0..1; alto = cambia más). */
  strength?: number;
}

/** Cuerpo de `POST /api/imagenes/revisar`: revisión legal/editorial (gate humano, no bloquea). */
export interface CuerpoImagenesRevisar {
  /** Nombre del objeto de media a revisar. */
  imagen: string;
  marca?: string;
}

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

/** Cuerpo de `POST /api/imagenes/componer`: estampa la plantilla de marca sobre una imagen. */
export interface CuerpoImagenesComponer {
  /** Nombre del objeto de media sobre el que componer. */
  imagen: string;
  marca: string;
  formato?: FormatoImagen;
  /** Titular corto opcional. */
  titular?: string;
  /** Etiqueta/pleca opcional (vacía = usa la de la plantilla). */
  etiqueta?: string;
}

// --- Galería de artes (objetos de media catalogados para reutilizar) ---

/** Origen de un arte: trabajado en el Estudio, subido por el usuario o generado con IA. */
export type TipoArte = "estudio" | "subida" | "ia";

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
