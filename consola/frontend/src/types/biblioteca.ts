// Tipos del dominio «Biblioteca de medios unificada»: el índice `catalogo_media` más la dimensión
// de carpeta (`fuente`: portal | originales | fotografias). Un buscador global cruza las tres
// carpetas; dentro de fotografías, los items se agrupan por `grupo` (el partido).

/** Carpeta lógica de origen de un item de la biblioteca. */
export type FuenteBiblioteca = "portal" | "originales" | "fotografias";

/** Un item de la biblioteca: una imagen del catálogo, servible y descargable, con su carpeta. */
export interface ItemBiblioteca {
  id: string;
  /** Key del objeto S3 (lo que resuelve `/api/media/<key>`). */
  key: string;
  /** URL para servir la imagen a tamaño completo. */
  url: string;
  /** URL (o data URI) de la miniatura para el grid. */
  thumb: string;
  titulo: string;
  etiquetas: string[];
  fuente: FuenteBiblioteca;
  /** Carpeta lógica (p. ej. el partido para fotografías); "" si no aplica. */
  grupo: string;
  marca: string;
  credito: string;
  creado: string;
  // Coordenadas del túnel, presentes solo en items de `fotografias` (las guardó `guardar-remoto`):
  // permiten navegar la RÁFAGA del burst (`GET /api/artes/propio/rafaga`).
  galeria_id?: string;
  archivo?: string;
  dispositivo?: string;
}

/** Respuesta de `GET /api/biblioteca`: items que cruzan las carpetas (filtrables por q/fuente/marca/grupo). */
export interface RespuestaBiblioteca {
  items: ItemBiblioteca[];
}

/** Conteo de items de un grupo (carpeta lógica) dentro de una fuente. */
export interface GrupoBiblioteca {
  grupo: string;
  total: number;
}

/** Resumen de una fuente (carpeta) para navegar: total y sus grupos. */
export interface CarpetaBiblioteca {
  fuente: FuenteBiblioteca;
  total: number;
  grupos: GrupoBiblioteca[];
}

/** Respuesta de `GET /api/biblioteca/carpetas`: resumen por fuente y por grupo. */
export interface RespuestaCarpetasBiblioteca {
  carpetas: CarpetaBiblioteca[];
}

/** Cuerpo de `POST /api/biblioteca/guardar-remoto`: guarda en Fotografías una foto de un dispositivo
 *  conectado (se pide el original por el túnel; se conservan las etiquetas del candidato). */
export interface CuerpoGuardarRemoto {
  galeria_id: string;
  archivo: string;
  dispositivo?: string;
  marca?: string;
  titulo?: string;
  etiquetas?: string[];
}

/** Respuesta de `POST /api/biblioteca/guardar-remoto`: el item insertado en la carpeta Fotografías. */
export interface RespuestaGuardarRemoto {
  item: ItemBiblioteca;
}

/** Cuerpo de `POST /api/biblioteca/adjuntar`: adjunta un item de la biblioteca a una pieza. */
export interface CuerpoAdjuntarBiblioteca {
  pieza_id: string;
  id: string;
}

/** Una foto del mismo burst (ráfaga) del keeper. */
export interface FotoRafaga {
  archivo: string;
  /** Miniatura (data URI o URL) para el visor. */
  thumb: string;
}

/** Respuesta de `GET /api/artes/propio/rafaga`: las fotos del mismo burst del keeper. */
export interface RespuestaRafaga {
  fotos: FotoRafaga[];
}
