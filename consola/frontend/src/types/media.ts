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
export interface ProveedorBuscarStock {
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
  // Campos EXTRA solo de la fuente «propio» (galería local del equipo vía el túnel keni-fotos):
  // identifican la foto original en la app de escritorio para adjuntarla por el túnel, no por URL.
  /** Id de la galería (partido) en la app de escritorio. */
  galeria_id?: string;
  /** Nombre del archivo original dentro de la galería. */
  archivo?: string;
  /** Dispositivo conectado que sirvió la candidata. */
  dispositivo?: string;
}

/** Respuesta de `GET /api/artes/stock/buscar`. */
export interface RespuestaBuscarStock {
  proveedores: ProveedorBuscarStock[];
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
 * Respuesta de `GET /api/artes/agencias/buscar`: misma forma que la de stock (proveedores +
 * candidatos), pero las candidatas son fotos LICENCIADAS de agencia (AFP), publicables con crédito.
 */
export type RespuestaBuscarAgencias = RespuestaBuscarStock;

/**
 * Cuerpo de `POST /api/artes/agencias/adjuntar`: la foto LICENCIADA elegida. A diferencia del stock,
 * `url` y `proveedor` son obligatorios y al adjuntar la pieza queda publicable (`imagen_origen=
 * "licenciada"`, `imagen_autorizada=true`), arrastrando el crédito/byline obligatorio de la agencia.
 */
export interface CuerpoAdjuntarAgencia {
  pieza_id: string;
  url: string;
  proveedor: string;
  autor?: string;
  licencia?: string;
  credito_url?: string;
}

// --- Fotos PROPIAS (galería local del equipo, vía el túnel keni-fotos; solo Claro Sports) ---
// Las apps de escritorio keni-fotos del usuario abren un túnel hacia keni-social; el backend hace
// fan-out de la búsqueda y, al adjuntar, trae el ORIGINAL por el túnel. Publicables sin licencia.

/** Fuente de la búsqueda de fotos del editor: bancos de stock, agencia licenciada o galería propia. */
export type FuenteFoto = "stock" | "agencias" | "propio";

/**
 * Respuesta de `GET /api/artes/propio/buscar`: misma forma que la de stock (proveedores +
 * candidatos). El único proveedor es «propio» y trae `dispositivos` (cuántas apps conectadas).
 */
export type RespuestaBuscarPropio = RespuestaBuscarStock;

/** Cuerpo de `POST /api/artes/propio/adjuntar`: la foto propia elegida (por túnel, no por URL). */
export interface CuerpoAdjuntarPropio {
  pieza_id: string;
  galeria_id: string;
  archivo: string;
  dispositivo?: string;
}

/** Una galería (partido) que ofrece una app de escritorio conectada. */
export interface GaleriaPropio {
  id: string;
  nombre: string;
  dia: string;
  fotos: number;
}

/** Un dispositivo (app de escritorio) conectado por el túnel, con sus galerías. */
export interface DispositivoPropio {
  dispositivo: string;
  version: string;
  galerias: GaleriaPropio[];
}

/** Respuesta de `GET /api/artes/propio/dispositivos`: las apps conectadas del usuario. */
export interface RespuestaDispositivosPropio {
  dispositivos: DispositivoPropio[];
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

// --- Configuración de FUENTES de stock (claves GLOBALES + toggles por marca) ---
// Las claves de Pexels/Pixabay son GLOBALES (una por agencia, vale para todas las
// marcas) y viven en Sistema → Proveedores; los toggles de qué bancos usa cada
// marca, en la subpágina de la etapa Stock (Contexto), siguen siendo por marca.

/**
 * Estado de un proveedor de fotos de stock a nivel GLOBAL (`GET /api/stock/proveedores`).
 * `configurado`/`pista` solo llegan cuando `requiere_clave` es `true`.
 */
export interface ProveedorStock {
  proveedor: string;
  nombre: string;
  /** El proveedor lleva API key (pexels/pixabay); los gratuitos no la necesitan. */
  requiere_clave: boolean;
  /** El proveedor puede operar (gratuito, o de pago con su clave global configurada). */
  disponible: boolean;
  /** La clave global de este proveedor está guardada (solo si `requiere_clave`). */
  configurado?: boolean;
  /** Pista no sensible de la clave guardada (`····last4`), solo si `requiere_clave`. */
  pista?: string | null;
}

/** Respuesta de `GET /api/stock/proveedores`: estado de las claves globales. */
export interface RespuestaProveedoresStock {
  proveedores: ProveedorStock[];
}

/**
 * Estado de un proveedor de fotos de stock PARA UNA MARCA (`GET /api/stock/fuentes?marca=`).
 * Si un banco de pago no se puede activar es porque su clave global falta: lo dice `disponible`.
 */
export interface FuenteStock {
  proveedor: string;
  nombre: string;
  /** El proveedor lleva API key (pexels/pixabay); los gratuitos no la necesitan. */
  requiere_clave: boolean;
  /** El proveedor puede operar (gratuito, o de pago con su clave global configurada). */
  disponible: boolean;
  /** Habilitado por el toggle de esta marca. */
  activa: boolean;
  /** Por qué no está disponible/activa (para el tooltip o la pista del toggle). */
  motivo: string;
}

/** Estado de las fuentes de stock de UNA marca (`GET /api/stock/fuentes?marca=`). */
export interface MarcaFuentesStock {
  marca: string;
  etiqueta: string;
  fuentes: FuenteStock[];
}

/** Cuerpo de `PUT /api/stock/fuentes/{marca}`: ids de proveedores habilitados. */
export interface CuerpoGuardarFuentesStock {
  activas: string[];
}

/** Cuerpo de `PUT /api/stock/clave`: clave GLOBAL de un proveedor (write-only). */
export interface CuerpoGuardarClaveStock {
  proveedor: string;
  api_key: string;
}

/** Respuesta al guardar o borrar la clave global de un proveedor de stock. */
export interface RespuestaClaveStock {
  configurado: boolean;
  mensaje: string;
}

/** Respuesta de `POST /api/stock/probar`: validación en vivo de una clave global. */
export interface RespuestaProbarStock {
  ok: boolean;
  mensaje: string;
}

// --- Credenciales de AGENCIAS (AFP / Reuters), dirigidas por metadatos ---
// El backend declara los campos de cada agencia (distintos entre ellas) y el front los
// pinta genéricamente. Mismo voto de pobreza que el resto de secretos: un campo `secreto`
// NUNCA trae `valor`, solo `configurado` + `pista` (`····last4`). Estas credenciales sirven
// a la agencia entera (noticias + foto licenciada); el env var sigue de respaldo.

/** Campo SECRETO de una agencia (API key, client secret…): write-only, nunca devuelve el valor. */
export interface CampoAgenciaSecreto {
  clave: string;
  etiqueta: string;
  secreto: true;
  /** El campo no es obligatorio para que la agencia opere. */
  opcional: boolean;
  /** El secreto está guardado. */
  configurado: boolean;
  /** Pista no sensible del secreto guardado (`····last4`), "" si no hay. */
  pista: string;
}

/** Campo NO secreto de una agencia (p. ej. base_url): trae su valor efectivo, editable. */
export interface CampoAgenciaPublico {
  clave: string;
  etiqueta: string;
  secreto: false;
  opcional: boolean;
  /** Valor efectivo actual (editable). */
  valor: string;
}

/** Un campo declarado por la agencia. Unión discriminada por `secreto`. */
export type CampoAgencia = CampoAgenciaSecreto | CampoAgenciaPublico;

/** Estado de una agencia de noticias/foto licenciada (AFP/Reuters). */
export interface Agencia {
  agencia: string;
  nombre: string;
  /** Sus credenciales obligatorias están todas guardadas. */
  configurado: boolean;
  /** La agencia puede operar ahora. */
  disponible: boolean;
  /** Por qué no está disponible (para mostrarlo discreto). */
  motivo: string;
  campos: CampoAgencia[];
}

/** Respuesta de `GET /api/stock/agencias`: estado de todas las agencias. */
export interface RespuestaAgencias {
  agencias: Agencia[];
}

/** Cuerpo de `PUT /api/stock/agencias/{agencia}`: solo los campos que el usuario tocó. */
export interface CuerpoGuardarAgencia {
  valores: Record<string, string>;
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
