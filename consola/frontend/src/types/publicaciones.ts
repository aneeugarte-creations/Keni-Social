import type { MarcaDisponible, Publicacion } from "../types.gen";
import type { Veredicto } from "./comun";

/** Resultado de programar una pieza en Metricool (preview dry-run o publicación real). */
export interface ResultadoProgramarMetricool {
  ok: boolean;
  /** true = solo se previsualizó (no se publicó); false = se publicó de verdad. */
  dry_run: boolean;
  /** Presente cuando ok=false: por qué no se pudo (sin credenciales, sin contenido…). */
  motivo?: string;
  /** Redes destino (nomenclatura Metricool: facebook/instagram/twitter/tiktok/youtube). */
  redes?: string[];
  /** Cuerpo exacto que se enviaría/envió al scheduler (preview). */
  cuerpo?: Record<string, unknown>;
  /** Id del post en Metricool (solo en publicación real). */
  id_post?: string;
  /** Estado por red devuelto por Metricool (solo en publicación real). */
  estados?: Record<string, string>;
}

/** Respuesta de POST /api/publicaciones/{id}/metricool. */
export interface RespuestaProgramarMetricool {
  resultado: ResultadoProgramarMetricool;
  /** Pieza tras el intento (actualizada a `publicado` si fue real); null si desapareció. */
  publicacion: Publicacion | null;
}

// --- Publicaciones ---

/** Estados del ciclo de vida de una publicación, en orden de avance.
 *
 * Se DERIVA del tipo generado `Publicacion["estado"]` para no driftar del backend
 * (el flujo de aprobación de equipo, #9, añadió `en_revision`): si el backend cambia
 * el set de estados, este alias lo sigue solo. */
export type EstadoPublicacion = Publicacion["estado"];

/** Una red social del catálogo (id canónico + límite de caracteres). */
export interface RedPublicacion {
  id: string;
  nombre: string;
  /** Límite de caracteres; `null` si la red no tiene límite. */
  limite: number | null;
}

/** Una opción de estado para los filtros. */
export interface EstadoOpcion {
  id: string;
  nombre: string;
}

/** Una línea editorial = etiqueta de clase `vertical` (la LÍNEA de contenido de una marca). */
export interface LineaEditorialOpcion {
  id: string;
  nombre: string;
  /** Marca dueña; "" = línea global (visible en todas las marcas). */
  marca: string;
}

export interface OpcionesPublicaciones {
  redes: RedPublicacion[];
  estados: EstadoOpcion[];
  marcas: MarcaDisponible[];
  /** Líneas editoriales (etiquetas verticales) para el filtro de Lista/Calendario/Feed. */
  lineas: LineaEditorialOpcion[];
  /**
   * Gate maestro `KENI_PUBLICAR_REAL`. Si es `false`, las piezas programadas NO salen
   * solas (el programador opera en dry-run): el SPA avisa cuando hay programadas en cola.
   */
  publicar_real: boolean;
}

/** Cuerpo para crear una publicación. */
export interface CuerpoCrearPublicacion {
  titulo: string;
  marca: string;
  red: string;
  contenido: string;
  estado?: EstadoPublicacion;
  fecha_programada?: string | null;
  veredicto?: Veredicto;
  origen?: string | null;
  /** Nombre del archivo de imagen adjunto (vacío para ninguna). */
  imagen?: string;
}

export interface CuerpoCrearPublicacionesLote {
  publicaciones: CuerpoCrearPublicacion[];
}

/** Cuerpo parcial para actualizar una publicación. */
export interface CuerpoActualizarPublicacion {
  titulo?: string;
  contenido?: string;
  /** Texto que va DENTRO de la imagen (copy-in), distinto del contenido. */
  copy_in?: string;
  estado?: EstadoPublicacion;
  fecha_programada?: string | null;
  /** Marca/desmarca la publicación como evergreen. */
  evergreen?: boolean;
  /** Nombre del archivo de imagen adjunto (`""` para quitarla). */
  imagen?: string;
  /** Media id de la FOTO CRUDA de fondo (separada de la placa compuesta `imagen`). */
  foto?: string;
  /** "Quitar plantilla": publicar solo la foto, sin la placa de marca encima. */
  placa_oculta?: boolean;
  /** Plantilla del estudio elegida ("" para volver a la placa de marca por defecto). */
  plantilla_diseno_id?: string;
  /** Reencuadre manual de la foto dentro del marco 4:5 (JSON `{"foco":[x,y],"zoom":z}`; "" = sin reencuadre). */
  foto_encuadre?: string;
  /** COLLAGE: JSON array `[{objeto,foco,zoom}, …]`, una foto por hueco. "" = sin collage. */
  fotos?: string;
  /** CARRUSEL: slides EXTRA en crudo, JSON `[{tipo:"imagen"|"video",objeto}, …]` en orden de
   *  publicación (la portada es la imagen compuesta de siempre). "" = sin slides. */
  carrusel?: string;
  /** ESPEJO entre redes (vive en la idea): editar el contenido de una pieza lo propaga a sus
   *  redes hermanas. ON por defecto; OFF = cada red se edita por separado. */
  espejo?: boolean;
}

/** Cuerpo opcional para duplicar una publicación (red/marca/título destino). */
export interface CuerpoDuplicarPublicacion {
  red?: string;
  marca?: string;
  titulo?: string;
}


// --- Hashtags ---

/** Un grupo de hashtags guardado. */
export interface GrupoHashtags {
  id: string;
  nombre: string;
  /** Marca asociada (`""` si es general). */
  marca: string;
  marca_nombre: string;
  hashtags: string[];
}

export interface RespuestaHashtags {
  grupos: GrupoHashtags[];
}

export interface RespuestaGrupoHashtags {
  grupo: GrupoHashtags;
}

/** Cuerpo para crear o editar un grupo de hashtags. */
export interface CuerpoGrupoHashtags {
  nombre: string;
  /** Marca asociada (opcional). */
  marca?: string;
  hashtags: string[];
}

/** Cuerpo para pedir sugerencias de hashtags con IA. */
export interface CuerpoSugerirHashtags {
  texto: string;
  marca: string;
  red?: string;
}

export interface RespuestaSugerirHashtags {
  hashtags: string[];
}

// --- Franjas (colas de publicación) ---

/** Una franja horaria de la cola de publicación. */
export interface Franja {
  id: string;
  /** Marca asociada (`""` si aplica a todas). */
  marca: string;
  marca_nombre: string;
  /** Red asociada (`""` si aplica a todas). */
  red: string;
  red_nombre: string;
  /** Día de la semana: 0=lunes .. 6=domingo. */
  dia_semana: number;
  /** Hora en formato "HH:MM" (UTC: el backend almacena instantes en UTC). */
  hora: string;
  /** Línea del plan a la que sirve ('' = franja genérica). */
  categoria: string;
}

export interface RespuestaFranjas {
  franjas: Franja[];
}

export interface RespuestaFranja {
  franja: Franja;
}

/** Cuerpo para crear una franja. */
export interface CuerpoCrearFranja {
  dia_semana: number;
  hora: string;
  marca?: string;
  red?: string;
  /** Línea del plan ('' = genérica): la pieza de esa línea usa estos horarios. */
  categoria?: string;
}

// --- Cadencia por red (margen entre posts) ---

/**
 * Una cadencia: scheduling por margen mínimo entre publicaciones de una red,
 * dentro de una ventana horaria y unos días, opcionalmente acotada a marca/red.
 */
export interface Cadencia {
  id: string;
  /** Marca asociada (`""` si aplica a todas). */
  marca: string;
  marca_nombre: string;
  /** Red asociada (`""` si aplica a todas). */
  red: string;
  red_nombre: string;
  /** Minutos mínimos entre posts. */
  margen_min: number;
  /** Hora de inicio de la ventana, formato "HH:MM". */
  hora_inicio: string;
  /** Hora de fin de la ventana, formato "HH:MM". */
  hora_fin: string;
  /** Días activos: 0=lunes .. 6=domingo. */
  dias: number[];
  activo: boolean;
}

export interface RespuestaCadencias {
  cadencias: Cadencia[];
}

export interface RespuestaCadencia {
  cadencia: Cadencia;
}

/** Cuerpo para crear o actualizar (UPSERT por marca+red) una cadencia. */
export interface CuerpoGuardarCadencia {
  marca?: string;
  red?: string;
  margen_min: number;
  hora_inicio: string;
  hora_fin: string;
  dias: number[];
  activo?: boolean;
}

/** Respuesta del borrado batch (`POST /api/publicaciones/borrar-lote`). */
export interface RespuestaBorrarLotePublicaciones {
  /** Cuántas se borraron de verdad. */
  borradas: number;
  /** Ids que NO se pudieron borrar (ya no existían); el resto del lote no se aborta. */
  fallos: string[];
}

export interface FiltrosPublicaciones {
  marca?: string;
  red?: string;
  estado?: string;
  /** Id de la línea editorial (etiqueta vertical) por la que filtrar. */
  linea?: string;
  /** "1" para mostrar solo publicaciones evergreens. */
  evergreen?: string;
  /** Paginacion offset-based (#121): tamaño de pagina; ausente = conjunto completo. */
  limite?: string;
  /** Paginacion offset-based (#121): offset; ausente = 0. */
  desplazamiento?: string;
  /**
   * Paginacion KEYSET para el feed (scroll infinito): clave `"<creado>|<id>"` de la última
   * fila vista. Devuelve solo las piezas posteriores en el orden `creado DESC`. La respuesta
   * trae `paginacion.cursor_siguiente` para encadenar; ausente = primera página/desde el inicio.
   */
  cursor?: string;
  /**
   * Activa el MODO FEED (keyset/scroll infinito) en la PRIMERA página, que llega sin `cursor`:
   * acota a un tamaño de página y devuelve `paginacion.cursor_siguiente`. Sin esto (y sin
   * `limite`), el endpoint devuelve el conjunto completo (modo retrocompatible). `"1"` para activar.
   */
  feed?: string;
  /** Permite pasarse a `query()` (Record<string, string | undefined>). */
  [clave: string]: string | undefined;
}

// --- Conexiones (clave de imagen IA + tokens de redes) ---
//
// Los secretos son write-only: nunca llegan al frontend. Del servidor solo se
// recibe el estado (`configurado`/`conectado`) y, para la imagen IA, una
// `pista` no sensible (p. ej. los últimos caracteres de la clave).

/** Un modelo de imagen IA de la lista curada (id + etiqueta legible para el dropdown). */
export interface ModeloImagen {
  id: string;
  etiqueta: string;
}

/** Estado de la configuración del proveedor de imagen con IA. */
export interface RespuestaConexionImagen {
  proveedor: string;
  /** Modelo de imagen EN USO (con su precedencia: almacén > env > por defecto). */
  modelo: string;
  /** Lista curada de modelos disponibles para el dropdown del selector. */
  modelos: ModeloImagen[];
  configurado: boolean;
  /** Pista no sensible de la clave (nunca el valor completo). */
  pista: string;
}

/** Cuerpo para fijar el modelo de imagen IA. */
export interface CuerpoGuardarModeloImagen {
  modelo: string;
}

/** Respuesta al fijar el modelo de imagen IA (devuelve el modelo guardado). */
export interface RespuestaGuardarModeloImagen {
  modelo: string;
}

/** Cuerpo para guardar la clave del proveedor de imagen IA. */
export interface CuerpoGuardarConexionImagen {
  /** Identificador del proveedor (opcional; el backend tiene uno por defecto). */
  proveedor?: string;
  api_key: string;
}

/** Respuesta al guardar la clave de imagen IA. */
export interface RespuestaGuardarConexionImagen {
  configurado: boolean;
  mensaje: string;
}

/** Respuesta de la prueba de conexión de imagen IA. */
export interface RespuestaProbarConexionImagen {
  ok: boolean;
  mensaje: string;
}

/** Estado de conexión de Metricool para UNA marca (sin exponer el token). */
export interface MarcaMetricool {
  marca: string;
  etiqueta: string;
  conectado: boolean;
  /** Pista no sensible del user_id (solo si está conectada). */
  user_id_pista?: string;
  /** blogId de Metricool (solo si está conectada; no es secreto). */
  blog_id?: string;
}

export interface RespuestaMetricool {
  marcas: MarcaMetricool[];
}

/** Cuerpo para descubrir las marcas (blogId) de un token de Metricool. */
export interface CuerpoPerfilesMetricool {
  user_token: string;
  user_id: string;
}

/** Una marca de Metricool descubierta vía simpleProfiles (sin token). */
export interface PerfilMetricool {
  blog_id: string;
  label: string;
}

/** Respuesta al descubrir marcas: lista de {blog_id, label}. */
export interface RespuestaPerfilesMetricool {
  marcas: PerfilMetricool[];
}

/** Cuerpo para guardar las credenciales de Metricool de una marca. */
export interface CuerpoGuardarMetricool {
  user_token: string;
  user_id: string;
  blog_id: string;
}

/** Respuesta al guardar una credencial de Metricool. */
export interface RespuestaGuardarMetricool {
  conectado: boolean;
  mensaje: string;
}

/** Respuesta de la prueba en vivo de una credencial de Metricool. */
export interface RespuestaProbarMetricool {
  ok: boolean;
  detalle: string;
}
